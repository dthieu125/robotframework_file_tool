"""
Statistics feature – integration tests.
Covers paste (JSON) vs file-upload (multipart) with various encodings.

Usage:
    python tests/test_statistics.py
    
Server must be running on http://localhost:5000 before running these tests.
"""
import sys
import os
import json
import urllib.request
import urllib.error
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:5000"

# ---------------------------------------------------------------------------
# Sample robot file used across all scenarios
# ---------------------------------------------------------------------------
ROBOT_CONTENT_LF = """\
*** Settings ***
Library    SeleniumLibrary
Library    Collections
Resource   common.resource

*** Variables ***
${URL}      https://example.com
${BROWSER}  chrome

*** Test Cases ***
Test Login
    [Documentation]    Verify user can log in
    [Tags]    smoke    auth
    Open Browser    ${URL}    ${BROWSER}
    Input Text      id=username    admin
    Click Button    Login

Test Logout
    [Tags]    smoke    auth
    Click Button    Logout

Test Register
    [Tags]    regression
    Click Link    Register
    Input Text    id=email    user@example.com
    Click Button  Submit

Test Search
    [Tags]    regression
    Input Text    id=search    keyword
    Press Keys    id=search    ENTER

*** Keywords ***
Setup Browser
    [Arguments]    ${url}    ${browser}=chrome
    Open Browser    ${url}    ${browser}

Teardown Browser
    Close All Browsers
"""

