"""
Report Merger – merges Robot Framework output.xml files using the
robot.api.ExecutionResult API, then generates log.html + report.html
via a rebot subprocess (following the pattern in refs/test_executor.py).

Two merge modes:
  - Combine mode (default): all unique test cases from every file are included.
  - Update mode: tests from later files replace tests with the same name in
    earlier files (uses rebot --merge).  Use this to fold a re-run's PASS
    results back into an older report.
"""
from __future__ import annotations

import datetime as _dt
import sys
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


# ---------------------------------------------------------------------------
# Timing helpers – compatible with RF 6 (string timestamps) and RF 7
# (datetime.datetime timestamps / timedelta elapsed_time).
# ---------------------------------------------------------------------------

def _suite_elapsed_ms(suite) -> int:
    """Return the elapsed time of *suite* in milliseconds.

    Tries, in order:
      1. RF 7+  suite.elapsed_time  → timedelta
      2. RF 6   suite.elapsedtime   → int (ms)
      3. Direct computation from starttime / endtime strings or datetime objs
    """
    et = getattr(suite, 'elapsed_time', None)
    if isinstance(et, _dt.timedelta):
        return max(0, int(et.total_seconds() * 1000))

    et = getattr(suite, 'elapsedtime', None)
    if et is not None:
        return max(0, int(et))

    s, e = getattr(suite, 'starttime', None), getattr(suite, 'endtime', None)
    if s and e:
        try:
            if isinstance(s, _dt.datetime):
                return max(0, int((e - s).total_seconds() * 1000))
            # RF 6 string format: 'YYYYMMDD HH:MM:SS.mmm'
            fmt = '%Y%m%d %H:%M:%S.%f'
            diff = _dt.datetime.strptime(e, fmt) - _dt.datetime.strptime(s, fmt)
            return max(0, int(diff.total_seconds() * 1000))
        except Exception:
            pass
    return 0


def _advance_timestamp(ts, ms: int):
    """Return *ts* advanced by *ms* milliseconds.

    *ts* may be a ``datetime.datetime`` (RF 7) or a string ``'YYYYMMDD HH:MM:SS.mmm'`` (RF 6).
    Returns the same type as *ts*.
    """
    delta = _dt.timedelta(milliseconds=ms)
    if isinstance(ts, _dt.datetime):
        return ts + delta
    # RF 6 string
    fmt = '%Y%m%d %H:%M:%S.%f'
    end = _dt.datetime.strptime(ts, fmt) + delta
    return end.strftime('%Y%m%d %H:%M:%S.') + f'{end.microsecond // 1000:03d}'


def _repair_suite_timing(suite) -> None:
    """Recompute missing ``start_time`` / ``end_time`` on *suite* and its descendants.

    ``rebot --merge`` (used by the Update / Replace mode) sometimes drops the
    suite-level ``start`` attribute when results from later files override
    earlier ones — the merged report then shows the suite Start Time / End Time
    as ``N/A``.  This helper walks the result tree bottom-up and fills in the
    missing timestamps from the actual tests / sub-suites contained in each
    suite, so the report correctly displays the real run window.
    """
    for sub in suite.suites:
        _repair_suite_timing(sub)

    starts: list = []
    ends: list = []

    for test in suite.tests:
        st = getattr(test, 'start_time', None)
        et = getattr(test, 'end_time', None)
        if st:
            starts.append(st)
        if et:
            ends.append(et)

    for sub in suite.suites:
        st = getattr(sub, 'start_time', None)
        et = getattr(sub, 'end_time', None)
        if st:
            starts.append(st)
        if et:
            ends.append(et)

    if starts and not getattr(suite, 'start_time', None):
        suite.start_time = min(starts)
    if ends and not getattr(suite, 'end_time', None):
        suite.end_time = max(ends)


def _strip_merge_history_messages(output_xml: Path) -> int:
    """Remove Robot Framework rerun merge history from test status messages.

    ``rebot --merge`` stores previous results as HTML text inside each
    ``<test><status>`` element.  Keeping that text is useful for audit trails,
    but when users only want the latest test state it creates repeated old
    FAIL/PASS blocks in output.xml, log.html and report.html.
    """
    tree = ET.parse(str(output_xml))
    root = tree.getroot()
    removed = 0

    for test in root.iter('test'):
        status = test.find('status')
        if status is None or not status.text:
            continue
        if 'Test has been re-executed and results merged' in status.text or 'class="merge"' in status.text:
            status.text = None
            removed += 1

    if removed:
        tree.write(str(output_xml), encoding='UTF-8', xml_declaration=True)
    return removed


