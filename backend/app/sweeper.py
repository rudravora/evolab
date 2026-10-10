"""Periodic housekeeping (plain code, no LLM): workers silent for 30 s go offline and their
jobs are requeued (max attempt 3); expired approvals count as rejected (ARCHITECTURE 3.1, 3.2, 3.6)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .events import emit
from .ids import now_iso
from .jobs import requeue_or_fail
from .models import Approval, Job, Worker

log = logging.getLogger("evolab.sweeper")
OFFLINE_AFTER = timedelta(seconds=30)
INTERVAL_S = 5.0


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def sweep(db: Session, now: datetime | None = None, services=None) -> None:
    from .routes.approvals import apply_decision

    now = now or datetime.now(timezone.utc)
    cutoff = _iso(now - OFFLINE_AFTER)
    for w in db.scalars(select(Worker).where(Worker.status == "online", Worker.last_heartbeat < cutoff)):
        w.status = "offline"
        emit(db, None, "orchestrator", "worker.status", {"worker_id": w.id, "status": "offline"})
    offline = select(Worker.id).where(Worker.status == "offline")
    for job in db.scalars(select(Job).where(Job.status.in_(("claimed", "running")), Job.worker_id.in_(offline))):
        requeue_or_fail(db, job, "worker went offline")
    for a in db.scalars(select(Approval).where(Approval.status == "pending", Approval.expires_at < _iso(now))):
        apply_decision(db, a, "expired", "system", "expired without a decision", services)
    db.commit()


async def run_forever(sessionmaker, services=None) -> None:
    def once():
        with sessionmaker() as db:
            sweep(db, services=services)

    while True:
        try:
            await asyncio.to_thread(once)
        except Exception:   # keep sweeping; one bad pass must not stop housekeeping
            log.exception("sweep failed at %s", now_iso())
        await asyncio.sleep(INTERVAL_S)