EXPECTED = {
    "total_test_cases": 4,
    "total_keywords":   2,
    "total_variables":  2,
    "libraries":        2,
    "tc_names": ["Test Login", "Test Logout", "Test Register", "Test Search"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_json(content: str) -> dict:
    """Send content as a JSON body (simulates the 'Paste text' mode in UI)."""
    data = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/statistics",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_file(content_bytes: bytes, filename: str = "test.robot") -> dict:
    """Upload bytes as a multipart file (simulates the 'Upload file' mode in UI)."""
    boundary = "----TestBoundary987654321"
    CRLF = b"\r\n"
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    body.write(b"Content-Type: text/plain\r\n")
    body.write(CRLF)
    body.write(content_bytes)
    body.write(CRLF)
    body.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BASE_URL}/api/statistics",
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check(result: dict, label: str) -> bool:
    s = result["summary"]
    checks = {
        "total_test_cases": (s["total_test_cases"], EXPECTED["total_test_cases"]),
        "total_keywords":   (s["total_keywords"],   EXPECTED["total_keywords"]),
        "total_variables":  (s["total_variables"],  EXPECTED["total_variables"]),
        "libraries":        (len(result["settings"]["libraries"]), EXPECTED["libraries"]),
        "tc_names":         ([t["name"] for t in result["test_cases"]], EXPECTED["tc_names"]),
    }
    all_ok = True
    for key, (got, exp) in checks.items():
        ok = got == exp
        status = "[PASS]" if ok else "[FAIL]"
        print(f"    {status}  {key}: expected={exp!r}  got={got!r}")
        if not ok:
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Scenario 1 – Paste text via JSON (LF)
# Represents the user pasting content directly in the textarea.
# ---------------------------------------------------------------------------
def scenario_1_paste_json_lf():
    """Scenario 1: paste via JSON, Unix LF line endings."""
    print("\n[Scenario 1] Paste content as JSON (LF line endings)")
    result = _post_json(ROBOT_CONTENT_LF)
    return check(result, "paste/json/lf")


# ---------------------------------------------------------------------------
# Scenario 2 – Upload file: UTF-8 + LF (normal Unix file)
# ---------------------------------------------------------------------------
def scenario_2_upload_utf8_lf():
    """Scenario 2: upload file – UTF-8, LF, no BOM."""
    print("\n[Scenario 2] Upload file: UTF-8, LF, no BOM")
    raw = ROBOT_CONTENT_LF.encode("utf-8")
    result = _post_file(raw)
    return check(result, "upload/utf8/lf")


# ---------------------------------------------------------------------------
# Scenario 3 – Upload file: UTF-8 + CRLF (Windows Notepad-saved, no BOM)
# The classic Windows line-ending that triggers the double-\r bug in
# text-mode temp-file writing.
# ---------------------------------------------------------------------------
def scenario_3_upload_utf8_crlf():
    """Scenario 3: upload file – UTF-8, CRLF, no BOM (Windows file)."""
    print("\n[Scenario 3] Upload file: UTF-8, CRLF (Windows), no BOM")
    crlf_content = ROBOT_CONTENT_LF.replace("\n", "\r\n")
    raw = crlf_content.encode("utf-8")
    result = _post_file(raw)
    return check(result, "upload/utf8/crlf")


# ---------------------------------------------------------------------------
# Scenario 4 – Upload file: UTF-8 BOM + CRLF (Notepad on Windows 10/11)
# Notepad saves files with UTF-8 BOM by default. This is the most common
# real-world format for Windows users who edit robot files in Notepad.
# ---------------------------------------------------------------------------
def scenario_4_upload_bom_crlf():
    """Scenario 4: upload file – UTF-8 BOM + CRLF (Notepad on Windows)."""
    print("\n[Scenario 4] Upload file: UTF-8 BOM + CRLF (Notepad-style)")
    crlf_content = ROBOT_CONTENT_LF.replace("\n", "\r\n")
    raw = b"\xef\xbb\xbf" + crlf_content.encode("utf-8")
    result = _post_file(raw)
    return check(result, "upload/bom+crlf")


# ---------------------------------------------------------------------------
# Scenario 5 – Upload file: UTF-8 BOM + LF
# Some editors (macOS TextEdit, VS Code on Mac) save UTF-8 BOM with LF.
# ---------------------------------------------------------------------------
def scenario_5_upload_bom_lf():
    """Scenario 5: upload file – UTF-8 BOM + LF."""
    print("\n[Scenario 5] Upload file: UTF-8 BOM + LF")
    raw = b"\xef\xbb\xbf" + ROBOT_CONTENT_LF.encode("utf-8")
    result = _post_file(raw)
    return check(result, "upload/bom+lf")


# ---------------------------------------------------------------------------
# Scenario 6 – Upload file: double-CRLF (\r\r\n) edge case
# This is what text-mode writing produces when CRLF content is fed into
# Python's text-mode NamedTemporaryFile on Windows WITHOUT the fix.
# The test verifies that the fix (newline='\n') prevents this corruption.
# ---------------------------------------------------------------------------
def scenario_6_double_crlf_edge_case():
    """Scenario 6: double-CRLF edge case (\r\r\n) – the core bug scenario."""
    print("\n[Scenario 6] Upload file: double-CRLF edge case (CRLF file on Windows)")
    # Simulate a file that was already CRLF and then fed through a text-mode
    # writer without the fix – produces \r\r\n.
    # We send the raw CRLF file; the server must NOT double the \r.
    crlf_content = ROBOT_CONTENT_LF.replace("\n", "\r\n")
    raw = crlf_content.encode("utf-8")
    result = _post_file(raw)
    ok = check(result, "upload/double-crlf-edge-case")
    # Additionally verify TC count matches paste
    paste_result = _post_json(ROBOT_CONTENT_LF)
    tc_match = result["summary"]["total_test_cases"] == paste_result["summary"]["total_test_cases"]
    status = "[PASS]" if tc_match else "[FAIL]"
    print(f"    {status}  upload TC count == paste TC count: "
          f"{result['summary']['total_test_cases']} == {paste_result['summary']['total_test_cases']}")
    return ok and tc_match


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 65)
    print("  Statistics Feature - Integration Tests")
    print(f"  Server: {BASE_URL}")
    print("=" * 65)

    scenarios = [
        scenario_1_paste_json_lf,
        scenario_2_upload_utf8_lf,
        scenario_3_upload_utf8_crlf,
        scenario_4_upload_bom_crlf,
        scenario_5_upload_bom_lf,
        scenario_6_double_crlf_edge_case,
    ]

    results = []
    for fn in scenarios:
        try:
            ok = fn()
        except Exception as exc:
            print(f"  [ERROR] Exception: {exc}")
            ok = False
        results.append(ok)

    passed = sum(results)
    total  = len(results)

    print("\n" + "=" * 65)
    for i, (fn, ok) in enumerate(zip(scenarios, results)):
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}]  Scenario {i+1}: {fn.__doc__.split(':')[0].strip()}")
    print("-" * 65)
    print(f"  Total: {passed}/{total} passed")
    print("=" * 65)

    sys.exit(0 if passed == total else 1)
