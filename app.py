import os
import sys
import io

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import uuid
import json
import zipfile
import shutil
import subprocess
import threading
import queue
import time
import tempfile
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify,
    send_file, Response, stream_with_context
)
from werkzeug.utils import secure_filename


def _decode_robot_bytes(raw: bytes) -> str:
    """Decode raw bytes from an uploaded robot file.

    Handles:
    - UTF-8 BOM  (0xEF 0xBB 0xBF) – Notepad / some Windows editors
    - UTF-16 BOM – rare but possible
    - CRLF / CR-only line endings – Windows Notepad
    Always returns a clean LF-only string so the temp-file write
    (text mode) never doubles the \\r on Windows.
    """
    # 1. Detect & strip BOM, choose codec
    for bom, codec in [
        (b'\xef\xbb\xbf', 'utf-8-sig'),    # UTF-8 BOM
        (b'\xff\xfe',      'utf-16'),        # UTF-16 LE BOM
        (b'\xfe\xff',      'utf-16'),        # UTF-16 BE BOM
    ]:
        if raw.startswith(bom):
            content = raw.decode(codec, errors='replace')
            break
    else:
        # No BOM: try UTF-8 first, fall back to latin-1
        try:
            content = raw.decode('utf-8')
        except UnicodeDecodeError:
            content = raw.decode('latin-1')

    # 2. Normalise line endings → LF only
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    return content

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB
app.config['SECRET_KEY'] = os.urandom(24)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'uploads'
RESULTS_DIR = BASE_DIR / 'results'
SETTINGS_FILE = BASE_DIR / 'settings.json'
UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# In-memory store for ongoing runs
run_store: dict = {}
cleanup_started = False

DEFAULT_SETTINGS = {
    'cleanup_age_hours': 24,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_dir(path: Path):
    try:
        shutil.rmtree(str(path), ignore_errors=True)
    except Exception:
        pass


def _load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                settings.update(saved)
        except Exception:
            pass
    return settings


def _save_settings(settings: dict) -> dict:
    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings)
    age = merged.get('cleanup_age_hours', DEFAULT_SETTINGS['cleanup_age_hours'])
    try:
        age = int(age)
    except (TypeError, ValueError):
        age = DEFAULT_SETTINGS['cleanup_age_hours']
    merged['cleanup_age_hours'] = max(1, age)
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding='utf-8')
    return merged


def _cleanup_old_files(age_hours=None) -> dict:
    if age_hours is None:
        age_hours = int(_load_settings().get('cleanup_age_hours', 24))
    cutoff = time.time() - (max(1, int(age_hours)) * 3600)
    removed = {'uploads': 0, 'results': 0}

    for label, root in [('uploads', UPLOAD_DIR), ('results', RESULTS_DIR)]:
        if not root.exists():
            continue
        for item in root.iterdir():
            try:
                if item.stat().st_mtime >= cutoff:
                    continue
                if item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                removed[label] += 1
            except Exception:
                pass
    return removed


def _start_cleanup_worker():
    global cleanup_started
    if cleanup_started:
        return
    cleanup_started = True

    def _worker():
        while True:
            try:
                _cleanup_old_files()
            except Exception:
                pass
            time.sleep(3600)

    threading.Thread(target=_worker, daemon=True).start()