def _output_paths(output_dir: Path, output_name: str | None) -> tuple[Path, Path, Path]:
    if output_name:
        return (
            output_dir / f'{output_name}_output.xml',
            output_dir / f'{output_name}_log.html',
            output_dir / f'{output_name}_report.html',
        )
    return (
        output_dir / 'output.xml',
        output_dir / 'log.html',
        output_dir / 'report.html',
    )


def _child_elements(elem: ET.Element, tag_name: str) -> list[ET.Element]:
    """Return direct children whose tag matches *tag_name* without namespaces."""
    return [child for child in list(elem) if child.tag.rsplit('}', 1)[-1] == tag_name]


def _find_status(test: ET.Element) -> ET.Element | None:
    for child in list(test):
        if child.tag.rsplit('}', 1)[-1] == 'status':
            return child
    return None


def _iter_suite_tests(suite: ET.Element, suite_path: tuple[str, ...] = ()):
    suite_name = suite.get('name', '')
    current_path = (*suite_path, suite_name) if suite_name else suite_path

    for test in _child_elements(suite, 'test'):
        status = _find_status(test)
        yield {
            'name': test.get('name', ''),
            'suite': ' / '.join(current_path),
            'status': status.get('status', '') if status is not None else '',
            'message': (status.text or '').strip()[:300] if status is not None else '',
        }

    for sub_suite in _child_elements(suite, 'suite'):
        yield from _iter_suite_tests(sub_suite, current_path)


def _root_suite(root: ET.Element) -> ET.Element | None:
    if root.tag.rsplit('}', 1)[-1] == 'suite':
        return root
    for child in list(root):
        if child.tag.rsplit('}', 1)[-1] == 'suite':
            return child
    return None


def _read_test_occurrences(xml_path: str, file_index: int, file_name: str) -> list[dict]:
    tree = ET.parse(xml_path)
    suite = _root_suite(tree.getroot())
    if suite is None:
        return []

    occurrences = []
    for item in _iter_suite_tests(suite):
        if not item['name']:
            continue
        occurrences.append({
            **item,
            'file_index': file_index,
            'file_name': file_name,
        })
    return occurrences


def list_update_candidates(xml_paths: list[str], file_names: list[str] | None = None) -> list[dict]:
    """List test names that can be replaced by a later file in update mode."""
    if file_names is None:
        file_names = [Path(p).name for p in xml_paths]

    seen_by_name: dict[str, list[dict]] = {}
    candidates: dict[str, dict] = {}

    for idx, xml_path in enumerate(xml_paths):
        file_name = file_names[idx] if idx < len(file_names) else Path(xml_path).name
        for occ in _read_test_occurrences(xml_path, idx, file_name):
            name = occ['name']
            previous = seen_by_name.get(name, [])
            if previous:
                candidate = candidates.setdefault(name, {
                    'name': name,
                    'earlier': [],
                    'later': [],
                })
                for prev in previous:
                    if not any(
                        p['file_index'] == prev['file_index'] and p['suite'] == prev['suite']
                        for p in candidate['earlier']
                    ):
                        candidate['earlier'].append(prev)
                candidate['later'].append(occ)
            seen_by_name.setdefault(name, []).append(occ)

    return sorted(candidates.values(), key=lambda item: item['name'].lower())


class MetadataConflictError(RuntimeError):
    def __init__(self, conflicts: list[dict]):
        super().__init__('Metadata differs between input files.')
        self.conflicts = conflicts


