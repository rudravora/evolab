"""Performance Council runner (AGENTS.md section 5a, D-040).

For a finished agent task: three judges (strong, code, fast tiers; never a fallback tier)
score it blind to the agent's model and version. Each judge replies with one JSON object
(shared/schemas/council_judge.json), one repair attempt. Code aggregates (median of 3,
mean of 2, unavailable below 2), stores council_scores rows, re-scores the task, emits
`council.score`, and sends the scores to LangSmith as feedback on the task's trace.
Runs off the critical path: the orchestrator never waits for it.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from jsonschema import Draft202012Validator
from sqlalchemy import select

from .agent_loop import schema
from .events import emit
from .ids import new_id
from .llm import LLMError, LLMRateLimited
from .models import Agent, AgentMessage, AgentTask, AgentVersion, CouncilScore, LedgerEntry
from .toolproto import UNTRUSTED_RULE, ProtocolError, extract_json, wrap_untrusted

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.council import aggregate  # noqa: E402

log = logging.getLogger("evolab.council")
TRANSCRIPT_CHARS = 14000
MAX_ATTEMPTS = 3
RETRY_AFTER_S = 90
_VALID = Draft202012Validator(schema("council_judge.json"))


def judge_input(db, task: AgentTask) -> str:
    agent = db.get(Agent, task.agent_id)
    version = db.get(AgentVersion, task.agent_version_id) if task.agent_version_id else None
    contract = (version.system_prompt[:3000] if version else "") + \
        ("\nOutput schema: " + json.dumps(schema(version.output_schema))[:3000] if version and version.output_schema else "")
    msgs = list(db.scalars(select(AgentMessage).where(AgentMessage.task_id == task.id).order_by(AgentMessage.seq)))
    lines = []
    for m in msgs[1:]:   # skip the opening context, which is restated as the task input below
        body = m.content or json.dumps(m.tool_result_json or m.tool_args_json or {}, ensure_ascii=False)[:1500]
        lines.append(f"[{m.role}{':' + m.tool_name if m.tool_name else ''}] {body[:1500]}")
    transcript = "\n".join(lines)
    if len(transcript) > TRANSCRIPT_CHARS:
        transcript = transcript[: TRANSCRIPT_CHARS // 2] + "\n...[middle trimmed]...\n" + transcript[-TRANSCRIPT_CHARS // 2:]
    ledger = [{"category": e.category, "description": e.description}
              for e in db.scalars(select(LedgerEntry).where(LedgerEntry.task_id == task.id))]
    return "\n\n".join([
        f"# Agent task to judge\nRole: {agent.role}\nTask type: {task.task_type}\nStatus: {task.status}"
        + (f"\nError: {task.error}" if task.error else ""),
        "## Role contract\n" + contract,
        "## Task input\n" + wrap_untrusted("task input", json.dumps(task.input_json or {}, ensure_ascii=False)[:4000]),
        "## Final output\n" + wrap_untrusted("agent output", json.dumps(task.output_json or {}, ensure_ascii=False)[:6000]),
        "## Transcript (truncated)\n" + wrap_untrusted("transcript", transcript),
        f"## Deterministic outcome check\nO_det = {task.outcome_det}",
        "## Ledger entries written by this task\n" + json.dumps(ledger)[:2000],
        f"## Cost\ntokens={task.tokens_in + task.tokens_out}, wall_s={task.wall_s}",
        'Reply with ONE JSON object only, matching: {"scores": {"task_fulfilment", "correctness", "contract_adherence", '
        '"efficiency", "honesty"} (each 0-1), "overall" (0-1), "rationale" (<=1200 chars), "failure_pattern" (short label '
        'or null), "confidence" (0-1)}.',
    ])


def _ask_judge(services, judge: Agent, version: AgentVersion, prompt: str, trace) -> tuple[dict | None, int, int]:
    messages = [{"role": "system", "content": version.system_prompt + "\n\n" + UNTRUSTED_RULE},
                {"role": "user", "content": prompt}]
    tin = tout = 0
    for attempt in range(2):
        try:
            reply = services.llm.call(version.model, messages, max_output_tokens=3000, allow_fallback=False,
                                      trace=trace, name=f"council:{judge.id}")
        except LLMRateLimited as exc:
            log.warning("judge %s rate limited: %s", judge.id, exc)
            return "rate_limited", tin, tout
        except LLMError as exc:
            log.warning("judge %s unavailable: %s", judge.id, exc)
            return None, tin, tout
        tin, tout = tin + reply.tokens_in, tout + reply.tokens_out
        try:
            out = extract_json(reply.text)
            errors = list(_VALID.iter_errors(out))
            if not errors:
                return out, tin, tout
            problem = "; ".join(e.message for e in errors[:4])
        except ProtocolError as exc:
            problem = str(exc)
        messages += [{"role": "assistant", "content": reply.text},
                     {"role": "user", "content": f"Invalid: {problem}. Reply with the JSON object only."}]
    return None, tin, tout


def run(services, task_id: str) -> None:
    from .rewards import score

    with services.sessionmaker() as db:
        task = db.get(AgentTask, task_id)
        if task is None or (task.state_json or {}).get("council") != "running":
            return
        prompt = judge_input(db, task)
        trace = task.langsmith_trace_id
        judges = list(db.scalars(select(Agent).where(Agent.role == "council_judge", Agent.status == "active").order_by(Agent.id)))
        rows = list(db.scalars(select(CouncilScore).where(CouncilScore.task_id == task.id)))
        done_judges = {r.judge_agent_id for r in rows}
        limited = False
        for judge in judges:
            if judge.id in done_judges:          # a retry only asks the judges that were missing
                continue
            version = db.get(AgentVersion, judge.current_version_id)
            out, tin, tout = _ask_judge(services, judge, version, prompt, trace)
            if out == "rate_limited":
                limited = True
                continue
            if out is None:
                continue
            row = CouncilScore(id=new_id("cs"), task_id=task.id, judge_agent_id=judge.id, tier=version.model,
                               scores_json=out["scores"], overall=out["overall"], rationale=out["rationale"],
                               failure_pattern=out.get("failure_pattern"), confidence=out["confidence"],
                               tokens_in=tin, tokens_out=tout)
            db.add(row)
            rows.append(row)
            services.tracer.feedback(trace, f"council.{version.model}", out["overall"], out["rationale"])
        result = aggregate([{"overall": r.overall, "failure_pattern": r.failure_pattern} for r in rows])
        task.council_q, task.council_judges = result.q, result.judges
        task.council_disagreement, task.council_split = result.disagreement, result.split
        state = {**(task.state_json or {}), "council": "done", "council_pattern": result.failure_pattern}
        attempts = state.get("council_attempts", 0) + 1
        if limited and len(rows) < len(judges) and attempts < MAX_ATTEMPTS:
            # The gateway rate-limits per minute: come back later for the missing judges (Q-26).
            state.update(council="pending", council_attempts=attempts, council_retry_at=time.time() + RETRY_AFTER_S)
        task.state_json = state
        if result.q is not None:
            services.tracer.feedback(trace, "council.Q", result.q, "split" if result.split else None)
        emit(db, task.run_id, "council", "council.score",
             {"task_id": task.id, "agent_id": task.agent_id,
              "judges": [{"judge_agent_id": r.judge_agent_id, "tier": r.tier, "overall": r.overall} for r in rows],
              "q": result.q, "disagreement": result.disagreement, "split": result.split})
        score(db, task)
        from .evolution import after_task
        after_task(db, services, task)
        db.commit()
