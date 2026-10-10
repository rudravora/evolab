"""Run events: raw timeline and the SSE stream (API.md sections 5 and 7).

The stream reads the append-only events table (polling every 0.5 s), so it is
restart-safe and resumes from `Last-Event-ID`. Global events (worker.status,
run_id null) are included in every run's stream. The stream closes after a
run reaches a terminal status and every event has been sent.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..models import Event, Run
from ..runs import TERMINAL
from ..security import current_user

router = APIRouter(tags=["events"], dependencies=[Depends(current_user)])
POLL_S = 0.5
KEEPALIVE_S = 15.0
BATCH = 500


class EventOut(BaseModel):
    id: int
    run_id: str | None
    ts: str
    actor: str
    type: str
    payload: dict | list | None


def _query(run_id: str, after_id: int, limit: int):
    return (select(Event).where(or_(Event.run_id == run_id, Event.run_id.is_(None)), Event.id > after_id)
            .order_by(Event.id).limit(limit))


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
def list_events(run_id: str, after_id: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000),
                db: Session = Depends(get_db)) -> list[EventOut]:
    if db.get(Run, run_id) is None:
        raise ApiError(404, "not_found", "Run not found")
    return [EventOut(id=e.id, run_id=e.run_id, ts=e.ts, actor=e.actor, type=e.type, payload=e.payload_json)
            for e in db.scalars(_query(run_id, after_id, limit))]


def _fetch(sessionmaker, run_id: str, after_id: int):
    with sessionmaker() as db:
        events = [(e.id, e.type, e.payload_json) for e in db.scalars(_query(run_id, after_id, BATCH))]
        run = db.get(Run, run_id)
        return events, (run.status if run else None)


@router.get("/runs/{run_id}/stream", response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}}}})
async def stream(run_id: str, request: Request, last_event_id: str | None = Header(default=None),
                 after_id: int = Query(default=0, ge=0)):
    sessionmaker = request.app.state.db.sessionmaker
    _, status = await asyncio.to_thread(_fetch, sessionmaker, run_id, 0)
    if status is None:
        raise ApiError(404, "not_found", "Run not found")
    try:
        cursor = int(last_event_id) if last_event_id else after_id
    except ValueError:
        cursor = after_id

    async def gen():
        nonlocal cursor
        idle = 0.0
        while True:
            events, run_status = await asyncio.to_thread(_fetch, sessionmaker, run_id, cursor)
            for eid, etype, payload in events:
                cursor = eid
                yield f"id: {eid}\nevent: {etype}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
            if events:
                idle = 0.0
                continue
            if run_status in TERMINAL:
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(POLL_S)
            idle += POLL_S
            if idle >= KEEPALIVE_S:
                idle = 0.0
                yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
