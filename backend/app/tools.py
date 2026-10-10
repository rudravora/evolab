"""Backend tool implementations (ARCHITECTURE section 5). Agents may call only the tools in
their version's `tools` list; each call is validated against the spec below.

A tool returns one of:
- Inline(content)         answer now, the loop continues
- Suspend("job", job_id)  a worker job was created; the task waits for its result
- Suspend("approval", id) the task waits for a researcher decision
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from jsonschema import Draft202012Validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import ApiError
from .events import emit
from .ids import new_id
from .jobs import create_job
from .models import (Agent, AgentTask, AgentVersion, Approval, Experiment, Job, JobLog, LedgerEntry, Note,
                     Run)
from .toolproto import wrap_untrusted
from .web import FetchError

if TYPE_CHECKING:
    from .services import Services

LEDGER_CATEGORIES = ["compute_adaptation", "dependency_fix", "bug_fix", "hyperparameter_change", "fidelity_deviation"]
_obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}
_s = {"type": "string"}
_i = {"type": "integer"}

SPECS: dict[str, dict] = {
    "finish": {"description": "End the task with your final output.",
               "args": _obj({"output": {"type": "object"}}, ["output"])},
    "search_papers": {"description": "Search arXiv. Returns titles, URLs and abstracts (untrusted).",
                      "args": _obj({"query": _s, "max_results": {"type": "integer", "minimum": 1, "maximum": 10}}, ["query"])},
    "fetch_pdf_text": {"description": "Text of a paper PDF (arXiv URL, arXiv id, or an uploaded input id), a window at a "
                                      "time (untrusted). Pass `search` to get up to 8 snippets with offsets instead, "
                                      "e.g. search='Table' or 'RMSE', then read around the best offset.",
                       "args": _obj({"url": _s, "offset": {"type": "integer", "minimum": 0},
                                     "length": {"type": "integer", "minimum": 500, "maximum": 10000},
                                     "search": {"type": "string", "minLength": 2, "maxLength": 80}}, ["url"])},
    "find_repo": {"description": "Search GitHub repositories, or read a repository README when given its URL (untrusted).",
                  "args": _obj({"query": _s}, ["query"])},
    "search_baselines": {"description": "Search arXiv abstracts for published baselines on a dataset (untrusted).",
                         "args": _obj({"dataset": _s}, ["dataset"])},
    "propose_candidates": {"description": "Submit 3-5 candidate papers for the researcher to pick (does not wait).",
                           "args": _obj({"candidates": {"type": "array", "minItems": 3, "maxItems": 5, "items": _obj(
                               {"title": _s, "url": _s, "why": _s}, ["title", "url", "why"])}}, ["candidates"])},
    "read_memory": {"description": "Search memory for past fixes, audits, gotchas, config outcomes, dataset profiles.",
                    "args": _obj({"query": _s, "kind": {"enum": ["error_fix", "config_outcome", "audit", "gotcha", "lesson",
                                                                  "dataset_profile"]}}, ["query"])},
    "write_memory": {"description": "Store a VERIFIED lesson (only after the fix was re-run and passed).",
                     "args": _obj({"kind": {"enum": ["error_fix", "config_outcome", "audit", "gotcha", "lesson", "dataset_profile"]},
                                   "key_text": _s, "content": {"type": "object"}, "libraries": {"type": "object"},
                                   "verified": {"type": "boolean"}}, ["kind", "key_text", "content", "verified"])},
    "log_ledger": {"description": "Record a deviation from the paper or official code, at the moment you make it.",
                   "args": _obj({"category": {"enum": LEDGER_CATEGORIES}, "description": _s, "diff_ref": _s,
                                 "before": {}, "after": {}}, ["category", "description"])},
    "read_ledger": {"description": "List this run's ledger entries.", "args": _obj({})},
    "record_metric": {"description": "Attach derived metrics to an experiment.",
                      "args": _obj({"experiment_id": _s, "metrics": {"type": "object"}}, ["experiment_id", "metrics"])},
    "write_note": {"description": "Save a Markdown note to the project.",
                   "args": _obj({"title": _s, "markdown": _s, "source_ref": _s}, ["title", "markdown"])},
    "read_logs": {"description": "Read a job's output tails and recent log lines.",
                  "args": _obj({"job_id": _s, "lines": {"type": "integer", "minimum": 10, "maximum": 400}}, ["job_id"])},
    "search_agents": {"description": "Search the agent registry by role, name or tag.", "args": _obj({"query": _s}, ["query"])},
    "match_agents": {"description": "Agents and dormant templates whose tags cover a tag set.",
                     "args": _obj({"tags": {"type": "array", "items": _s}}, ["tags"])},
    "spawn_agent": {"description": "Ask for an agent covering tags; walks the resolution ladder and creates an evolution approval.",
                    "args": _obj({"required_tags": {"type": "array", "items": _s, "minItems": 1}, "reason": _s},
                                 ["required_tags", "reason"])},
    "replan": {"description": "Not used directly: return replan diffs through finish (kind=replan).", "args": _obj({})},
    "propose_branch": {"description": "Propose one what-if branch (the Meta-Controller decides whether it runs).",
                       "args": _obj({"hypothesis": _s, "spec": {"type": "object"}, "est_cost": {"type": "object"},
                                     "expected_effect": _s, "kind": {"enum": ["whatif", "exploratory", "baseline", "transfer"]}},
                                    ["hypothesis", "spec", "kind"])},
    "request_approval": {"description": "Ask the researcher a question and wait for the answer.",
                         "args": _obj({"question": _s}, ["question"])},
    "get_budget": {"description": "Run budget and usage so far.", "args": _obj({})},
    "create_job": {"description": "Run something on the researcher's laptop (policy-checked). Types: shell, python_script, "
                                  "pip_install, write_file, read_file, list_dir, git, download (payloads in API.md 9).",
                   "args": _obj({"type": {"enum": ["shell", "python_script", "pip_install", "write_file", "read_file",
                                                   "list_dir", "git", "download"]},
                                 "payload": {"type": "object"}, "timeout_s": {"type": "integer", "minimum": 10, "maximum": 3600}},
                                ["type", "payload"])},
    "read_file": {"description": "Read a file in the project workspace on the worker.", "args": _obj({"path": _s}, ["path"])},
    "write_file": {"description": "Write a file in the project workspace on the worker.",
                   "args": _obj({"path": _s, "content": _s}, ["path", "content"])},
}
_VALIDATORS = {name: Draft202012Validator(spec["args"]) for name, spec in SPECS.items()}


@dataclass
class Inline:
    content: str | dict | list


@dataclass
class Suspend:
    kind: str          # job | approval
    id: str


@dataclass
class Finish:
    output: dict


@dataclass
class ToolContext:
    db: Session
    services: "Services"
    run: Run
    task: AgentTask
    agent: Agent
    version: AgentVersion


def validate_args(name: str, args: dict) -> str | None:
    errors = sorted(_VALIDATORS[name].iter_errors(args), key=lambda e: e.path)
    return "; ".join(f"{'/'.join(map(str, e.path)) or 'args'}: {e.message}" for e in errors[:5]) or None


def job_result_view(job: Job) -> str:
    view = {"job_id": job.id, "type": job.type, "status": job.status, "exit_code": job.exit_code,
            "stdout_tail": (job.stdout_tail or "")[-4000:], "stderr_tail": (job.stderr_tail or "")[-4000:],
            "metrics": job.metrics_json or {}}
    return wrap_untrusted(f"worker job {job.id}", json.dumps(view, ensure_ascii=False))


def run_tool(ctx: ToolContext, name: str, args: dict) -> Inline | Suspend | Finish:
    if name == "finish":
        return Finish(args["output"])
    fn = _IMPL.get(name)
    if fn is None:
        return Inline({"error": f"tool {name} is not implemented"})
    try:
        return fn(ctx, args)
    except (FetchError, httpx.HTTPError) as exc:
        # A failed web fetch is a tool result the agent can react to, not a crash.
        return Inline({"error": f"fetch failed: {type(exc).__name__}: {str(exc)[:200]}"})
    except ApiError as exc:
        return Inline({"error": exc.code, "message": exc.message})


# --- research tools ------------------------------------------------------------------------

def _search_papers(ctx, a):
    papers = ctx.services.web.arxiv_search(a["query"], a.get("max_results", 5))
    return Inline(wrap_untrusted("arxiv search", json.dumps([p.__dict__ for p in papers], ensure_ascii=False)))


def _cache_path(ctx, url: str) -> Path:
    d = Path(ctx.services.settings.artifacts_dir) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".txt")


def _uploaded_pdf_text(ctx, input_id: str) -> str:
    from pypdf import PdfReader

    from .models import Input
    inp = ctx.db.get(Input, input_id)
    if inp is None or inp.project_id != ctx.run.project_id or inp.source != "upload" or not (inp.meta_json or {}).get("path"):
        raise FetchError("no uploaded PDF with that input id in this project")
    reader = PdfReader(inp.meta_json["path"])
    return "\n".join((p.extract_text() or "") for p in reader.pages[:60])


def _fetch_pdf_text(ctx, a):
    raw = a["url"].strip()
    url = raw if raw.startswith(("http", "inp_")) else f"https://arxiv.org/abs/{raw}"
    path = _cache_path(ctx, url)
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = _uploaded_pdf_text(ctx, url) if url.startswith("inp_") else ctx.services.web.pdf_text(url)
        path.write_text(text, encoding="utf-8")
    if a.get("search"):
        # Jump to the parts that matter (e.g. "Table", "RMSE", "grid") instead of reading page by page.
        needle, hits, i = a["search"].lower(), [], -1
        low = text.lower()
        while len(hits) < 8 and (i := low.find(needle, i + 1)) != -1:
            hits.append({"offset": max(0, i - 200), "snippet": text[max(0, i - 200): i + 400]})
        return Inline(f"{len(hits)} match(es) for {a['search']!r} in {len(text)} chars\n" +
                      wrap_untrusted(url, json.dumps(hits, ensure_ascii=False)))
    off, length = a.get("offset", 0), a.get("length", 8000)
    window = text[off:off + length]
    header = f"chars {off}-{off + len(window)} of {len(text)}" + ("" if off + length >= len(text) else f"; next offset {off + length}")
    return Inline(header + "\n" + wrap_untrusted(url, window))


def _find_repo(ctx, a):
    q = a["query"].strip()
    if q.startswith("https://github.com/"):
        readme = ctx.services.web.github_readme(q)
        return Inline(wrap_untrusted(f"README {q}", (readme or "README not found")[:12000]))
    return Inline(wrap_untrusted("github search", json.dumps(ctx.services.web.github_search(q))))


def _search_baselines(ctx, a):
    papers = ctx.services.web.arxiv_search(f"{a['dataset']} benchmark baseline", 6)
    return Inline(wrap_untrusted("baseline search", json.dumps([p.__dict__ for p in papers], ensure_ascii=False)))


def _propose_candidates(ctx, a):
    goal = ctx.run.goal or ""
    approval = Approval(id=new_id("apr"), run_id=ctx.run.id, type="candidate_selection", requested_by=ctx.agent.id,
                        payload_json={"summary": f"Pick a paper for: {goal}"[:300], "candidates": a["candidates"],
                                      "task_id": ctx.task.id})
    ctx.db.add(approval)
    ctx.db.flush()
    emit(ctx.db, ctx.run.id, ctx.agent.id, "approval.requested",
         {"approval_id": approval.id, "type": "candidate_selection", "summary": approval.payload_json["summary"]})
    emit(ctx.db, ctx.run.id, ctx.agent.id, "candidates.ready", {"approval_id": approval.id, "count": len(a["candidates"])})
    ctx.services.notify(ctx.db, "approval_requested", approval)
    return Inline({"approval_id": approval.id, "note": "Submitted. Do not wait; finish with the same candidates."})


# --- memory, ledger, notes --------------------------------------------------------------------

def _read_memory(ctx, a):
    entries, how = ctx.services.librarian.search(ctx.db, a["query"], kind=a.get("kind"), project_id=ctx.run.project_id)
    for e in entries:
        emit(ctx.db, ctx.run.id, "librarian", "memory.hit", {"task_id": ctx.task.id, "entry_id": e.id, "kind": e.kind,
                                                              "source": e.source})
    return Inline({"retrieved_by": how, "entries": [{"id": e.id, "kind": e.kind, "source": e.source,
                                                     "content": e.content_json} for e in entries]})


def _write_memory(ctx, a):
    if not a["verified"]:
        return Inline({"error": "only verified lessons are written; re-run the fix first"})
    ok_job = ctx.db.scalar(select(func.count()).select_from(Job).where(Job.task_id == ctx.task.id, Job.status == "done"))
    if a["kind"] in ("error_fix", "config_outcome") and not ok_job:
        return Inline({"error": "no successful re-run in this task yet; a lesson is verified only after it passes"})
    e = ctx.services.librarian.write(ctx.db, kind=a["kind"], key_text=a["key_text"], content=a["content"],
                                     libraries=a.get("libraries"), verified=True, project_id=ctx.run.project_id,
                                     run_id=ctx.run.id, context={"task_id": ctx.task.id, "agent_id": ctx.agent.id})
    return Inline({"entry_id": e.id, "signature": e.signature})


def _log_ledger(ctx, a):
    e = LedgerEntry(id=new_id("led"), run_id=ctx.run.id, task_id=ctx.task.id, category=a["category"],
                    description=a["description"][:2000], diff_ref=a.get("diff_ref"),
                    before_json=a.get("before"), after_json=a.get("after"))
    ctx.db.add(e)
    ctx.db.flush()
    emit(ctx.db, ctx.run.id, ctx.agent.id, "ledger.entry", {"id": e.id, "category": e.category, "description": e.description})
    return Inline({"ledger_entry_id": e.id})


def ledger_rows(db: Session, run_id: str) -> list[dict]:
    return [{"id": e.id, "category": e.category, "description": e.description, "diff_ref": e.diff_ref,
             "task_id": e.task_id} for e in db.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run_id)
                                                          .order_by(LedgerEntry.created_at))]


def _read_ledger(ctx, a):
    return Inline(ledger_rows(ctx.db, ctx.run.id))


def _record_metric(ctx, a):
    exp = ctx.db.get(Experiment, a["experiment_id"])
    if exp is None:
        return Inline({"error": "experiment not found"})
    exp.metrics_json = {**(exp.metrics_json or {}), **{k: v for k, v in a["metrics"].items() if isinstance(v, (int, float))}}
    return Inline({"ok": True})


def _write_note(ctx, a):
    n = Note(id=new_id("note"), project_id=ctx.run.project_id, title=a["title"][:300], markdown=a["markdown"][:50_000],
             source_ref=a.get("source_ref") or f"task:{ctx.task.id}")
    ctx.db.add(n)
    return Inline({"note_id": n.id})


def _read_logs(ctx, a):
    job = ctx.db.get(Job, a["job_id"])
    if job is None or job.run_id != ctx.run.id:
        return Inline({"error": "job not found in this run"})
    lines = list(ctx.db.scalars(select(JobLog.chunk).where(JobLog.job_id == job.id, JobLog.attempt == job.attempt)
                                .order_by(JobLog.seq.desc()).limit(a.get("lines", 120))))[::-1]
    return Inline(job_result_view(job) + "\n" + wrap_untrusted("job log", "\n".join(lines)[-8000:]))


# --- registry, evolution, planning --------------------------------------------------------------

def _search_agents(ctx, a):
    from .rewards import rolling_reward
    q = a["query"].lower()
    out = []
    for ag in ctx.db.scalars(select(Agent)):
        v = ctx.db.get(AgentVersion, ag.current_version_id) if ag.current_version_id else None
        hay = " ".join([ag.name, ag.role, *(v.capability_tags_json if v else [])]).lower()
        if q in hay:
            out.append({"agent_id": ag.id, "name": ag.name, "role": ag.role, "kind": ag.kind, "status": ag.status,
                        "tags": v.capability_tags_json if v else [], "rolling_reward": rolling_reward(ctx.db, ag.id)})
    return Inline(out[:20])


def _match_agents(ctx, a):
    from .ladder import covering_agents
    return Inline([{"agent_id": ag.id, "name": ag.name, "status": ag.status, "kind": ag.kind}
                   for ag in covering_agents(ctx.db, set(a["tags"]), include_inactive=True)])


def _spawn_agent(ctx, a):
    if ctx.agent.role != "meta_controller":
        return Inline({"error": "only the Meta-Controller proposes new agents"})
    from .evolution import open_gap
    result = open_gap(ctx.db, ctx.services, ctx.run, set(a["required_tags"]), source="researcher", reason=a["reason"],
                      task=None)
    return Inline(result)


def _replan(ctx, a):
    return Inline({"note": "Return the diff through finish with kind=replan."})


def _propose_branch(ctx, a):
    from .executor import ensure_branch
    b = ensure_branch(ctx.db, ctx.run, a, proposed_by=ctx.agent.id)
    return Inline({"branch_id": b.id, "status": b.status})


def _request_approval(ctx, a):
    approval = Approval(id=new_id("apr"), run_id=ctx.run.id, type="human_input", requested_by=ctx.agent.id,
                        payload_json={"summary": a["question"][:500], "question": a["question"], "task_id": ctx.task.id})
    ctx.db.add(approval)
    ctx.db.flush()
    emit(ctx.db, ctx.run.id, ctx.agent.id, "approval.requested",
         {"approval_id": approval.id, "type": "human_input", "summary": approval.payload_json["summary"]})
    ctx.services.notify(ctx.db, "approval_requested", approval)
    return Suspend("approval", approval.id)


def _get_budget(ctx, a):
    from .orchestrator import usage
    return Inline({"budget": ctx.run.budget_json, "usage": usage(ctx.db, ctx.run)})


# --- worker tools ------------------------------------------------------------------------------

def _create_job(ctx, a):
    job = create_job(ctx.db, ctx.run, a["type"], a["payload"], task_id=ctx.task.id,
                     timeout_s=a.get("timeout_s", 600), actor=ctx.agent.id)
    return Suspend("job", job.id)


def _read_file(ctx, a):
    job = create_job(ctx.db, ctx.run, "read_file", {"path": a["path"]}, task_id=ctx.task.id, timeout_s=60, actor=ctx.agent.id)
    return Suspend("job", job.id)


def _write_file(ctx, a):
    job = create_job(ctx.db, ctx.run, "write_file", {"path": a["path"], "content": a["content"]}, task_id=ctx.task.id,
                     timeout_s=60, actor=ctx.agent.id)
    return Suspend("job", job.id)


_IMPL = {
    "search_papers": _search_papers, "fetch_pdf_text": _fetch_pdf_text, "find_repo": _find_repo,
    "search_baselines": _search_baselines, "propose_candidates": _propose_candidates, "read_memory": _read_memory,
    "write_memory": _write_memory, "log_ledger": _log_ledger, "read_ledger": _read_ledger,
    "record_metric": _record_metric, "write_note": _write_note, "read_logs": _read_logs,
    "search_agents": _search_agents, "match_agents": _match_agents, "spawn_agent": _spawn_agent, "replan": _replan,
    "propose_branch": _propose_branch, "request_approval": _request_approval, "get_budget": _get_budget,
    "create_job": _create_job, "read_file": _read_file, "write_file": _write_file,
}