def _metadata_conflicts_from_suites(suites: list, file_names: list[str] | None = None) -> list[dict]:
    all_keys: list[str] = []
    for suite in suites:
        for key in suite.metadata:
            text_key = str(key)
            if text_key not in all_keys:
                all_keys.append(text_key)

    values_by_key: dict[str, list[dict]] = {key: [] for key in all_keys}
    for idx, suite in enumerate(suites):
        file_name = file_names[idx] if file_names and idx < len(file_names) else Path(str(getattr(suite, 'source', '') or f'File {idx + 1}')).name
        for key in all_keys:
            text = str(suite.metadata.get(key, ''))
            choices = values_by_key.setdefault(key, [])
            if not any(choice['value'] == text for choice in choices):
                choices.append({
                    'value': text,
                    'file_index': idx,
                    'file_name': file_name,
                    'is_default': len(choices) == 0,
                })

    return [
        {'key': key, 'choices': choices}
        for key, choices in sorted(values_by_key.items())
        if len(choices) > 1
    ]


def _suite_has_tests(suite: ET.Element) -> bool:
    if _child_elements(suite, 'test'):
        return True
    return any(_suite_has_tests(sub) for sub in _child_elements(suite, 'suite'))


def _filter_suite_for_selected_tests(suite: ET.Element, selected_names: set[str], eligible_names: set[str]) -> int:
    kept = 0

    for child in list(suite):
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'test':
            name = child.get('name', '')
            if name in selected_names and name in eligible_names:
                kept += 1
            else:
                suite.remove(child)
        elif tag == 'suite':
            kept += _filter_suite_for_selected_tests(child, selected_names, eligible_names)
            if not _suite_has_tests(child):
                suite.remove(child)

    return kept


def _prepare_selective_update_paths(
    xml_paths: list[str],
    selected_names: set[str],
    temp_dir: Path,
) -> tuple[list[str], int]:
    """Return XML paths for selective update mode.

    The first file is kept intact. Later files are copied to temporary XMLs
    with only selected tests that have appeared in an earlier file.
    """
    prepared = [xml_paths[0]]
    seen_names: set[str] = set()
    kept_total = 0

    for idx, xml_path in enumerate(xml_paths):
        original_occurrences = _read_test_occurrences(xml_path, idx, Path(xml_path).name)
        current_names = {occ['name'] for occ in original_occurrences}

        if idx == 0:
            seen_names.update(current_names)
            continue

        tree = ET.parse(xml_path)
        suite = _root_suite(tree.getroot())
        if suite is not None:
            kept = _filter_suite_for_selected_tests(suite, selected_names, seen_names)
            if kept:
                filtered_path = temp_dir / f'selected_update_{idx}.xml'
                tree.write(str(filtered_path), encoding='UTF-8', xml_declaration=True)
                prepared.append(str(filtered_path))
                kept_total += kept

        seen_names.update(current_names)

    return prepared, kept_total


