"""Tests for shared/signature.py: normalize_error and signature determinism
across platforms/paths/timestamps, and sensitivity to real differences
(different errors, different library versions).

Run: python -m shared.tests.test_signature
"""
import sys

from shared.signature import normalize_error, signature

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


TRACEBACK_POSIX = """Traceback (most recent call last):
  File "/Users/alice/project/src/foo.py", line 42, in main
    result = compute(x)
  File "/Users/alice/project/src/compute.py", line 17, in compute
    return 1 / x
ZeroDivisionError: division by zero
"""

TRACEBACK_WINDOWS = """Traceback (most recent call last):
  File "C:\\Users\\bob\\project\\src\\foo.py", line 99, in main
    result = compute(x)
  File "C:\\Users\\bob\\project\\src\\compute.py", line 5, in compute
    return 1 / x
ZeroDivisionError: division by zero
"""

TRACEBACK_WINDOWS_FORWARD_SLASH = """Traceback (most recent call last):
  File "C:/Users/carol/other_project/src/foo.py", line 7, in main
    result = compute(x)
  File "C:/Users/carol/other_project/src/compute.py", line 123, in compute
    return 1 / x
ZeroDivisionError: division by zero
"""


# ---------------------------------------------------------------------------
# 1. Same error, two machines/paths -> same signature (POSIX vs Windows)
# ---------------------------------------------------------------------------

def test_same_error_posix_vs_windows_path_same_signature() -> None:
    sig1 = signature(TRACEBACK_POSIX, {"numpy": "1.26.4"})
    sig2 = signature(TRACEBACK_WINDOWS, {"numpy": "1.26.4"})
    check("same_error.posix_vs_windows_backslash", sig1 == sig2, (sig1, sig2))


def test_same_error_windows_forward_slash_path_same_signature() -> None:
    sig1 = signature(TRACEBACK_POSIX, {"numpy": "1.26.4"})
    sig3 = signature(TRACEBACK_WINDOWS_FORWARD_SLASH, {"numpy": "1.26.4"})
    check("same_error.posix_vs_windows_forward_slash", sig1 == sig3, (sig1, sig3))


# ---------------------------------------------------------------------------
# 2. Different line numbers, same machine style -> same signature
# ---------------------------------------------------------------------------

def test_different_line_numbers_same_signature() -> None:
    err_a = 'File "/a/b/c.py", line 10, in f\nValueError: bad input'
    err_b = 'File "/a/b/c.py", line 9999, in f\nValueError: bad input'
    check("line_numbers.irrelevant", signature(err_a) == signature(err_b), (err_a, err_b))


# ---------------------------------------------------------------------------
# 3. Different errors -> different signatures
# ---------------------------------------------------------------------------

def test_different_errors_different_signatures() -> None:
    sig_a = signature("ValueError: invalid literal for int() with base 10")
    sig_b = signature("TypeError: unsupported operand type")
    check("different_errors.differ", sig_a != sig_b, (sig_a, sig_b))


def test_different_exception_classes_same_message_differ() -> None:
    sig_a = signature("ValueError: something went wrong")
    sig_b = signature("TypeError: something went wrong")
    check("different_exception_classes.differ", sig_a != sig_b, (sig_a, sig_b))


# ---------------------------------------------------------------------------
# 4. Library version changes the signature
# ---------------------------------------------------------------------------

def test_library_version_change_changes_signature() -> None:
    err = "ImportError: cannot import name 'x' from 'numpy'"
    sig_a = signature(err, {"numpy": "1.26.4"})
    sig_b = signature(err, {"numpy": "1.27.0"})
    check("library_version.changes_signature", sig_a != sig_b, (sig_a, sig_b))


def test_library_set_change_changes_signature() -> None:
    err = "ImportError: cannot import name 'x' from 'numpy'"
    sig_a = signature(err, {"numpy": "1.26.4"})
    sig_b = signature(err, {"numpy": "1.26.4", "scipy": "1.11.0"})
    check("library_set.changes_signature", sig_a != sig_b, (sig_a, sig_b))


def test_library_order_does_not_change_signature() -> None:
    err = "ImportError: cannot import name 'x'"
    sig_a = signature(err, {"numpy": "1.26.4", "scipy": "1.11.0"})
    sig_b = signature(err, {"scipy": "1.11.0", "numpy": "1.26.4"})
    check("library_order.irrelevant", sig_a == sig_b, (sig_a, sig_b))


def test_library_as_list_of_strings() -> None:
    err = "ImportError: cannot import name 'x'"
    sig_dict = signature(err, {"numpy": "1.26.4"})
    sig_list = signature(err, ["numpy==1.26.4"])
    check("library_list_form.matches_dict_form", sig_dict == sig_list, (sig_dict, sig_list))