def _zip_dir(src: Path, dest: Path):
    with zipfile.ZipFile(str(dest), 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in src.rglob('*'):
            if f.is_file():
                zf.write(str(f), str(f.relative_to(src)))


# ---------------------------------------------------------------------------
# Routes – pages
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/settings', methods=['GET', 'POST'])
def app_settings():
    if request.method == 'GET':
        return jsonify(_load_settings())
    try:
        data = request.get_json(silent=True) or {}
        return jsonify(_save_settings(data))
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


@app.route('/api/cleanup', methods=['POST'])
def cleanup_files():
    try:
        data = request.get_json(silent=True) or {}
        age_hours = data.get('cleanup_age_hours')
        removed = _cleanup_old_files(age_hours)
        return jsonify({'success': True, 'removed': removed})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


# ---------------------------------------------------------------------------
# API – Report Merger
# ---------------------------------------------------------------------------

@app.route('/api/merge', methods=['POST'])
def merge_reports():
    import hashlib
    from modules.merger import merge_xml_reports
    try:
        files = request.files.getlist('files')
        flatten = request.form.get('flatten', 'false').lower() == 'true'
        update_mode = request.form.get('update_mode', 'false').lower() == 'true'
        keep_update_history = request.form.get('keep_update_history', 'true').lower() == 'true'
        raw_output_name = request.form.get('output_name', '').strip()
        output_name = secure_filename(raw_output_name) if raw_output_name else None
        suite_name = request.form.get('suite_name', '').strip() or None

        if len(files) < 2:
            return jsonify({'error': 'At least 2 output.xml files are required'}), 400

        run_id = str(uuid.uuid4())
        work_dir = UPLOAD_DIR / run_id
        work_dir.mkdir(parents=True)

        # -- Deduplicate files with same name & content ----------------------
        # Read all file contents into memory first so we can compare them
        file_entries = []  # list of (original_name, content_bytes)
        for f in files:
            if not f.filename:
                continue
            raw = f.read()
            file_entries.append((f.filename, raw))

        # Group by (secure_name, content_hash) to detect exact duplicates
        seen_hashes: dict[str, list[str]] = {}   # hash -> [original_names]
        unique_entries = []       # deduplicated (original_name, content_bytes)
        skipped_duplicates = []   # list of original filenames that were skipped

        for orig_name, content in file_entries:
            content_hash = hashlib.sha256(content).hexdigest()
            key = f"{secure_filename(orig_name)}::{content_hash}"
            if key in seen_hashes:
                skipped_duplicates.append(orig_name)
                seen_hashes[key].append(orig_name)
            else:
                seen_hashes[key] = [orig_name]
                unique_entries.append((orig_name, content))

        # If ALL files are identical, nothing meaningful to merge
        if len(unique_entries) < 2:
            _cleanup_dir(work_dir)
            dup_names = ', '.join(dict.fromkeys(e[0] for e in file_entries))
            if len(unique_entries) == 1 and skipped_duplicates:
                return jsonify({
                    'error': (
                        f'All input files are identical ({dup_names}). '
                        f'At least 2 files with different content are required to merge.'
                    ),
                    'skipped_duplicates': skipped_duplicates,
                }), 400
            return jsonify({'error': 'At least 2 valid files are required'}), 400

        # -- Save unique files to disk, handle name collisions ---------------
        xml_paths = []
        name_counter: dict[str, int] = {}  # secure_name -> next suffix

        for orig_name, content in unique_entries:
            base_name = secure_filename(orig_name)
            stem = Path(base_name).stem
            ext = Path(base_name).suffix or '.xml'

            if base_name in name_counter:
                idx = name_counter[base_name]
                name_counter[base_name] = idx + 1
                fn = f"{stem}_{idx}{ext}"
            else:
                name_counter[base_name] = 2
                fn = base_name

            p = work_dir / fn
            p.write_bytes(content)
            xml_paths.append(str(p))

        result_dir = RESULTS_DIR / run_id
        result_dir.mkdir(parents=True)

        result = merge_xml_reports(
            xml_paths,
            result_dir,
            output_name,
            flatten,
            update_mode,
            suite_name,
            keep_update_history,
        )

        zip_path = RESULTS_DIR / f'{run_id}.zip'
        _zip_dir(result_dir, zip_path)
        _cleanup_dir(work_dir)

        resp = {
            'success': True,
            'run_id': run_id,
            'files': [Path(fp).name for fp in result['files']],
            'download_url': f'/api/download/{run_id}',
            'report_url': f'/api/merge/{run_id}/report',
            'log_url': f'/api/merge/{run_id}/log',
            'update_mode': update_mode,
            'keep_update_history': keep_update_history,
            'stripped_history_count': result.get('stripped_history_count', 0),
        }
        if skipped_duplicates:
            resp['skipped_duplicates'] = skipped_duplicates
            resp['unique_file_count'] = len(unique_entries)
        return jsonify(resp)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API – File Statistics
# ---------------------------------------------------------------------------

@app.route('/api/statistics', methods=['POST'])
def get_statistics():
    from modules.statistics import analyze_robot_file
    try:
        content = None
        filename = 'test.robot'

        if 'file' in request.files:
            f = request.files['file']
            filename = f.filename or 'test.robot'
            content = _decode_robot_bytes(f.read())
        elif request.is_json and 'content' in request.json:
            content = request.json['content']
            filename = request.json.get('filename', 'test.robot')
        else:
            data = request.form.get('content')
            if data:
                content = data
            else:
                return jsonify({'error': 'No file content provided'}), 400

        result = analyze_robot_file(content, filename)
        return jsonify(result)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# API – Test Runner
# ---------------------------------------------------------------------------

@app.route('/api/run', methods=['POST'])
def start_run():
    try:
        if 'robot_file' not in request.files:
            return jsonify({'error': 'Missing robot file'}), 400

        robot_file = request.files['robot_file']
        config_file = request.files.get('config_file')

        include_tags = request.form.get('include_tags', '')
        exclude_tags = request.form.get('exclude_tags', '')
        extra_vars = request.form.get('variables', '')

        run_id = str(uuid.uuid4())
        work_dir = UPLOAD_DIR / run_id
        work_dir.mkdir(parents=True)
        output_dir = RESULTS_DIR / run_id
        output_dir.mkdir(parents=True)

        robot_fn = secure_filename(robot_file.filename or 'test.robot')
        robot_path = work_dir / robot_fn
        robot_file.save(str(robot_path))

        config_path = None
        if config_file and config_file.filename:
            cfg_fn = secure_filename(config_file.filename)
            config_path = work_dir / cfg_fn
            config_file.save(str(config_path))

        options = []
        if include_tags:
            for tag in include_tags.split(','):
                t = tag.strip()
                if t:
                    options += ['--include', t]
        if exclude_tags:
            for tag in exclude_tags.split(','):
                t = tag.strip()
                if t:
                    options += ['--exclude', t]
        if extra_vars:
            for line in extra_vars.splitlines():
                line = line.strip()
                if ':' in line:
                    options += ['--variable', line]
        if config_path:
            options += ['--variablefile', str(config_path)]

        q: queue.Queue = queue.Queue()
        run_store[run_id] = {
            'queue': q,
            'status': 'running',
            'output_dir': str(output_dir),
            'exit_code': None,
        }

        def _run():
            cmd = [
                sys.executable, '-m', 'robot',
                '--outputdir', str(output_dir),
                *options,
                str(robot_path),
            ]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace',
                )
                for line in proc.stdout:
                    q.put({'type': 'output', 'data': line.rstrip()})
                proc.wait()
                exit_code = proc.returncode
                run_store[run_id]['exit_code'] = exit_code
                run_store[run_id]['status'] = 'done'

                zip_path = RESULTS_DIR / f'{run_id}_results.zip'
                _zip_dir(output_dir, zip_path)

                q.put({
                    'type': 'done',
                    'exit_code': exit_code,
                    'download_url': f'/api/download/{run_id}',
                    'report_url': f'/api/run/{run_id}/report',
                })
            except Exception as exc:
                run_store[run_id]['status'] = 'error'
                q.put({'type': 'error', 'data': str(exc)})
            finally:
                _cleanup_dir(work_dir)

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({'run_id': run_id})

    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/run/<run_id>/stream')
