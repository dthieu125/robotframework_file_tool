#!/usr/bin/env python3
"""
rf_merge.py — Standalone CLI tool to merge Robot Framework output.xml files.

Includes automatic deduplication: files with the same name AND identical
content are merged only once.  Files with the same name but different
content are kept and renamed automatically (e.g. output.xml, output_2.xml).

Requirements:
    pip install robotframework

         Flag           |         Description
==============================================================================
-o DIR / --output-dir   | Output directory (default: ./merged_results/)
------------------------------------------------------------------------------
-n NAME / --name        | Suite name and file prefix (default: merged)
------------------------------------------------------------------------------
--flatten               | Flatten all test cases to a single level
------------------------------------------------------------------------------
--update                | Update mode: tests from later files replace tests
                        | with the same name in earlier files.  Use this to
                        | fold a re-run's PASS result back into an old report.
------------------------------------------------------------------------------
--xml-only              | Only produce merged output.xml, skip HTML generation
------------------------------------------------------------------------------
--no-dedup              | Disable automatic deduplication
------------------------------------------------------------------------------

Usage:
    python rf_merge.py file1.xml file2.xml [file3.xml ...]
    python rf_merge.py *.xml
    python rf_merge.py -o results -n my_report --flatten file1.xml file2.xml

Examples:
    # Basic merge (output goes to ./merged_results/)
    python rf_merge.py run1/output.xml run2/output.xml

    # Custom output directory and name
    python rf_merge.py -o reports -n sprint42 run1/output.xml run2/output.xml

    # Flatten all test cases to a single level
    python rf_merge.py --flatten *.xml

    # Skip HTML generation (only produce merged output.xml)
    python rf_merge.py --xml-only run1/output.xml run2/output.xml

    # Update mode: replace old FAIL results with new PASS results
    python rf_merge.py --update old_results.xml new_rerun.xml
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import subprocess
import sys
import xml.etree.ElementTree as _ET
from pathlib import Path


# ---------------------------------------------------------------------------
# Timing helpers – RF 6 (string timestamps) / RF 7 (datetime objects) compat
# ---------------------------------------------------------------------------

def _suite_elapsed_ms(suite) -> int:
    """Return elapsed time of *suite* in milliseconds (RF 6/7 compatible)."""
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
            fmt = '%Y%m%d %H:%M:%S.%f'
            diff = _dt.datetime.strptime(e, fmt) - _dt.datetime.strptime(s, fmt)
            return max(0, int(diff.total_seconds() * 1000))
        except Exception:
            pass
    return 0


def _advance_timestamp(ts, ms: int):
    """Return *ts* advanced by *ms* milliseconds (RF 6 string or RF 7 datetime)."""
    delta = _dt.timedelta(milliseconds=ms)
    if isinstance(ts, _dt.datetime):
        return ts + delta
    fmt = '%Y%m%d %H:%M:%S.%f'
    end = _dt.datetime.strptime(ts, fmt) + delta
    return end.strftime('%Y%m%d %H:%M:%S.') + f'{end.microsecond // 1000:03d}'


def _repair_suite_timing(suite) -> None:
    """Recompute missing ``start_time`` / ``end_time`` on *suite* and descendants.

    ``rebot --merge`` (used by Update / Replace mode) sometimes drops the
    suite-level ``start`` attribute when results from later files override
    earlier ones — the merged report then shows the suite Start Time / End
    Time as ``N/A``.  Walk the result tree bottom-up and fill in the missing
    timestamps from the actual tests / sub-suites contained in each suite.
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


def deduplicate_files(xml_paths: list[Path]) -> tuple[list[Path], list[str]]:
    """Remove files that have the same name AND identical content.

    Returns (unique_paths, skipped_messages).
    For same-name-different-content files, copies are written to a
    temp location with disambiguated names.
    """
    entries: list[tuple[str, bytes, Path]] = []
    for p in xml_paths:
        raw = p.read_bytes()
        entries.append((p.name, raw, p))

    seen: dict[str, list[Path]] = {}
    unique: list[tuple[str, bytes, Path]] = []
    skipped: list[str] = []

    for name, content, path in entries:
        key = f"{name}::{hashlib.sha256(content).hexdigest()}"
        if key in seen:
            skipped.append(f"  Skipped duplicate: {path} (identical to {seen[key][0]})")
            seen[key].append(path)
        else:
            seen[key] = [path]
            unique.append((name, content, path))

    unique_paths = [path for _, _, path in unique]
    return unique_paths, skipped


def _detect_suite_names(xml_paths: list[str]) -> list[str]:
    """Return the top-level suite name from each XML file (empty string if unreadable)."""
    names: list[str] = []
    for path in xml_paths:
        try:
            root = _ET.parse(path).getroot()
            suite = root if root.tag == 'suite' else root.find('suite')
            names.append(suite.get('name', '') if suite is not None else '')
        except Exception:
            names.append('')
    return names