def merge_xml_reports(
    xml_paths: list[str],
    output_dir: Path,
    output_name: str | None = 'merged',
    flatten: bool = False,
    update_mode: bool = False,
    suite_name: str | None = None,
    keep_update_history: bool = True,
    selected_update_tests: list[str] | None = None,
    metadata_overrides: dict[str, str] | None = None,
    file_names: list[str] | None = None,
) -> dict:
    """
    Merge Robot Framework output XML files.

    Combine mode (update_mode=False, default):
      Step 1 – Use ExecutionResult API to combine XMLs and (optionally) flatten
                the suite structure, then save the merged output.xml.
      Step 2 – Run `python -m robot.rebot` on the merged XML to produce
                log.html and report.html.

    Update mode (update_mode=True):
      Run `python -m robot.rebot --merge` directly on all input XMLs so that
      test results from later files replace results of the same-named tests in
      earlier files.  Use this to fold a re-run's PASS results back into an
      existing report without duplicating tests.

    Returns a dict with key ``files`` – list of created file paths.
    """
    output_xml, output_log, output_report = _output_paths(output_dir, output_name)

    run_kwargs: dict = dict(
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    if sys.platform == 'win32':
        run_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    if update_mode:
        # ------------------------------------------------------------------ #
        # Update mode: rebot --merge lets later files override earlier ones   #
        #                                                                     #
        # We run rebot --merge to produce only the merged XML, then patch up  #
        # any missing suite-level start_time / end_time (rebot --merge often  #
        # drops the suite ``start`` attribute, which would make the report    #
        # show Start Time / End Time as N/A), and finally re-run rebot on the #
        # repaired XML to regenerate log.html and report.html.                #
        # ------------------------------------------------------------------ #
        effective_name = suite_name or output_name
        selective_count = 0
        temp_ctx = None
        merge_paths = xml_paths

        if selected_update_tests is not None:
            selected_names = {name for name in selected_update_tests if name}
            if not selected_names:
                raise RuntimeError('No test cases were selected for selective update.')
            temp_ctx = tempfile.TemporaryDirectory(prefix='rf_selective_update_')
            merge_paths, selective_count = _prepare_selective_update_paths(
                xml_paths,
                selected_names,
                Path(temp_ctx.name),
            )
            if len(merge_paths) < 2 or selective_count == 0:
                temp_ctx.cleanup()
                raise RuntimeError('None of the selected test cases can replace an earlier result.')

        rebot_cmd = [
            sys.executable, '-m', 'robot.rebot',
            '--merge',
            '--outputdir', str(output_dir),
            '--output', output_xml.name,
            '--log', 'NONE',
            '--report', 'NONE',
            *merge_paths,
        ]
        if effective_name:
            rebot_cmd[6:6] = ['--name', effective_name]

        try:
            proc = subprocess.run(rebot_cmd, **run_kwargs)
        finally:
            if temp_ctx is not None:
                temp_ctx.cleanup()

        if proc.returncode >= 250:
            detail = (proc.stderr or '').strip() or (proc.stdout or '').strip()
            raise RuntimeError(
                f'rebot --merge failed (exit {proc.returncode})'
                + (f': {detail}' if detail else '')
            )

        if not output_xml.exists():
            raise RuntimeError('rebot --merge produced no files. Check the input XML format.')

        stripped_history_count = 0
        if not keep_update_history:
            try:
                stripped_history_count = _strip_merge_history_messages(output_xml)
            except Exception as exc:
                raise RuntimeError(f'Failed to remove update history from merged XML: {exc}') from exc

        # ------------------------------------------------------------------ #
        # Repair missing suite-level timing then re-save the merged XML       #
        # ------------------------------------------------------------------ #
        try:
            from robot.api import ExecutionResult
        except ImportError as exc:
            raise RuntimeError(f'robotframework is not installed: {exc}') from exc

        try:
            merged = ExecutionResult(str(output_xml))
            _repair_suite_timing(merged.suite)
            merged.save(str(output_xml))
        except Exception as exc:
            raise RuntimeError(f'Failed to post-process merged XML: {exc}') from exc

        # ------------------------------------------------------------------ #
        # Re-generate log.html + report.html from the repaired XML            #
        # ------------------------------------------------------------------ #
        regen_cmd = [
            sys.executable, '-m', 'robot.rebot',
            '--outputdir', str(output_dir),
            '--log', output_log.name,
            '--report', output_report.name,
            '--output', 'NONE',
            str(output_xml),
        ]
        if effective_name:
            regen_cmd[5:5] = ['--name', effective_name]
        proc = subprocess.run(regen_cmd, **run_kwargs)
        if proc.returncode >= 250:
            detail = (proc.stderr or '').strip() or (proc.stdout or '').strip()
            raise RuntimeError(
                f'rebot failed while generating HTML (exit {proc.returncode})'
                + (f': {detail}' if detail else '')
            )

        created = [str(p) for p in [output_xml, output_log, output_report] if p.exists()]
        if not created:
            raise RuntimeError('rebot --merge produced no files. Check the input XML format.')
        return {
            'files': created,
            'stripped_history_count': stripped_history_count,
            'selective_update_count': selective_count,
        }

    # ---------------------------------------------------------------------- #
    # Combine mode (default)                                                  #
    # ---------------------------------------------------------------------- #
    try:
        from robot.api import ExecutionResult
    except ImportError as exc:
        raise RuntimeError(f'robotframework is not installed: {exc}') from exc

    # ------------------------------------------------------------------ #
    # Step 1: Merge XML files in-memory via ExecutionResult               #
    # ------------------------------------------------------------------ #
    try:
        merged = ExecutionResult(*xml_paths)
    except Exception as exc:
        raise RuntimeError(f'Failed to read XML file: {exc}') from exc

    # ------------------------------------------------------------------ #
    # Aggregate metadata + timing from every sub-suite                    #
    # (mirrors _aggregate_suite_data in refs/test_executor.py)            #
    # ------------------------------------------------------------------ #
    suites_to_process = (
        list(merged.suite.suites) if merged.suite.suites
        else [merged.suite]
    )

    # Determine suite name: use provided name, else auto-detect from first sub-suite
    if suite_name:
        merged.suite.name = suite_name
    elif suites_to_process:
        merged.suite.name = suites_to_process[0].name
    else:
        merged.suite.name = output_name or 'Merged Results'

    metadata_conflicts = _metadata_conflicts_from_suites(suites_to_process, file_names)
    if metadata_conflicts and metadata_overrides is None:
        raise MetadataConflictError(metadata_conflicts)

    combined_metadata: dict = {}
    first_metadata = dict(suites_to_process[0].metadata) if suites_to_process else {}
    for key, value in first_metadata.items():
        combined_metadata[str(key)] = value
    if metadata_overrides:
        for key, value in metadata_overrides.items():
            if value == '':
                combined_metadata.pop(str(key), None)
            else:
                combined_metadata[str(key)] = value

    all_tests: list = []

    for sub in suites_to_process:
        for test in sub.tests:
            # Append source file info to each test's doc (like refs code)
            source_info = f"Source: {sub.source}"
            test.doc = f"{test.doc}\n\n{source_info}" if test.doc else source_info
            all_tests.append(test)

    merged.suite.metadata = combined_metadata

    # Fix timing:
    #   start_time = earliest start time across all sub-suites (RF 7 datetime).
    #   end_time   = start_time + sum of each sub-suite's elapsed time, so that
    #                the displayed elapsed = actual total test-running time (not
    #                wall-clock gap when suites ran hours apart on different CI
    #                machines).  Falls back to test-level timing when the suite
    #                status element carries no start time.
    _starts: list[_dt.datetime] = []
    _total_elapsed_ms = 0
    for sub in suites_to_process:
        st = getattr(sub, 'start_time', None) or None
        if st is None:
            # Fall back: earliest test start in this sub-suite
            for t in sub.tests:
                tst = getattr(t, 'start_time', None) or None
                if tst:
                    if st is None or tst < st:
                        st = tst
        if st:
            _starts.append(st)
        _total_elapsed_ms += _suite_elapsed_ms(sub)

    if _starts:
        _root_start = min(_starts)
        merged.suite.start_time = _root_start
        if _total_elapsed_ms > 0:
            merged.suite.end_time = (
                _root_start + _dt.timedelta(milliseconds=_total_elapsed_ms)
            )

    if flatten:
        # Move all tests to root level, drop nested sub-suites
        all_tests.sort(key=lambda t: (t.starttime or ''))
        merged.suite.tests = all_tests
        merged.suite.suites = []

    try:
        merged.save(str(output_xml))
    except Exception as exc:
        raise RuntimeError(f'Failed to save merged XML: {exc}') from exc

    if not output_xml.exists():
        raise RuntimeError('Failed to create merged XML file.')

    # ------------------------------------------------------------------ #
    # Step 2: Generate log.html + report.html via rebot subprocess        #
    # ------------------------------------------------------------------ #
    effective_name = merged.suite.name  # already resolved above
    rebot_cmd = [
        sys.executable, '-m', 'robot.rebot',
        '--outputdir', str(output_dir),
        '--name', effective_name,
        '--log', output_log.name,
        '--report', output_report.name,
        '--output', 'NONE',   # keep our already-saved merged XML intact
        str(output_xml),
    ]

    proc = subprocess.run(rebot_cmd, **run_kwargs)

    # rebot exit codes: 0-249 = number of failing tests (normal),
    # 250 = timeout, 251 = invalid data, 252 = invalid arguments
    if proc.returncode >= 250:
        detail = (proc.stderr or '').strip() or (proc.stdout or '').strip()
        raise RuntimeError(
            f'rebot failed (exit {proc.returncode})'
            + (f': {detail}' if detail else '')
        )

    created = [str(p) for p in [output_xml, output_log, output_report] if p.exists()]

    if not created:
        raise RuntimeError('rebot produced no files. Check the input XML format.')

    return {'files': created}