def stream_run(run_id):
    if run_id not in run_store:
        return jsonify({'error': 'Run not found'}), 404

    def _generate():
        q = run_store[run_id]['queue']
        while True:
            try:
                msg = q.get(timeout=60)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get('type') in ('done', 'error'):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return Response(
        stream_with_context(_generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/run/<run_id>/report')
def view_report(run_id):
    report = RESULTS_DIR / run_id / 'report.html'
    if not report.exists():
        return 'Report not found', 404
    return send_file(str(report))


@app.route('/api/run/<run_id>/log')
def view_log(run_id):
    log = RESULTS_DIR / run_id / 'log.html'
    if not log.exists():
        return 'Log not found', 404
    return send_file(str(log))


# ---------------------------------------------------------------------------
# API – Merge Report Viewer
# ---------------------------------------------------------------------------

@app.route('/api/merge/<run_id>/report')
def view_merge_report(run_id):
    result_dir = RESULTS_DIR / run_id
    for candidate in [result_dir / 'report.html', *result_dir.glob('*_report.html')]:
        if candidate.exists():
            return send_file(str(candidate))
    return 'Report not found', 404


@app.route('/api/merge/<run_id>/log')
def view_merge_log(run_id):
    result_dir = RESULTS_DIR / run_id
    for candidate in [result_dir / 'log.html', *result_dir.glob('*_log.html')]:
        if candidate.exists():
            return send_file(str(candidate))
    return 'Log not found', 404


# ---------------------------------------------------------------------------
# API – Download
# ---------------------------------------------------------------------------

@app.route('/api/download/<run_id>')
def download_results(run_id):
    for candidate in [
        RESULTS_DIR / f'{run_id}_results.zip',
        RESULTS_DIR / f'{run_id}.zip',
    ]:
        if candidate.exists():
            return send_file(
                str(candidate),
                as_attachment=True,
                download_name='results.zip',
                mimetype='application/zip',
            )
    return jsonify({'error': 'Results not found'}), 404


# ---------------------------------------------------------------------------
# API – Name Formatter
# ---------------------------------------------------------------------------

@app.route('/api/format/preview', methods=['POST'])
def format_preview():
    from modules.formatter import preview_format
    try:
        content, filename = _read_content_from_request()
        rules = _parse_rules_from_request()
        result = preview_format(content, rules)
        return jsonify(result)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/format/apply', methods=['POST'])
def format_apply():
    from modules.formatter import apply_format
    try:
        content, filename = _read_content_from_request()
        rules = _parse_rules_from_request()
        modified = apply_format(content, rules)

        run_id = str(uuid.uuid4())
        out_path = RESULTS_DIR / f'{run_id}_formatted.robot'
        out_path.write_text(modified, encoding='utf-8')

        return send_file(
            str(out_path),
            as_attachment=True,
            download_name=f'formatted_{Path(filename).name}',
            mimetype='text/plain',
        )
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def _read_content_from_request():
    filename = 'test.robot'
    if 'file' in request.files:
        f = request.files['file']
        filename = f.filename or filename
        content = _decode_robot_bytes(f.read())
    elif request.is_json and 'content' in request.json:
        content = request.json['content']
        filename = request.json.get('filename', filename)
    elif request.form.get('content'):
        content = request.form['content']
        filename = request.form.get('filename', filename)
    else:
        raise ValueError('No file content provided')
    return content, filename


def _parse_rules_from_request():
    if request.is_json:
        return request.json.get('rules', {})
    raw = request.form.get('rules', '{}')
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import socket

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = '127.0.0.1'

    port = int(os.environ.get('PORT', 5000))

    print('\n' + '=' * 55)
    print('  Robot Framework Web Tool')
    print('=' * 55)
    print(f'  Local  : http://localhost:{port}')
    print(f'  Network: http://{local_ip}:{port}')
    print('=' * 55)
    print('  Press Ctrl+C to stop\n')

    _start_cleanup_worker()
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
