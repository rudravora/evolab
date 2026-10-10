"""Librarian: memory store and retrieval (AGENTS.md section 7, D-038).

- `memory_entries` is the audit record: kind, signature, verified lessons only,
  success/fail counts, `seeded`/`learned` source.
- Every entry is mirrored to Supermemory (container `evolab-global`, plus
  `evolab-proj-<project_id>` for project notes and gotchas), which does semantic retrieval.
- Retrieval: exact signature first; then Supermemory search; if Supermemory is not
  configured or fails, a local keyword match over the table (stated in the transcript).
- Ranking: relevance * success_rate * recency. At most 3 entries are injected.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .events import emit
from .ids import new_id, now_iso
from .models import MemoryEntry
from .supermemory import Supermemory, SupermemoryError

log = logging.getLogger("evolab.librarian")
KINDS = {"error_fix", "config_outcome", "audit", "gotcha", "lesson", "dataset_profile"}
GLOBAL_TAG = "evolab-global"
MAX_HITS = 3
SEEDED_FILE = Path(__file__).resolve().parent.parent.parent / "experiments" / "seeded_memory.json"

_PATHS = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][\w.\-]+)+")
_HEX = re.compile(r"0x[0-9a-fA-F]+|\b[0-9a-f]{8,}\b")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def normalize_error(text: str) -> str:
    """Strip paths, hex and numbers so the same error on another machine has the same signature."""
    t = _PATHS.sub("<path>", text or "")
    t = _HEX.sub("<hex>", t)
    t = _NUM.sub("<n>", t)
    return " ".join(t.split())[:500]


def error_class(text: str) -> str:
    """Last 'SomethingError: message' line, normalized; used for 'same error class twice'."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    errors = [l for l in lines if re.match(r"^[\w.]+(Error|Exception)\b", l)]
    pick = errors[-1] if errors else (lines[-1] if lines else "")
    return normalize_error(pick)[:200]


def signature(kind: str, key_text: str, libraries: dict | None = None) -> str:
    libs = ",".join(f"{k}={v}" for k, v in sorted((libraries or {}).items()))
    base = normalize_error(key_text) if kind == "error_fix" else " ".join((key_text or "").lower().split())
    return hashlib.sha256(f"{kind}|{base}|{libs}".encode()).hexdigest()[:32]


def _recency(ts: str | None) -> float:
    if not ts:
        return 0.5
    try:
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).days
    except ValueError:
        return 0.5
    return math.exp(-age_days / 30)


def _success_rate(e: MemoryEntry) -> float:
    return (e.success_count + 1) / (e.success_count + e.fail_count + 2)   # Laplace smoothing


def as_text(e: MemoryEntry) -> str:
    return f"[{e.kind}] " + json.dumps(e.content_json, ensure_ascii=False)[:1500]


