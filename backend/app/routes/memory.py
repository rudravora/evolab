"""Memory and notes (API.md section 10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..ids import new_id, now_iso
from ..models import MemoryEntry, Note, Project
from ..security import current_user

router = APIRouter(tags=["memory"], dependencies=[Depends(current_user)])


def _entry(e: MemoryEntry) -> dict:
    return {"id": e.id, "kind": e.kind, "signature": e.signature, "source": e.source, "content": e.content_json,
            "context": e.context_json, "success_count": e.success_count, "fail_count": e.fail_count,
            "last_used_at": e.last_used_at, "created_at": e.created_at, "mirrored": bool(e.supermemory_id)}


@router.get("/memory")
def list_memory(request: Request, q: str | None = None, kind: str | None = None, source: str | None = None,
                db: Session = Depends(get_db)) -> dict:
    if q:
        entries, how = request.app.state.services.librarian.search(db, q, kind=kind, limit=20)
        entries = [e for e in entries if not source or e.source == source]
        return {"retrieved_by": how, "entries": [_entry(e) for e in entries]}
    query = select(MemoryEntry).order_by(MemoryEntry.created_at.desc()).limit(200)
    if kind:
        query = query.where(MemoryEntry.kind == kind)
    if source:
        query = query.where(MemoryEntry.source == source)
    rows = list(db.scalars(query))
    return {"retrieved_by": "list", "entries": [_entry(e) for e in rows],
            "counts": {"seeded": sum(e.source == "seeded" for e in rows), "learned": sum(e.source == "learned" for e in rows)}}


@router.get("/memory/{entry_id}")
def get_memory(entry_id: str, db: Session = Depends(get_db)) -> dict:
    e = db.get(MemoryEntry, entry_id)
    if e is None:
        raise ApiError(404, "not_found", "Memory entry not found")
    return _entry(e)


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    markdown: str = Field(max_length=50_000)
    source_ref: str | None = Field(default=None, max_length=300)


def _note(n: Note) -> dict:
    return {"id": n.id, "project_id": n.project_id, "title": n.title, "markdown": n.markdown, "source_ref": n.source_ref,
            "updated_at": n.updated_at}


@router.get("/projects/{project_id}/notes")
def list_notes(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Project, project_id) is None:
        raise ApiError(404, "not_found", "Project not found")
    return [_note(n) for n in db.scalars(select(Note).where(Note.project_id == project_id).order_by(Note.updated_at.desc()))]


@router.post("/projects/{project_id}/notes", status_code=201)
def create_note(project_id: str, body: NoteIn, db: Session = Depends(get_db)) -> dict:
    if db.get(Project, project_id) is None:
        raise ApiError(404, "not_found", "Project not found")
    n = Note(id=new_id("note"), project_id=project_id, title=body.title, markdown=body.markdown, source_ref=body.source_ref)
    db.add(n)
    db.commit()
    return _note(n)


@router.put("/notes/{note_id}")
def update_note(note_id: str, body: NoteIn, db: Session = Depends(get_db)) -> dict:
    n = db.get(Note, note_id)
    if n is None:
        raise ApiError(404, "not_found", "Note not found")
    n.title, n.markdown, n.source_ref, n.updated_at = body.title, body.markdown, body.source_ref, now_iso()
    db.commit()
    return _note(n)
