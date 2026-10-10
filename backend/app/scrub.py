"""Scrub key-like strings from worker output before it is stored or streamed
(ARCHITECTURE section 6.4; the worker scrubs too, this is the second pass)."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\blsv2_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)\s*[=:]\s*\S{6,}"),
]


def scrub(text: str | None) -> str | None:
    if not text:
        return text
    for pattern in _PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: f"{m.group(1)} [REDACTED]" if m.group(1).lower() == "bearer"
                               else f"{m.group(1)}=[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text
