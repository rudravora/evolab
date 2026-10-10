"""Error normalization and signature for memory_entries (AGENTS.md section 7:
"error_fix" signature = "Hash of error text with paths, hex and numbers
stripped, plus library names and versions").

Standard library only. Deterministic across platforms: the same error from
two different machines/paths/line numbers, with the same library versions,
must produce the same signature, so two runs can dedupe into one
memory_entries row instead of inserting duplicates (AGENTS.md: "dedupe by
signature and increment counters instead of inserting duplicates").

normalize_error(text) -> str
    Strips (in this order, so later patterns don't get confused by what
    earlier ones left behind):
    - file paths: POSIX (/a/b/c.py), Windows drive paths (C:\\a\\b.py or
      C:/a/b.py), and Windows UNC paths (\\\\server\\share\\a.py)
    - hex addresses (0x7f8a1c0b2e40, or a bare 16+ hex-digit run)
    - line/column references (line 42, :42:13, row 42)
    - UUIDs (8-4-4-4-12 hex, any case)
    - timestamps (ISO-ish: 2026-10-10T18:30:00, 2026-10-10 18:30:00, or a
      bare date 2026-10-10)
    - any remaining bare integer (counts, PIDs, byte offsets, etc.)
    then collapses whitespace and lowercases. The traceback's call-stack
    frame lines ("File ..., line N, in func") are collapsed to nothing
    useful once paths and numbers are stripped, which is intentional: they
    carry no information that survives across machines. The exception
    class name and the first non-blank message line (typically the final
    "ExceptionType: message" line of a Python traceback, or the first line
    of a non-traceback error string) are what remains and what the
    signature is actually keyed on.

signature(text, libs=None) -> str
    sha256 hex digest over normalize_error(text) plus a sorted, deterministic
    rendering of `libs` (a dict of {library_name: version} or an iterable of
    "name==version" strings) appended -- so the same error under a different
    library version produces a different signature, per the spec ("plus
    library names and versions").
"""
from __future__ import annotations

import hashlib
import re

# Order matters: paths before hex/numbers (a path can contain digit runs
# that would otherwise look like "a number" and get stripped as one, which
# is fine either way here, but paths are matched first for clarity and to
# strip the whole path including its drive letter/slashes in one pattern).

_WINDOWS_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\\\\\)[^\s:\"']*[\\/][^\s:\"']+"
)
_POSIX_PATH_RE = re.compile(r"(?<![\w.])/(?:[\w.\-]+/)+[\w.\-]+")
_HEX_ADDRESS_RE = re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]{16,}\b")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_ISO_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_BARE_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_LINE_COL_RE = re.compile(
    r"\b(?:line|row|col|column)\s+\d+\b|:\d+:\d+\b", re.IGNORECASE
)
_TRACEBACK_FRAME_RE = re.compile(r'^\s*File\s+"[^"]*",\s*line\s+\d+.*$', re.MULTILINE)
_BARE_NUMBER_RE = re.compile(r"\b\d+\b")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_error(text: str) -> str:
    if not text:
        return ""

    normalized = text

    # Traceback frame lines carry only path+line info once stripped; drop
    # the whole line rather than leave a ragged "File , line , in" behind.
    normalized = _TRACEBACK_FRAME_RE.sub(" ", normalized)

    normalized = _WINDOWS_PATH_RE.sub(" ", normalized)
    normalized = _POSIX_PATH_RE.sub(" ", normalized)
    normalized = _UUID_RE.sub(" ", normalized)
    normalized = _ISO_TIMESTAMP_RE.sub(" ", normalized)
    normalized = _BARE_DATE_RE.sub(" ", normalized)
    normalized = _HEX_ADDRESS_RE.sub(" ", normalized)
    normalized = _LINE_COL_RE.sub(" ", normalized)
    normalized = _BARE_NUMBER_RE.sub(" ", normalized)

    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized.lower()


def _normalize_libs(libs) -> list[str]:
    if not libs:
        return []
    if isinstance(libs, dict):
        pairs = [f"{name}=={version}" for name, version in libs.items()]
    else:
        pairs = [str(item) for item in libs]
    return sorted(p.lower() for p in pairs)


def signature(text: str, libs=None) -> str:
    normalized_text = normalize_error(text)
    normalized_libs = _normalize_libs(libs)
    payload = normalized_text + "|" + ",".join(normalized_libs)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