class Librarian:
    def __init__(self, supermemory: Supermemory | None):
        self.sm = supermemory

    # --- write -------------------------------------------------------------------------------
    def write(self, db: Session, *, kind: str, key_text: str, content: dict, context: dict | None = None,
              libraries: dict | None = None, source: str = "learned", verified: bool = False,
              project_id: str | None = None, run_id: str | None = None, sig: str | None = None) -> MemoryEntry:
        if kind not in KINDS:
            raise ValueError(f"unknown memory kind {kind}")
        if source == "learned" and not verified:
            raise ValueError("only verified lessons are written (the fix was re-run and passed)")
        sig = sig or signature(kind, key_text, libraries)
        existing = db.scalar(select(MemoryEntry).where(MemoryEntry.signature == sig))
        if existing is not None:
            existing.success_count += 1
            existing.last_used_at = now_iso()
            return existing
        entry = MemoryEntry(id=new_id("mem"), kind=kind, signature=sig, content_json=content,
                            context_json={**(context or {}), "key_text": key_text[:500], "libraries": libraries or {},
                                          "project_id": project_id},
                            source=source, success_count=1 if source == "learned" else 0)
        db.add(entry)
        db.flush()
        self._mirror(entry, project_id)
        if run_id:
            emit(db, run_id, "librarian", "memory.write", {"entry_id": entry.id, "kind": kind, "source": source})
        return entry

    def _mirror(self, entry: MemoryEntry, project_id: str | None) -> None:
        if not (self.sm and self.sm.enabled):
            return
        container = f"evolab-proj-{project_id}" if project_id and entry.kind in ("gotcha", "lesson") else GLOBAL_TAG
        try:
            entry.supermemory_id = self.sm.add(
                as_text(entry) + "\n" + entry.context_json.get("key_text", ""), container, entry.id,
                {"entry_id": entry.id, "kind": entry.kind, "signature": entry.signature, "source": entry.source})
        except SupermemoryError:
            log.warning("supermemory mirror failed for %s", entry.id, exc_info=True)

    def record_outcome(self, db: Session, entry_id: str, helped: bool) -> None:
        e = db.get(MemoryEntry, entry_id)
        if e is not None:
            if helped:
                e.success_count += 1
            else:
                e.fail_count += 1

    # --- read --------------------------------------------------------------------------------
    def search(self, db: Session, query: str, *, kind: str | None = None, project_id: str | None = None,
               sig: str | None = None, limit: int = MAX_HITS) -> tuple[list[MemoryEntry], str]:
        """Return (entries, how) where how says which retrieval path answered."""
        hits: dict[str, tuple[float, MemoryEntry]] = {}
        if sig:
            e = db.scalar(select(MemoryEntry).where(MemoryEntry.signature == sig))
            if e is not None:
                hits[e.id] = (10.0, e)
        how = "signature" if hits else "none"
        if len(hits) < limit and query.strip():
            sm_ok = False
            if self.sm and self.sm.enabled:
                try:
                    tags = [GLOBAL_TAG] + ([f"evolab-proj-{project_id}"] if project_id else [])
                    for r in self.sm.search(query, tags, limit=limit * 2, kind=kind):
                        eid = (r["metadata"] or {}).get("entry_id")
                        e = db.get(MemoryEntry, eid) if eid else None
                        if e is not None and e.id not in hits:
                            hits[e.id] = (r["similarity"], e)
                    sm_ok, how = True, ("supermemory" if how == "none" else how + "+supermemory")
                except SupermemoryError:
                    log.warning("supermemory search failed; using local keyword match", exc_info=True)
            if not sm_ok:
                for score, e in self._keyword(db, query, kind):
                    hits.setdefault(e.id, (score, e))
                how = "keyword" if how == "none" else how + "+keyword"
        ranked = sorted(hits.values(), key=lambda p: p[0] * _success_rate(p[1]) * _recency(p[1].last_used_at or p[1].created_at),
                        reverse=True)
        return [e for _, e in ranked[:limit]], how

    def _keyword(self, db: Session, query: str, kind: str | None) -> list[tuple[float, MemoryEntry]]:
        words = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query.lower())][:8]
        if not words:
            return []
        q = select(MemoryEntry)
        if kind:
            q = q.where(MemoryEntry.kind == kind)
        q = q.where(or_(*[MemoryEntry.content_json.cast(type_=_text()).ilike(f"%{w}%") for w in words]))
        out = []
        for e in db.scalars(q.limit(50)):
            text = (json.dumps(e.content_json) + json.dumps(e.context_json or {})).lower()
            out.append((sum(w in text for w in words) / len(words), e))
        return out

    def inject(self, db: Session, *, run_id: str, task_id: str, query: str, kind: str | None = None,
               project_id: str | None = None, sig: str | None = None) -> tuple[str, list[str]]:
        """Context block for an agent task, labelled seeded/learned; emits memory.hit events."""
        entries, how = self.search(db, query, kind=kind, project_id=project_id, sig=sig)
        if not entries:
            return "", []
        lines = [f"## Memory ({len(entries)} entries, retrieved by {how}; treat as hints, verify before relying)"]
        for e in entries:
            e.last_used_at = now_iso()
            lines.append(f"- ({e.source}) {as_text(e)}")
            emit(db, run_id, "librarian", "memory.hit", {"task_id": task_id, "entry_id": e.id, "kind": e.kind, "source": e.source})
        return "\n".join(lines), [e.id for e in entries]

    # --- cold start ---------------------------------------------------------------------------
    def load_seeded(self, db: Session, path: Path = SEEDED_FILE) -> int:
        """Load hand-written entries from experiments/seeded_memory.json (B), labelled `seeded`."""
        if not path.exists():
            return 0
        n = 0
        for item in json.loads(path.read_text(encoding="utf-8")):
            sig = signature(item["kind"], item.get("key_text", ""), item.get("libraries"))
            if db.scalar(select(MemoryEntry.id).where(MemoryEntry.signature == sig)) is None:
                self.write(db, kind=item["kind"], key_text=item.get("key_text", ""), content=item["content"],
                           libraries=item.get("libraries"), source="seeded", sig=sig)
                n += 1
        db.commit()
        return n


def _text():
    from sqlalchemy import Text
    return Text()
