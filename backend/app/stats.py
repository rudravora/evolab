"""Statistics computed in code and passed to the Evaluator (WORKFLOW 5.1): the LLM writes
the judgement, never the numbers."""

from __future__ import annotations

import math
from statistics import mean, stdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Branch, Experiment


def summarize(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0}
    m = mean(values)
    sd = stdev(values) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 6), "std": round(sd, 6), "min": round(min(values), 6), "max": round(max(values), 6),
            "sem": round(sd / math.sqrt(n), 6) if n > 1 else None}


def run_stats(db: Session, run_id: str) -> dict:
    branches = list(db.scalars(select(Branch).where(Branch.run_id == run_id).order_by(Branch.created_at)))
    out: dict = {"branches": [], "baseline_branch_id": None}
    baseline = next((b for b in branches if b.parent_branch_id is None), None)
    if baseline:
        out["baseline_branch_id"] = baseline.id
    per_branch: dict[str, dict[str, dict]] = {}
    for b in branches:
        exps = list(db.scalars(select(Experiment).where(Experiment.branch_id == b.id)))
        done = [e for e in exps if e.status == "done" and e.metrics_json]
        metrics: dict[str, list[float]] = {}
        for e in done:
            for k, v in (e.metrics_json or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    metrics.setdefault(k, []).append(float(v))
        summary = {k: summarize(v) for k, v in metrics.items()}
        per_branch[b.id] = summary
        out["branches"].append({"branch_id": b.id, "hypothesis": b.hypothesis, "kind": b.kind, "status": b.status,
                                "spec": b.spec_json, "experiments": len(exps), "done": len(done),
                                "failed": sum(e.status == "failed" for e in exps),
                                "seeds": sorted(e.seed for e in done if e.seed is not None), "metrics": summary})
    base = per_branch.get(baseline.id) if baseline else None
    if base:
        for entry in out["branches"]:
            if entry["branch_id"] == baseline.id:
                continue
            deltas = {}
            for k, s in entry["metrics"].items():
                if s.get("n") and base.get(k, {}).get("n"):
                    d = s["mean"] - base[k]["mean"]
                    pooled = math.sqrt(((s["std"] or 0) ** 2 + (base[k]["std"] or 0) ** 2) / 2)
                    deltas[k] = {"delta": round(d, 6), "beyond_seed_variance": bool(pooled and abs(d) > 2 * pooled)}
            entry["delta_vs_baseline"] = deltas
    return out