def merge_xml_reports(
    xml_paths: list[str],
    output_dir: Path,
    output_name: str = 'merged',
    flatten: bool = False,
    xml_only: bool = False,
    update_mode: bool = False,
    suite_name: str | None = None,
) -> list[Path]:
    """Merge Robot Framework output XML files and optionally generate HTML.

    When update_mode is True, tests from later files replace same-named tests
    in earlier files (uses rebot --merge).  Useful for folding re-run PASS
    results back into an existing report.
    """
    output_xml = output_dir / f'{output_name}_output.xml'
    output_log = output_dir / f'{output_name}_log.html'
    output_report = output_dir / f'{output_name}_report.html'

    run_kwargs: dict = dict(
        capture_output=True, text=True,
        encoding='utf-8', errors='replace',
    )
    if sys.platform == 'win32':
        run_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

    if update_mode:
        # Use rebot --merge: later files override earlier files by test name.
        #
        # rebot --merge often drops the suite-level ``start`` attribute when
        # tests from later files replace tests in earlier files, which makes
        # the merged report display Start Time / End Time as N/A.  We work
        # around that by:
        #   1. running rebot --merge to produce only the merged XML
        #   2. patching the merged XML so every suite has a start_time /
        #      end_time computed from its tests / sub-suites
        #   3. running rebot a second time on the repaired XML to generate
        #      log.html and report.html (unless --xml-only was requested).
        effective_name = suite_name or output_name
        rebot_cmd = [
            sys.executable, '-m', 'robot.rebot',
            '--merge',
            '--outputdir', str(output_dir),
            '--name', effective_name,
            '--output', output_xml.name,
            '--log', 'NONE',
            '--report', 'NONE',
        ]
        rebot_cmd += xml_paths

        proc = subprocess.run(rebot_cmd, **run_kwargs)
        if proc.returncode >= 250:
            detail = (proc.stderr or '').strip() or (proc.stdout or '').strip()
            print(f"Warning: rebot --merge failed (exit {proc.returncode})", file=sys.stderr)
            if detail:
                print(f"  {detail}", file=sys.stderr)

        created: list[Path] = []

        if output_xml.exists():
            try:
                from robot.api import ExecutionResult
                merged = ExecutionResult(str(output_xml))
                _repair_suite_timing(merged.suite)
                merged.save(str(output_xml))
            except ImportError:
                print("Error: robotframework is not installed.", file=sys.stderr)
                print("  Install it with:  pip install robotframework", file=sys.stderr)
                sys.exit(1)
            except Exception as exc:
                print(f"Warning: failed to repair merged XML timing: {exc}",
                      file=sys.stderr)

            created.append(output_xml)

            if not xml_only:
                regen_cmd = [
                    sys.executable, '-m', 'robot.rebot',
                    '--outputdir', str(output_dir),
                    '--name', effective_name,
                    '--log', output_log.name,
                    '--report', output_report.name,
                    '--output', 'NONE',
                    str(output_xml),
                ]
                proc = subprocess.run(regen_cmd, **run_kwargs)
                if proc.returncode >= 250:
                    detail = (proc.stderr or '').strip() or (proc.stdout or '').strip()
                    print(f"Warning: rebot failed while generating HTML "
                          f"(exit {proc.returncode})", file=sys.stderr)
                    if detail:
                        print(f"  {detail}", file=sys.stderr)
                else:
                    if output_log.exists():
                        created.append(output_log)
                    if output_report.exists():
                        created.append(output_report)

        return created

    # ---------------------------------------------------------------------- #
    # Combine mode (default)                                                  #
    # ---------------------------------------------------------------------- #
    try:
        from robot.api import ExecutionResult
    except ImportError:
        print("Error: robotframework is not installed.", file=sys.stderr)
        print("  Install it with:  pip install robotframework", file=sys.stderr)
        sys.exit(1)

    merged = ExecutionResult(*xml_paths)

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
        merged.suite.name = output_name

    combined_metadata: dict = {}
    all_tests: list = []

    for sub in suites_to_process:
        for key, value in sub.metadata.items():
            if key in combined_metadata:
                existing = [v.strip() for v in str(combined_metadata[key]).split(',')]
                if str(value) not in existing:
                    combined_metadata[key] = f"{combined_metadata[key]}, {value}"
            else:
                combined_metadata[key] = value

        for test in sub.tests:
            source_info = f"Source: {sub.source}"
            test.doc = f"{test.doc}\n\n{source_info}" if test.doc else source_info
            all_tests.append(test)

    merged.suite.metadata = combined_metadata

    # Fix timing:
    #   start_time = earliest start time across all sub-suites (RF 7 datetime).
    #   end_time   = start_time + sum of each sub-suite's elapsed time, so that
    #                elapsed = actual total test-running time (not wall-clock gap
    #                when suites ran hours apart on different CI machines).
    #                Falls back to test-level start time when suite status has none.
    _starts: list[_dt.datetime] = []
    _total_elapsed_ms = 0
    for sub in suites_to_process:
        st = getattr(sub, 'start_time', None) or None
        if st is None:
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
        all_tests.sort(key=lambda t: (t.starttime or ''))
        merged.suite.tests = all_tests
        merged.suite.suites = []

    merged.save(str(output_xml))

    created = [output_xml]

    if not xml_only:
        effective_name = merged.suite.name  # already resolved above
        rebot_cmd = [
            sys.executable, '-m', 'robot.rebot',
            '--outputdir', str(output_dir),
            '--name', effective_name,
            '--log', output_log.name,
            '--report', output_report.name,
            '--output', 'NONE',
            str(output_xml),
        ]

        proc = subprocess.run(rebot_cmd, **run_kwargs)

        if proc.returncode >= 250:
            detail = (proc.stderr or '').strip() or (proc.stdout or '').strip()
            print(f"Warning: rebot failed (exit {proc.returncode})", file=sys.stderr)
            if detail:
                print(f"  {detail}", file=sys.stderr)
        else:
            if output_log.exists():
                created.append(output_log)
            if output_report.exists():
                created.append(output_report)

    return created


