"""The generic agent loop (ARCHITECTURE 3.3, AGENTS.md section 3, D-005, D-006).

One function runs any agent: its version is data (prompt, tools, tier, schema). Each step
is one LLM call whose reply must be one JSON tool call. Backend tools answer inline;
worker tools create a job and the task SUSPENDS (no LLM call is held open); approvals
suspend the same way. `finish` output is validated against the role's JSON schema with
one repair attempt. State is persisted after every step, so a restart resumes cleanly.
"""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from . import context
from .events import emit
from .ids import new_id, now_iso
from .llm import LLMError, LLMRateLimited
from .models import Agent, AgentMessage, AgentTask, AgentVersion, Run
from .toolproto import UNTRUSTED_RULE, ProtocolError, parse_tool_call, tools_section
from .tools import SPECS, Finish, Inline, Suspend, ToolContext, run_tool, validate_args

log = logging.getLogger("evolab.loop")
SCHEMAS = Path(__file__).resolve().parent.parent.parent / "shared" / "schemas"
MAX_PROTOCOL_REPAIRS = 2
MAX_SCHEMA_REPAIRS = 1
RATE_LIMIT_PAUSE_S = 30
MAX_PAUSES = 20                   # about 10+ minutes of an unreachable or rate-limited AI service
TASK_TOKEN_CAP = 250_000
OUTPUT_TOKENS: dict[str, int] = {}          # all tasks use the gateway maximum (4000)


@lru_cache
def schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def system_prompt(version: AgentVersion) -> str:
    out_schema = schema(version.output_schema) if version.output_schema else None
    specs = {t: SPECS[t] for t in version.tools_json if t in SPECS}
    # The untrusted-content rule is appended by code, so no refinement can remove it (AGENTS.md 6).
    return f"{version.system_prompt.strip()}\n\n{tools_section(specs, out_schema)}\n\n{UNTRUSTED_RULE}"


def _msg(db, task: AgentTask, role: str, content: str | None, tool_name=None, tool_args=None, tool_result=None) -> None:
    seq = (task.state_json or {}).get("seq", 0) + 1
    task.state_json = {**(task.state_json or {}), "seq": seq}
    db.add(AgentMessage(id=new_id("msg"), task_id=task.id, seq=seq, role=role, content=content, tool_name=tool_name,
                        tool_args_json=tool_args, tool_result_json=tool_result if isinstance(tool_result, (dict, list)) else
                        ({"text": tool_result[:20000]} if isinstance(tool_result, str) else None)))
    emit(db, task.run_id, task.agent_id or "agent", "agent.message",
         {"task_id": task.id, "seq": seq, "role": role, "content": (content or "")[:500]})


def _set_state(task: AgentTask, **kw) -> None:
    task.state_json = {**(task.state_json or {}), **kw}


def _task_event(db, task: AgentTask, agent: Agent | None, summary: str) -> None:
    emit(db, task.run_id, task.agent_id or "orchestrator", "agent.task",
         {"task_id": task.id, "agent_id": task.agent_id, "agent_name": agent.name if agent else None,
          "status": task.status, "summary": summary[:300]})


def fail(db, services, task: AgentTask, agent: Agent | None, reason: str) -> None:
    from .orchestrator import on_task_finished

    task.status, task.error, task.ended_at = "failed", reason[:2000], now_iso()
    _task_event(db, task, agent, reason)
    services.tracer.end_task((task.state_json or {}).get("trace"), None, reason)
    on_task_finished(db, services, task)


def run_task(services, task_id: str) -> None:
    """Advance one claimed task (status 'running') until it finishes or suspends."""
    with services.sessionmaker() as db:
        task = db.get(AgentTask, task_id)
        if task is None or task.status != "running":
            return
        try:
            _run(db, services, task)
        except Exception as exc:  # noqa: BLE001 - one broken task must not kill the scheduler
            log.exception("task %s crashed", task_id)
            db.rollback()
            task = db.get(AgentTask, task_id)
            fail(db, services, task, db.get(Agent, task.agent_id) if task.agent_id else None,
                 f"internal error: {type(exc).__name__}")
        db.commit()


