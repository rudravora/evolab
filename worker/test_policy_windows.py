"""Table-driven tests for policy.check_windows_path_safety, using
PureWindowsPath/ntpath semantics so every case runs on every OS (no real
Windows filesystem needed for the string-level rules). A few cases that
genuinely need Windows's own filesystem/OS behaviour (not just path string
shape) are marked and skipped elsewhere; see the final report for exactly
which ones and why.

Run: python worker/test_policy_windows.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import policy  # noqa: E402

FAILURES: list[str] = []
SKIPPED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


# (label, path, should_be_rejected)
CASES = [
    # --- drive letters ---
    ("drive letter backslash", "C:\\Users\\x", True),
    ("drive letter forward slash", "C:/Users/x", True),
    ("drive letter no separator", "C:x", True),
    ("drive letter lowercase", "c:\\windows", True),
    ("drive letter D", "D:\\data", True),

    # --- UNC paths ---
    ("UNC backslash", "\\\\server\\share\\x", True),
    ("UNC forward slash", "//server/share/x", True),
    ("UNC with deep path", "\\\\server\\share\\a\\b\\c", True),

    # --- reserved device names, bare ---
    ("CON bare", "CON", True),
    ("con lowercase bare", "con", True),
    ("PRN bare", "PRN", True),
    ("AUX bare", "AUX", True),
    ("NUL bare", "NUL", True),
    ("COM1 bare", "COM1", True),
    ("COM9 bare", "COM9", True),
    ("LPT1 bare", "LPT1", True),
    ("LPT9 bare", "LPT9", True),
    ("COM0 is not reserved (no such device)", "COM0", False),
    ("COM10 is not reserved (only 1-9)", "COM10", False),

    # --- reserved device names, in a path segment, with/without extension ---
    ("CON in subpath", "code\\CON", True),
    ("con.txt in subpath", "code\\con.txt", True),
    ("CON.TXT uppercase ext", "code\\CON.TXT", True),
    ("nul.log", "code\\nul.log", True),
    ("aux.config", "data\\aux.config", True),
    ("prn mid-path", "code\\PRN\\sub", True),
    ("lpt3.dat", "out\\lpt3.dat", True),

    # --- reserved names that are substrings but not exact segment matches ---
    ("constants.py is not CON", "code\\constants.py", False),
    ("auxiliary.py is not AUX", "code\\auxiliary.py", False),
    ("nullable.py is not NUL", "code\\nullable.py", False),
    ("prints.py is not PRN", "code\\prints.py", False),

    # --- trailing dot/space in a segment ---
    ("trailing dot on filename", "code\\file.txt.", True),
    ("trailing space on filename", "code\\file.txt ", True),
    ("trailing dot on directory segment", "code.\\file.txt", True),
    ("trailing space on directory segment", "code \\file.txt", True),
    ("no trailing dot/space is fine", "code\\file.txt", False),
    ("dot in the middle is fine", "code\\file.v2.txt", False),

    # --- "." and ".." must not be flagged by the trailing-dot rule ---
    ("single dot segment is navigation, not a violation here", "code\\.\\file.txt", False),
    ("dotdot segment is navigation, not a violation here", "code\\..\\file.txt", False),
    ("dotdot forward slash", "code/../file.txt", False),

    # --- alternate data streams ---
    ("ADS colon mid-segment", "code\\file:stream", True),
    ("ADS colon with type", "code\\file.txt:$DATA", True),
    ("ADS on directory segment", "code:stream\\file.txt", True),

    # --- ordinary, safe paths ---
    ("simple relative path", "code", False),
    ("nested relative path", "code\\sub\\dir\\file.py", False),
    ("forward-slash relative path", "code/sub/dir/file.py", False),
    ("filename with numbers", "code\\model_v2_final.pt", False),
    ("filename with spaces mid-name", "code\\my results.json", False),
    ("empty string is trivially safe (resolve_in_jail handles emptiness separately)", "", False),

    # --- case insensitivity of reserved names ---
    ("Con mixed case", "code\\Con", True),
    ("CoM1 mixed case", "code\\CoM1", True),
]


def run_cases() -> None:
    for label, path, should_be_rejected in CASES:
        try:
            policy.check_windows_path_safety(path)
            rejected = False
        except policy.JailViolation:
            rejected = True
        check(
            f"windows_path[{label}]",
            rejected == should_be_rejected,
            f"path={path!r} expected_rejected={should_be_rejected} got_rejected={rejected}",
        )


def note_untestable_cases() -> None:
    """Cases that need real Windows filesystem/OS behaviour (not just path
    string shape) to verify properly -- noted here rather than silently
    skipped, since this suite runs on macOS/Linux in CI.
    """
    SKIPPED.append(
        "ADS: actually opening 'file.txt:stream' as a real alternate data "
        "stream (vs. just rejecting the string) can only be verified on a "
        "real NTFS volume -- this suite only checks the string is rejected "
        "before any filesystem call is made."
    )
    SKIPPED.append(
        "Reserved device names: whether the OS itself treats 'CON' as a "
        "device (e.g. opening it blocks or redirects to console I/O) can "
        "only be observed on real Windows -- this suite only checks the "
        "name is rejected before any filesystem call is made."
    )
    SKIPPED.append(
        "chmod 600 being skipped on Windows (worker.save_token) and the "
        "resulting file ACLs being 'private to the user profile by "
        "default' is an OS/filesystem claim this suite cannot verify "
        "without a real Windows machine."
    )
    SKIPPED.append(
        "creationflags=CREATE_NEW_PROCESS_GROUP and the taskkill fallback "
        "path in runner.kill_process_tree can only be exercised with a real "
        "Windows subprocess.Popen call -- this suite can only confirm the "
        "attribute exists on this platform's subprocess module when it does."
    )


def main() -> None:
    run_cases()
    note_untestable_cases()

    if FAILURES:
        print(f"FAILED {len(FAILURES)} of {len(CASES)} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"ALL CHECKS PASSED ({len(CASES)} cases)")
    if SKIPPED:
        print(f"\n{len(SKIPPED)} case(s) need a real Windows machine to fully verify (see runner report):")
        for s in SKIPPED:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
