"""Append-only event log (ARCHITECTURE principle 5). Every state change calls emit();
the SSE stream reads the events table, so the dashboard is a view over it."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Event


def emit(db: Session, run_id: str | None, actor: str, type_: str, payload: dict) -> Event:
    event = Event(run_id=run_id, actor=actor, type=type_, payload_json=payload)
    db.add(event)
    return event