def main():
    parser = argparse.ArgumentParser(
        description='Merge Robot Framework output.xml files into a single report.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s run1/output.xml run2/output.xml
  %(prog)s -o results -n sprint42 *.xml
  %(prog)s --flatten --xml-only *.xml
        """,
    )
    parser.add_argument(
        'files', nargs='+', type=Path,
        help='output.xml files to merge (at least 2)',
    )
    parser.add_argument(
        '-o', '--output-dir', type=Path, default=Path('merged_results'),
        help='output directory (default: ./merged_results/)',
    )
    parser.add_argument(
        '-n', '--name', default='merged',
        help='file prefix for the generated output files (default: merged)',
    )
    parser.add_argument(
        '--suite-name', default=None, metavar='NAME',
        help=(
            'top-level suite name in the merged report '
            '(default: auto-detected from the first input file)'
        ),
    )
    parser.add_argument(
        '--flatten', action='store_true',
        help='flatten all test cases to a single suite level',
    )
    parser.add_argument(
        '--xml-only', action='store_true',
        help='only produce the merged output.xml, skip HTML generation',
    )
    parser.add_argument(
        '--update', action='store_true',
        help=(
            'update mode: tests from later files replace same-named tests in '
            'earlier files (uses rebot --merge).  Useful for folding a re-run '
            'PASS result back into an existing report.'
        ),
    )
    parser.add_argument(
        '--no-dedup', action='store_true',
        help='disable automatic deduplication of identical files',
    )

    args = parser.parse_args()

    # --- Validate input files ---
    missing = [f for f in args.files if not f.exists()]
    if missing:
        for f in missing:
            print(f"Error: file not found: {f}", file=sys.stderr)
        sys.exit(1)

    non_xml = [f for f in args.files if f.suffix.lower() != '.xml']
    if non_xml:
        for f in non_xml:
            print(f"Warning: not an .xml file, skipping: {f}", file=sys.stderr)
        args.files = [f for f in args.files if f.suffix.lower() == '.xml']

    if len(args.files) < 2:
        print("Error: at least 2 .xml files are required.", file=sys.stderr)
        sys.exit(1)

    # --- Deduplicate ---
    if not args.no_dedup:
        unique_paths, skipped = deduplicate_files(args.files)
        if skipped:
            print(f"Deduplication: {len(skipped)} identical file(s) removed:")
            for msg in skipped:
                print(msg)
            print()

        if len(unique_paths) < 2:
            print("Error: all input files are identical. At least 2 files with "
                  "different content are required.", file=sys.stderr)
            sys.exit(1)

        xml_paths = [str(p) for p in unique_paths]
    else:
        xml_paths = [str(p) for p in args.files]

    # --- Create output dir ---
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # --- Resolve suite name ---
    resolved_suite_name = args.suite_name
    if not resolved_suite_name:
        detected = _detect_suite_names(xml_paths)
        unique_detected = list(dict.fromkeys(n for n in detected if n))
        if unique_detected:
            resolved_suite_name = unique_detected[0]
            if len(unique_detected) > 1:
                print(f"Multiple suite names detected: {', '.join(unique_detected)}")
                print(f"  Using: '{resolved_suite_name}'  (use --suite-name to override)")
                print()

    # --- Merge ---
    mode_label = 'update (replace by name)' if args.update else 'combine (add unique)'
    print(f"Merging {len(xml_paths)} file(s)  [mode: {mode_label}]...")
    for p in xml_paths:
        print(f"  + {p}")
    if resolved_suite_name:
        print(f"  Suite name: {resolved_suite_name}")
    print()

    try:
        created = merge_xml_reports(
            xml_paths,
            args.output_dir,
            args.name,
            args.flatten,
            args.xml_only,
            args.update,
            resolved_suite_name,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Summary ---
    print("Done! Generated files:")
    for f in created:
        size_kb = f.stat().st_size / 1024
        print(f"  {f}  ({size_kb:.1f} KB)")
    print()
    print(f"Output directory: {args.output_dir.resolve()}")


if __name__ == '__main__':
    main()
