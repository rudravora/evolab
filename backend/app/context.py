"""Task context: the first user message an agent sees (AGENTS.md section 3, "context assembly").

Task input, then role-specific material from earlier tasks, then up to 3 memory hits.
Untrusted text (paper text, READMEs, worker output) is wrapped in <untrusted> tags.
Each block is bounded so the opening message stays well under the 48 KB request cap.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .librarian import error_class, signature
from .models import Agent, AgentTask, AgentVersion, Approval, Branch, Input, Job, Run
from .stats import run_stats
from .toolproto import wrap_untrusted

BLOCK = 6000


def _j(obj, limit: int = BLOCK) -> str:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


def latest_output(db: Session, run_id: str, task_type: str) -> dict | None:
    t = db.scalar(select(AgentTask).where(AgentTask.run_id == run_id, AgentTask.task_type == task_type,
                                          AgentTask.status == "done").order_by(AgentTask.ended_at.desc()).limit(1))
    return t.output_json if t else None


def _inputs(db: Session, run: Run, kind: str | None = None) -> list[Input]:
    q = select(Input).where(Input.project_id == run.project_id)
    if kind:
        q = q.where(Input.kind == kind)
    return list(db.scalars(q.order_by(Input.created_at)))


def _input_view(i: Input) -> str:
    m = i.meta_json or {}
    view = {"input_id": i.id, "kind": i.kind, "source": i.source, "ref": i.ref, "title": m.get("title")}
    text = _j(view)
    if m.get("abstract"):
        text += "\n" + wrap_untrusted(f"abstract of {i.ref}", m["abstract"][:2500])
    if m.get("readme_excerpt"):
        text += "\n" + wrap_untrusted(f"README of {i.ref}", m["readme_excerpt"][:4000])
    return text


def _registry(db: Session) -> list[dict]:
    out = []
    for a in db.scalars(select(Agent).where(Agent.role != "council_judge")):
        v = db.get(AgentVersion, a.current_version_id) if a.current_version_id else None
        out.append({"agent_id": a.id, "name": a.name, "role": a.role, "status": a.status, "kind": a.kind,
                    "tags": v.capability_tags_json if v else []})
    return out


def _graph_view(db: Session, run: Run) -> list[dict]:
    return [{"task_id": t.graph_key, "task_type": t.task_type, "agent_id": t.agent_id, "status": t.status,
             "depends_on": t.depends_on_json or []}
            for t in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.graph_key.is_not(None))
                                .order_by(AgentTask.created_at))]


def _branches(db: Session, run: Run, statuses: tuple[str, ...] | None = None) -> list[dict]:
    q = select(Branch).where(Branch.run_id == run.id)
    if statuses:
        q = q.where(Branch.status.in_(statuses))
    return [{"branch_id": b.id, "hypothesis": b.hypothesis, "kind": b.kind, "status": b.status,
             "spec": {k: v for k, v in (b.spec_json or {}).items() if not k.startswith("_")},
             "est_cost": (b.spec_json or {}).get("_est_cost")} for b in db.scalars(q.order_by(Branch.created_at))]


def build(db: Session, services, run: Run, task: AgentTask) -> tuple[str, dict]:
    """Return (message, memory_query) for the task's first user message."""
    tt, inp = task.task_type, task.input_json or {}
    brief = run.brief_json or {}
    parts = [f"# Task: {tt}", f"Run goal: {run.goal or '(none)'}", "Task input: " + _j(inp, 3000)]
    mem: dict = {"query": run.goal or tt, "kind": None, "sig": None}

    if tt == "plan":
        parts += ["Return finish.output with kind=plan.",
                  "Research Brief: " + _j({k: brief.get(k) for k in ("entry_types", "facts", "domain", "reference_targets")}),
                  "Deterministic activation: " + _j(run.activation_json),
                  "Draft task graph from fragments (adapt it; every change needs a reason in activation or signals): "
                  + _j(inp.get("draft_graph"), 9000),
                  "Capability gaps (tasks no active agent covers): " + _j(inp.get("gaps")),
                  "Budget: " + _j(run.budget_json), "Agent registry: " + _j(_registry(db), 4000)]
        if inp.get("comment"):
            parts.append(wrap_untrusted("researcher comment on the rejected plan", inp["comment"]))
        mem.update(kind="audit")
    elif tt == "replan":
        parts += ["Return finish.output with kind=replan: the smallest diff that handles the trigger, plus a reason.",
                  "Trigger: " + _j(inp.get("trigger")), "Current graph: " + _j(_graph_view(db, run), 7000),
                  "Budget: " + _j(run.budget_json)]
        if inp.get("message"):
            parts.append(wrap_untrusted("researcher chat message", inp["message"]))
    elif tt in ("select_branches", "decide_branches"):
        stage = "select which proposed branches run within the budget" if tt == "select_branches" else \
            "decide expand or prune for every finished branch, citing metric deltas and seed variance"
        parts += [f"Return finish.output with kind=replan, an empty diff, and branch_decisions: {stage}. "
                  "decision 'expanded' = run it / worth following up; 'pruned' = stop.",
                  "Branches: " + _j(_branches(db, run), 6000), "Statistics: " + _j(run_stats(db, run.id), 9000),
                  "Budget: " + _j(run.budget_json)]
    elif tt == "evolution_draft":
        parts += ["Return finish.output with kind=evolution_draft.", "Candidate: " + _j(inp.get("candidate"), 9000),
                  "Agent registry: " + _j(_registry(db), 4000)]
    elif tt == "extract_spec":
        papers = [i for i in _inputs(db, run, "paper") if not inp.get("input_id") or i.id == inp["input_id"]]
        parts += ["mode=paper. Read the first window with fetch_pdf_text, then use its search argument to jump to the "
                  "experiments and tables; extract the spec within about 10 tool calls."] + [_input_view(p) for p in papers]
        mem.update(query=" ".join((p.meta_json or {}).get("title") or p.ref for p in papers), kind="gotcha")
    elif tt == "find_candidates":
        parts += ["mode=question. Find 3-5 candidate papers, submit them with propose_candidates, then finish."] + \
                 [_input_view(q) for q in _inputs(db, run, "question")]
    elif tt == "search_baselines":
        parts += ["mode=baselines."] + [_input_view(d) for d in _inputs(db, run, "dataset")]
    elif tt == "audit_repo":
        repos = _inputs(db, run, "repo")
        parts += ["Reproduction spec: " + _j(latest_output(db, run.id, "extract_spec"))] + [_input_view(r) for r in repos]
        mem.update(query=" ".join(r.ref for r in repos), kind="audit")
    elif tt == "setup_env":
        parts += ["Spec: " + _j(latest_output(db, run.id, "extract_spec")),
                  "Audit: " + _j(latest_output(db, run.id, "audit_repo"))] + [_input_view(d) for d in _inputs(db, run, "dataset")]
        if inp.get("profile_dataset"):
            parts.append("Profile every dataset with a python_script job running profile_dataset.py (API.md 9) and report "
                         "leakage or a missing target in signals.")
        mem.update(query=" ".join(d.ref for d in _inputs(db, run, "dataset")) or (run.goal or ""), kind="dataset_profile")
    elif tt == "implement":
        parts += ["Spec: " + _j(latest_output(db, run.id, "extract_spec")),
                  "Audit: " + _j(latest_output(db, run.id, "audit_repo")),
                  "Environment and data: " + _j(latest_output(db, run.id, "setup_env")),
                  f"Mode: {run.mode or inp.get('mode', 'A')}",
                  "Entry point contract: return entrypoints as command templates the Executor fills in. Placeholders: "
                  "{seed}, {budget_min} (minutes of training budget per run), {results_path} (write a JSON file there with "
                  '{"metrics": {name: number}, "param_count": int, "train_seconds": number, "status": "done"}), '
                  "{spec_args} (branch overrides as --key value). Put the working directory, relative to the project "
                  "workspace, in finish.output.workdir if it is not the workspace root."]
        mem.update(query=(run.goal or "") + " implementation", kind="config_outcome")
    elif tt in ("design_exploratory", "design_baseline_suite", "design_branches"):
        kind = inp.get("kind") or ("whatif" if tt == "design_branches" else "baseline")
        parts += [f"Propose branches of kind '{kind}' (plus 'transfer' if transfer=true). For baseline-kind branches on a "
                  "dataset with no Implementer, give spec.entrypoint (a command template, see placeholders below) and "
                  "spec.workdir.",
                  "Placeholders: {seed}, {budget_min}, {results_path}, {spec_args}.",
                  "Spec: " + _j(latest_output(db, run.id, "extract_spec")),
                  "Published baselines: " + _j(latest_output(db, run.id, "search_baselines")),
                  "Statistics so far: " + _j(run_stats(db, run.id), 6000), "Budget: " + _j(run.budget_json)]
        parts += [_input_view(q) for q in _inputs(db, run, "question")]
        mem.update(kind="config_outcome")
    elif tt in ("evaluate", "evaluate_final"):
        parts += ["Reference targets: " + _j(brief.get("reference_targets")),
                  "Spec (claim and metric): " + _j(latest_output(db, run.id, "extract_spec"), 3000),
                  "Repo-reported numbers: " + _j((latest_output(db, run.id, "audit_repo") or {}).get("reported_numbers")),
                  "Published baselines: " + _j(latest_output(db, run.id, "search_baselines"), 3000),
                  "Statistics (computed in code; use only these numbers): " + _j(run_stats(db, run.id), 12000)]
    elif tt == "write_report":
        from .tools import ledger_rows
        parts += ["Brief: " + _j({k: brief.get(k) for k in ("entry_types", "facts", "reference_targets")}),
                  "Verdicts: " + _j(latest_output(db, run.id, "evaluate_final") or latest_output(db, run.id, "evaluate"), 4000),
                  "Ledger (every entry must appear in why_differs): " + _j(ledger_rows(db, run.id), 6000),
                  "Branches and decisions: " + _j(_branches(db, run), 4000),
                  "Statistics: " + _j(run_stats(db, run.id), 8000)]
    elif tt == "debug":
        job = db.get(Job, inp.get("failed_job_id"))
        err = (job.stderr_tail or "") + "\n" + (job.stdout_tail or "") if job else ""
        parts += ["A job failed. Diagnose, fix, re-run it with create_job, and write a verified error_fix lesson if the "
                  "re-run passes. Set failure_origin_agent_id if the evidence shows which agent's output caused it.",
                  "Command: " + _j(inp.get("command")), "Recent history: " + _j(inp.get("history"), 2000)]
        if job:
            from .tools import job_result_view
            parts.append(job_result_view(job))
        mem.update(query=error_class(err), kind="error_fix", sig=signature("error_fix", error_class(err)))
    else:
        parts.append("Do the task described by your role.")
    return "\n\n".join(parts), mem


def pending_question(db: Session, approval_id: str) -> str:
    a = db.get(Approval, approval_id)
    return a.payload_json.get("question", "") if a else ""
