"""
Statistics – parse a Robot Framework file and extract structured data.
"""
import os
import tempfile
from pathlib import Path


def analyze_robot_file(content: str, filename: str = 'test.robot') -> dict:
    """Parse *content* (raw text) of a .robot/.resource file and return a dict
    with sections: test_cases, keywords, settings, variables, summary."""

    try:
        from robot.api import get_model
    except ImportError:
        raise RuntimeError(
            'robotframework chưa được cài đặt. Chạy: pip install robotframework'
        )

    suffix = Path(filename).suffix
    if suffix not in ('.robot', '.resource', '.txt', '.tsv'):
        suffix = '.robot'

    # Normalise line endings BEFORE writing so Windows text-mode does not
    # double the \r in CRLF files (which would produce \r\r\n).
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    with tempfile.NamedTemporaryFile(
        mode='w', suffix=suffix, delete=False, encoding='utf-8',
        newline='\n'    # do NOT let Python add \r on Windows
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        model = get_model(tmp_path)
    except Exception as exc:
        os.unlink(tmp_path)
        raise RuntimeError(f'Không thể parse file: {exc}')

    result: dict = {
        'test_cases': [],
        'keywords': [],
        'settings': {
            'libraries': [],
            'resources': [],
            'variables_files': [],
            'suite_setup': None,
            'suite_teardown': None,
            'test_setup': None,
            'test_teardown': None,
            'test_tags': [],
            'metadata': [],
        },
        'variables': [],
        'summary': {
            'total_test_cases': 0,
            'total_keywords': 0,
            'total_variables': 0,
            'total_lines': len(content.splitlines()),
            'filename': filename,
        },
        'raw_content': content,
    }

    try:
        for section in model.sections:
            stype = type(section).__name__

            if stype == 'TestCaseSection':
                for item in section.body:
                    if type(item).__name__ == 'TestCase':
                        result['test_cases'].append(_parse_test(item))

            elif stype == 'KeywordSection':
                for item in section.body:
                    if type(item).__name__ == 'Keyword':
                        result['keywords'].append(_parse_keyword(item))

            elif stype == 'SettingSection':
                for stmt in section.body:
                    _parse_setting(stmt, result['settings'])

            elif stype == 'VariableSection':
                for item in section.body:
                    itype = type(item).__name__
                    if itype == 'Variable':
                        val = ''
                        if hasattr(item, 'value'):
                            raw = item.value
                            val = '    '.join(str(v) for v in raw) if raw else ''
                        # RF7: name may come from get_value() or direct .name
                        var_name = ''
                        if hasattr(item, 'name') and item.name:
                            var_name = item.name
                        elif hasattr(item, 'get_value'):
                            try:
                                var_name = item.get_value('VARIABLE', default='')
                            except Exception:
                                pass
                        result['variables'].append({
                            'name': var_name,
                            'value': val,
                            'lineno': item.lineno,
                        })
    finally:
        os.unlink(tmp_path)

    result['summary']['total_test_cases'] = len(result['test_cases'])
    result['summary']['total_keywords'] = len(result['keywords'])
    result['summary']['total_variables'] = len(result['variables'])
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_test(tc) -> dict:
    info = {
        'name': tc.name,
        'lineno': tc.lineno,
        'doc': '',
        'tags': [],
        'setup': None,
        'teardown': None,
        'template': None,
        'steps': [],
        'step_count': 0,
    }
    for stmt in tc.body:
        stype = type(stmt).__name__
        if stype == 'Documentation':
            info['doc'] = _get_value(stmt)
        elif stype == 'Tags':
            info['tags'] = _get_values(stmt)
        elif stype == 'Setup':
            info['setup'] = _kw_name(stmt)
        elif stype == 'Teardown':
            info['teardown'] = _kw_name(stmt)
        elif stype == 'Template':
            info['template'] = _get_value(stmt)
        elif stype == 'KeywordCall':
            kw_name = _kw_name(stmt)
            info['steps'].append({
                'name': kw_name,
                'args': list(getattr(stmt, 'args', [])),
                'lineno': stmt.lineno,
            })
        elif stype == 'For':
            info['steps'].append({'name': f'FOR loop (line {stmt.lineno})', 'args': [], 'lineno': stmt.lineno})
        elif stype == 'If':
            info['steps'].append({'name': f'IF block (line {stmt.lineno})', 'args': [], 'lineno': stmt.lineno})
        elif stype == 'While':
            info['steps'].append({'name': f'WHILE loop (line {stmt.lineno})', 'args': [], 'lineno': stmt.lineno})
        elif stype == 'TryExcept':
            info['steps'].append({'name': f'TRY/EXCEPT (line {stmt.lineno})', 'args': [], 'lineno': stmt.lineno})
    info['step_count'] = len(info['steps'])
    return info


def _parse_keyword(kw) -> dict:
    info = {
        'name': kw.name,
        'lineno': kw.lineno,
        'doc': '',
        'arguments': [],
        'return_type': None,
        'setup': None,
        'teardown': None,
        'tags': [],
        'steps': [],
        'step_count': 0,
    }
    for stmt in kw.body:
        stype = type(stmt).__name__
        if stype == 'Documentation':
            info['doc'] = _get_value(stmt)
        elif stype == 'Arguments':
            info['arguments'] = _get_values(stmt)
        elif stype in ('Return', 'ReturnStatement', 'ReturnSetting'):
            vals = _get_values(stmt)
            info['return_type'] = ', '.join(vals) if vals else ''
        elif stype == 'Setup':
            info['setup'] = _kw_name(stmt)
        elif stype == 'Teardown':
            info['teardown'] = _kw_name(stmt)
        elif stype == 'Tags':
            info['tags'] = _get_values(stmt)
        elif stype == 'KeywordCall':
            kw_name = _kw_name(stmt)
            info['steps'].append({
                'name': kw_name,
                'args': list(getattr(stmt, 'args', [])),
                'lineno': stmt.lineno,
            })
    info['step_count'] = len(info['steps'])
    return info


def _parse_setting(stmt, settings: dict):
    stype = type(stmt).__name__
    if stype == 'LibraryImport':
        settings['libraries'].append({
            'name': getattr(stmt, 'name', ''),
            'args': list(getattr(stmt, 'args', [])),
            'alias': getattr(stmt, 'alias', None),
            'lineno': stmt.lineno,
        })
    elif stype == 'ResourceImport':
        settings['resources'].append({
            'name': getattr(stmt, 'name', ''),
            'lineno': stmt.lineno,
        })
    elif stype == 'VariablesImport':
        settings['variables_files'].append({
            'name': getattr(stmt, 'name', ''),
            'args': list(getattr(stmt, 'args', [])),
            'lineno': stmt.lineno,
        })
    elif stype == 'SuiteSetup':
        settings['suite_setup'] = _kw_name(stmt)
    elif stype == 'SuiteTeardown':
        settings['suite_teardown'] = _kw_name(stmt)
    elif stype == 'TestSetup':
        settings['test_setup'] = _kw_name(stmt)
    elif stype == 'TestTeardown':
        settings['test_teardown'] = _kw_name(stmt)
    elif stype in ('TestTags', 'DefaultTags', 'ForceTags'):
        settings['test_tags'] = _get_values(stmt)
    elif stype == 'Metadata':
        settings['metadata'].append({
            'name': getattr(stmt, 'name', ''),
            'value': _get_value(stmt),
            'lineno': stmt.lineno,
        })


def _kw_name(stmt) -> str:
    """Get the keyword name from a Setup/Teardown/KeywordCall node (RF-version-safe)."""
    return (getattr(stmt, 'name', None) or getattr(stmt, 'keyword', '') or '')


def _get_value(stmt) -> str:
    if hasattr(stmt, 'value'):
        return str(stmt.value)
    return ''


def _get_values(stmt) -> list:
    if hasattr(stmt, 'values'):
        return list(stmt.values)
    return []
