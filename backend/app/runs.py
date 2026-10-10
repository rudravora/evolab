"""Run state machine (ARCHITECTURE section 3.4)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .errors import ApiError
from .events import emit
from .ids import now_iso
from .models import Run

TRANSITIONS: dict[str, set[str]] = {
    "planning": {"awaiting_approval", "running", "failed", "cancelled"},
    "awaiting_approval": {"planning", "running", "failed", "cancelled"},
    "running": {"paused", "done", "failed", "cancelled"},
    "paused": {"running", "cancelled"},
    "done": set(), "failed": set(), "cancelled": set(),
}
TERMINAL = {"done", "failed", "cancelled"}


def set_status(db: Session, run: Run, status: str, actor: str = "orchestrator") -> None:
    if status not in TRANSITIONS[run.status]:
        raise ApiError(409, "invalid_state", f"Run cannot go from {run.status} to {status}")
    run.status = status
    if status in TERMINAL:
        run.ended_at = now_iso()
    emit(db, run.id, actor, "run.status", {"status": status})