# ---------------------------------------------------------------------------
# 5. Multi-frame traceback normalization keeps the exception class + message
# ---------------------------------------------------------------------------

def test_multi_frame_traceback_normalized_keeps_exception_info() -> None:
    normalized = normalize_error(TRACEBACK_POSIX)
    check("multi_frame.keeps_exception_class", "zerodivisionerror" in normalized, normalized)
    check("multi_frame.keeps_message", "division by zero" in normalized, normalized)
    check("multi_frame.no_path_remains", "/users/" not in normalized and "foo.py" not in normalized, normalized)
    check("multi_frame.no_line_number_remains", "42" not in normalized and "17" not in normalized, normalized)


def test_deeper_multi_frame_traceback() -> None:
    deep = """Traceback (most recent call last):
  File "/a/one.py", line 1, in <module>
    run()
  File "/a/two.py", line 22, in run
    step()
  File "/a/three.py", line 333, in step
    raise RuntimeError("pipeline stalled")
RuntimeError: pipeline stalled
"""
    normalized = normalize_error(deep)
    check("deep_frames.keeps_exception", "runtimeerror" in normalized, normalized)
    check("deep_frames.keeps_message", "pipeline stalled" in normalized, normalized)
    check("deep_frames.no_paths", "/a/" not in normalized, normalized)


# ---------------------------------------------------------------------------
# 6. Hex addresses, UUIDs, timestamps stripped
# ---------------------------------------------------------------------------

def test_hex_address_stripped() -> None:
    err = "Segfault at address 0x7f8a1c0b2e40 in thread"
    normalized = normalize_error(err)
    check("hex_address.stripped", "0x7f8a1c0b2e40" not in normalized, normalized)
    check("hex_address.keeps_message", "segfault" in normalized and "thread" in normalized, normalized)


def test_uuid_stripped() -> None:
    err = "Request abc12345-6789-4abc-8def-0123456789ab failed"
    normalized = normalize_error(err)
    check("uuid.stripped", "abc12345" not in normalized, normalized)
    check("uuid.keeps_message", "request" in normalized and "failed" in normalized, normalized)


def test_timestamp_stripped() -> None:
    err_iso = "Error at 2026-10-10T18:30:00Z during fetch"
    err_space = "Error at 2026-10-10 18:30:00 during fetch"
    normalized_iso = normalize_error(err_iso)
    normalized_space = normalize_error(err_space)
    check("timestamp.iso_stripped", "2026" not in normalized_iso, normalized_iso)
    check("timestamp.space_stripped", "2026" not in normalized_space, normalized_space)
    check("timestamp.same_after_strip", normalized_iso == normalized_space, (normalized_iso, normalized_space))


def test_bare_date_stripped() -> None:
    err = "Last run on 2026-10-10 produced no output"
    normalized = normalize_error(err)
    check("bare_date.stripped", "2026" not in normalized, normalized)


# ---------------------------------------------------------------------------
# 7. Case and whitespace normalization
# ---------------------------------------------------------------------------

def test_case_insensitive() -> None:
    sig_a = signature("ValueError: Bad Input")
    sig_b = signature("VALUEERROR: BAD INPUT")
    check("case.insensitive", sig_a == sig_b, (sig_a, sig_b))


def test_whitespace_collapsed() -> None:
    sig_a = signature("ValueError:    bad   input\n\n\nhere")
    sig_b = signature("ValueError: bad input here")
    check("whitespace.collapsed", sig_a == sig_b, (sig_a, sig_b))


def test_empty_string() -> None:
    check("empty.normalize_returns_empty", normalize_error("") == "", normalize_error(""))
    check("empty.signature_is_deterministic", signature("") == signature(""), "signature('') should be stable")


def main() -> None:
    tests = [
        test_same_error_posix_vs_windows_path_same_signature,
        test_same_error_windows_forward_slash_path_same_signature,
        test_different_line_numbers_same_signature,
        test_different_errors_different_signatures,
        test_different_exception_classes_same_message_differ,
        test_library_version_change_changes_signature,
        test_library_set_change_changes_signature,
        test_library_order_does_not_change_signature,
        test_library_as_list_of_strings,
        test_multi_frame_traceback_normalized_keeps_exception_info,
        test_deeper_multi_frame_traceback,
        test_hex_address_stripped,
        test_uuid_stripped,
        test_timestamp_stripped,
        test_bare_date_stripped,
        test_case_insensitive,
        test_whitespace_collapsed,
        test_empty_string,
    ]
    for t in tests:
        t()

    if FAILURES:
        print(f"FAILED {len(FAILURES)} of {len(tests)} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"ALL CHECKS PASSED ({len(tests)} cases)")


if __name__ == "__main__":
    main()
