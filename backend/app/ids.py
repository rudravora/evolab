"""Opaque, time-ordered text IDs (`run_0192f3...`) and UTC ISO timestamps (ARCHITECTURE section 4)."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone


def new_id(prefix: str) -> str:
    """Prefix, 12 hex chars of milliseconds since epoch, 16 random hex chars."""
    return f"{prefix}_{int(time.time() * 1000):012x}{secrets.token_hex(8)}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
