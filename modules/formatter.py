"""
Name Formatter – preview and apply test-case name transformations.

Supported rules (all optional, applied in order):
  find_pattern        – regex pattern to search
  replace_pattern     – replacement template (supports \1, named groups)
  case_insensitive    – bool, use re.IGNORECASE for find/replace
  prefix              – string prepended to each name
  suffix              – string appended to each name
  case_conversion     – 'upper' | 'lower' | 'title' | 'snake' | 'screaming_snake'
  spaces_to_underscores – bool
  template            – e.g. "TC_{project}_{name}" where {name} = current name
  template_vars       – dict of extra variable values, e.g. {"project": "MYAPP"}
  numbering           – bool; if true prepend "{N:02d}_"
  numbering_start     – int (default 1)
  numbering_step      – int (default 1)
"""
import re
import os
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preview_format(content: str, rules: dict) -> dict:
    """Return a preview list of {original, new, lineno, type, unchanged}."""
    names = _extract_test_names(content)
    changes = []
    counter = int(rules.get('numbering_start', 1))
    step = int(rules.get('numbering_step', 1))

    for name, lineno in names:
        new_name = _apply_rules(name, rules, counter)
        unchanged = new_name == name
        changes.append({
            'original': name,
            'new': new_name,
            'lineno': lineno,
            'type': 'test_case',
            'unchanged': unchanged,
        })
        if not unchanged:
            counter += step

    return {
        'changes': changes,
        'total_tests': len(changes),
        'total_changes': sum(1 for c in changes if not c['unchanged']),
    }


def apply_format(content: str, rules: dict) -> str:
    """Apply formatting rules to *content* and return the modified text."""
    preview = preview_format(content, rules)

    # Build a mapping: lineno -> new_name
    line_map = {
        c['lineno']: c['new']
        for c in preview['changes']
        if not c['unchanged']
    }

    if not line_map:
        return content

    lines = content.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        lineno = idx + 1
        if lineno in line_map:
            original_name = next(
                c['original'] for c in preview['changes'] if c['lineno'] == lineno
            )
            new_name = line_map[lineno]
            lines[idx] = line.replace(original_name, new_name, 1)

    return ''.join(lines)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _extract_test_names(content: str) -> list[tuple[str, int]]:
    """Try robot.api first, fall back to regex."""
    try:
        from robot.api import get_model
        return _extract_via_api(content)
    except Exception:
        return _extract_via_regex(content)


def _extract_via_api(content: str) -> list[tuple[str, int]]:
    from robot.api import get_model
    suffix = '.robot'
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    with tempfile.NamedTemporaryFile(
        mode='w', suffix=suffix, delete=False, encoding='utf-8',
        newline='\n'
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        model = get_model(tmp_path)
        names: list[tuple[str, int]] = []
        for section in model.sections:
            if type(section).__name__ == 'TestCaseSection':
                for item in section.body:
                    if type(item).__name__ == 'TestCase':
                        names.append((item.name, item.lineno))
        return names
    finally:
        os.unlink(tmp_path)


def _extract_via_regex(content: str) -> list[tuple[str, int]]:
    """Fallback: detect test names by parsing section headers and indentation."""
    names: list[tuple[str, int]] = []
    in_tc_section = False

    for idx, line in enumerate(content.splitlines()):
        stripped = line.rstrip()
        if re.match(r'^\s*\*+\s*(Test\s*Cases?|Tasks?)\s*\**', stripped, re.I):
            in_tc_section = True
            continue
        if re.match(r'^\s*\*+\s*\w', stripped):
            in_tc_section = False
            continue

        if in_tc_section:
            # Non-indented, non-empty, non-comment line = test name
            if stripped and not stripped.startswith(' ') and not stripped.startswith('\t') and not stripped.startswith('#'):
                names.append((stripped.strip(), idx + 1))

    return names


def _apply_rules(name: str, rules: dict, counter: int = 1) -> str:
    result = name

    # 1. Regex find & replace
    fp = rules.get('find_pattern', '')
    rp = rules.get('replace_pattern')
    if fp and rp is not None:
        try:
            flags = re.IGNORECASE if rules.get('case_insensitive') else 0
            result = re.sub(fp, rp, result, flags=flags)
        except re.error:
            pass

    # 2. Prefix / suffix
    if rules.get('prefix'):
        result = str(rules['prefix']) + result
    if rules.get('suffix'):
        result = result + str(rules['suffix'])

    # 3. Case conversion
    conv = rules.get('case_conversion', '')
    if conv == 'upper':
        result = result.upper()
    elif conv == 'lower':
        result = result.lower()
    elif conv == 'title':
        result = result.title()
    elif conv == 'snake':
        result = re.sub(r'\s+', '_', result.lower())
    elif conv == 'screaming_snake':
        result = re.sub(r'\s+', '_', result.upper())

    # 4. Spaces → underscores
    if rules.get('spaces_to_underscores'):
        result = result.replace(' ', '_')

    # 5. Template substitution  e.g.  "TC_{project}_{name}"
    tmpl = rules.get('template', '')
    if tmpl:
        tvars: dict = dict(rules.get('template_vars') or {})
        tvars.setdefault('name', result)
        tvars.setdefault('NAME', result.upper())
        tvars.setdefault('N', str(counter))
        tvars.setdefault('NN', f'{counter:02d}')
        try:
            result = tmpl.format_map(_SafeDict(tvars))
        except Exception:
            pass

    # 6. Numbering prefix
    if rules.get('numbering') and not tmpl:
        step = int(rules.get('numbering_step', 1))
        result = f'{counter:02d}_{result}'

    return result.strip()


class _SafeDict(dict):
    """Return '{key}' for missing keys so partial templates don't crash."""
    def __missing__(self, key):
        return '{' + key + '}'
