"""LangSmith tracing (D-039). One agent task = one trace; LLM and tool calls are child runs;
council scores are feedback on the task's trace. Off unless LANGSMITH_TRACING=true and a key is set.

Tracing must never break a run: every LangSmith call is wrapped and errors are logged only.
Text sent to LangSmith is scrubbed of key-like strings first.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from .config import Settings
from .scrub import scrub

log = logging.getLogger("evolab.tracing")
MAX_FIELD = 20_000


def _clip(value):
    if isinstance(value, str):
        return scrub(value[:MAX_FIELD])
    if isinstance(value, list):
        return [_clip(v) for v in value[:50]]
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in list(value.items())[:50]}
    return value


class NoopTracer:
    enabled = False

    def start_task(self, task_id: str, name: str, metadata: dict, inputs: dict) -> str | None:
        return None

    def log_llm(self, trace, name, tier, messages, reply) -> None: ...

    def log_tool(self, trace, name: str, args: dict, result) -> None: ...

    def end_task(self, trace, outputs: dict | None, error: str | None) -> None: ...

    def feedback(self, trace_id: str | None, key: str, score: float, comment: str | None = None) -> None: ...

    def url(self, trace_id: str | None) -> str | None:
        return None


class LangSmithTracer(NoopTracer):
    enabled = True

    def __init__(self, settings: Settings):
        from langsmith import Client

        self.client = Client(api_key=settings.langsmith_api_key)
        self.project = settings.langsmith_project

    def _safe(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - tracing must never break a run
            log.warning("langsmith call failed", exc_info=True)
            return None

    def start_task(self, task_id, name, metadata, inputs):
        run_id = str(uuid.uuid4())
        self._safe(self.client.create_run, name=name, inputs=_clip(inputs), run_type="chain", id=run_id,
                   project_name=self.project, start_time=datetime.now(timezone.utc),
                   extra={"metadata": {**metadata, "task_id": task_id}})
        return run_id

    def log_llm(self, trace, name, tier, messages, reply):
        if not trace:
            return
        child = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        self._safe(self.client.create_run, name=f"{name}:{tier}", run_type="llm", id=child, parent_run_id=trace,
                   project_name=self.project, inputs={"messages": _clip(messages)}, start_time=now,
                   extra={"metadata": {"tier": tier, "model": reply.model, "trimmed": reply.trimmed}})
        self._safe(self.client.update_run, child, end_time=now, outputs={"text": _clip(reply.text)},
                   extra={"metadata": {"tokens_in": reply.tokens_in, "tokens_out": reply.tokens_out}})

    def log_tool(self, trace, name, args, result):
        if not trace:
            return
        child = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        self._safe(self.client.create_run, name=f"tool:{name}", run_type="tool", id=child, parent_run_id=trace,
                   project_name=self.project, inputs=_clip(args), start_time=now)
        self._safe(self.client.update_run, child, end_time=now, outputs={"result": _clip(result)})

    def end_task(self, trace, outputs, error):
        if trace:
            self._safe(self.client.update_run, trace, end_time=datetime.now(timezone.utc),
                       outputs=_clip(outputs or {}), error=error)

    def feedback(self, trace_id, key, score, comment=None):
        if trace_id:
            self._safe(self.client.create_feedback, run_id=trace_id, key=key, score=score,
                       comment=scrub(comment) if comment else None)


def make_tracer(settings: Settings):
    if settings.langsmith_tracing and settings.langsmith_api_key:
        try:
            return LangSmithTracer(settings)
        except Exception:  # noqa: BLE001
            log.warning("LangSmith disabled: client could not start", exc_info=True)
    return NoopTracer()