def _run(db, services, task: AgentTask) -> None:
    run = db.get(Run, task.run_id)
    agent = db.get(Agent, task.agent_id)
    version = db.get(AgentVersion, agent.current_version_id)
    task.agent_version_id = version.id
    state = task.state_json or {}
    messages: list[dict] = state.get("messages") or []

    if not messages:
        trace = services.tracer.start_task(task.id, f"{agent.name}:{task.task_type}",
                                           {"run_id": run.id, "agent_id": agent.id, "agent_version": version.version,
                                            "role": agent.role, "tier": version.model}, task.input_json or {})
        task.langsmith_trace_id = trace
        first, mem = context.build(db, services, run, task)
        block, ids = services.librarian.inject(db, run_id=run.id, task_id=task.id, query=mem["query"] or "",
                                                kind=mem["kind"], project_id=run.project_id, sig=mem["sig"])
        if block:
            first += "\n\n" + block
        messages = [{"role": "system", "content": system_prompt(version)}, {"role": "user", "content": first}]
        _set_state(task, trace=trace, memory_ids=ids, protocol_repairs=0, schema_repairs=0)
        _msg(db, task, "user", first)
        _task_event(db, task, agent, f"{agent.name} started {task.task_type}")
    trace = (task.state_json or {}).get("trace")
    allowed = set(version.tools_json)
    ctx = ToolContext(db=db, services=services, run=run, task=task, agent=agent, version=version)
    started = time.monotonic()

    while True:
        if task.steps >= version.max_steps:
            return fail(db, services, task, agent, f"step cap reached ({version.max_steps})")
        if task.tokens_in + task.tokens_out > TASK_TOKEN_CAP:
            return fail(db, services, task, agent, "token cap reached for this task")
        # Never hold SQLite's write lock across a slow AI call: other writers (approvals,
        # the worker's results) would wait and time out (found in a live demo).
        _set_state(task, messages=messages)
        db.commit()
        try:
            reply = services.llm.call(version.model, messages, max_output_tokens=OUTPUT_TOKENS.get(task.task_type, 4000),
                                      trace=trace, name=agent.role)
        except LLMRateLimited as exc:
            pauses = (task.state_json or {}).get("pauses", 0) + 1
            if pauses > MAX_PAUSES:
                return fail(db, services, task, agent, f"AI service unavailable after {MAX_PAUSES} pauses: {exc}")
            _set_state(task, messages=messages, retry_at=time.time() + RATE_LIMIT_PAUSE_S, pauses=pauses)
            task.status = "queued"
            _task_event(db, task, agent, f"AI service busy or unreachable; retrying in {RATE_LIMIT_PAUSE_S}s ({exc})")
            return
        except LLMError as exc:
            return fail(db, services, task, agent, f"LLM error: {exc}")
        task.steps += 1
        task.tokens_in += reply.tokens_in
        task.tokens_out += reply.tokens_out
        task.wall_s = round((task.wall_s or 0) + (time.monotonic() - started), 3)
        started = time.monotonic()
        messages.append({"role": "assistant", "content": reply.text})
        _msg(db, task, "assistant", reply.text)

        try:
            name, args = parse_tool_call(reply.text, allowed)
        except ProtocolError as exc:
            n = (task.state_json or {}).get("protocol_repairs", 0) + 1
            if n > MAX_PROTOCOL_REPAIRS:
                return fail(db, services, task, agent, f"invalid tool call: {exc}")
            _set_state(task, protocol_repairs=n)
            note = f'Invalid reply: {exc}. Reply with exactly one JSON object {{"tool": ..., "args": {{...}}}}.'
            messages.append({"role": "user", "content": note})
            _msg(db, task, "user", note)
            db.commit()
            continue
        if problem := validate_args(name, args):
            note = f"Tool {name}: invalid args: {problem}"
            messages.append({"role": "user", "content": note})
            _msg(db, task, "user", note)
            db.commit()
            continue

        db.commit()                       # some tools fetch from the web; don't hold the lock meanwhile
        result = run_tool(ctx, name, args)
        services.tracer.log_tool(trace, name, args, result.content if isinstance(result, Inline) else
                                 (result.output if isinstance(result, Finish) else {"suspend": result.kind, "id": result.id}))

        if isinstance(result, Finish):
            out = result.output
            errors = []
            if version.output_schema:
                errors = sorted(Draft202012Validator(schema(version.output_schema)).iter_errors(out), key=lambda e: list(e.path))
            if errors:
                n = (task.state_json or {}).get("schema_repairs", 0) + 1
                detail = "; ".join(f"{'/'.join(map(str, e.path)) or 'output'}: {e.message}" for e in errors[:6])
                if n > MAX_SCHEMA_REPAIRS:
                    return fail(db, services, task, agent, f"output failed its schema: {detail}")
                _set_state(task, schema_repairs=n)
                note = f"finish.output does not match the schema: {detail}. Fix it and call finish again."
                messages.append({"role": "user", "content": note})
                _msg(db, task, "user", note)
                db.commit()
                continue
            _msg(db, task, "tool", None, "finish", None, out)
            return _done(db, services, task, agent, out)

        if isinstance(result, Suspend):
            _msg(db, task, "tool", None, name, args, {"suspended": result.kind, "id": result.id})
            _set_state(task, messages=messages, pending={"kind": result.kind, "id": result.id, "tool": name})
            task.status = "waiting_for_job" if result.kind == "job" else "waiting_for_approval"
            _task_event(db, task, agent, f"waiting for {result.kind} {result.id}")
            return

        content = result.content if isinstance(result.content, str) else json.dumps(result.content, ensure_ascii=False, default=str)
        note = f"Result of {name}:\n{content[:16000]}"
        messages.append({"role": "user", "content": note})
        _msg(db, task, "tool", None, name, args, result.content)
        _set_state(task, messages=messages)
        db.commit()


def _done(db, services, task: AgentTask, agent: Agent, output: dict) -> None:
    from .orchestrator import on_task_finished

    task.output_json = output
    task.signals_json = output.get("signals") or []
    task.status, task.ended_at = "done", now_iso()
    _set_state(task, messages=None, pending=None)      # transcript lives in agent_messages
    _task_event(db, task, agent, f"{agent.name} finished {task.task_type}")
    services.tracer.end_task((task.state_json or {}).get("trace"), output, None)
    on_task_finished(db, services, task)


def resume_with(db, task: AgentTask, text: str) -> None:
    """Append a job or approval result to a suspended task and queue it to continue."""
    state = task.state_json or {}
    messages = state.get("messages") or []
    messages.append({"role": "user", "content": text[:20000]})
    task.state_json = {**state, "messages": messages, "pending": None}
    task.status = "queued"
    _msg(db, task, "tool", None, (state.get("pending") or {}).get("tool"), None, text[:20000])
