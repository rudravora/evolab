"""Intake: facts detection and the Research Brief (WORKFLOW stage 1, ARCHITECTURE 3.0a, D-029).

Deterministic: classify inputs, fetch metadata (arXiv title and abstract, README text,
dataset HEAD), detect links between inputs, choose a domain tag and rank reference
targets. Runs in the background (never inside the request). Fetched text is untrusted
and only used for matching; it never becomes an instruction.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .events import emit
from .models import Input, Run
from .web import FetchError, arxiv_id

log = logging.getLogger("evolab.intake")

DOMAIN_KEYWORDS = {
    "materials": ["crystal", "materials", "matbench", "cif", "lattice", "alloy", "dft"],
    "edge-ml": ["quantiz", "pruning", "distill", "latency", "edge device", "mobile", "sparsity"],
    "3d": ["point cloud", "mesh", "voxel", "nerf", "multi-view", "3d"],
    "cpu-ml": ["kan", "kolmogorov", "tabular", "mlp", "pinn", "symbolic", "spline", "regression"],
}
TARGET_RANK = {"paper_claim": 1, "repo_reported": 2, "published_baseline": 3, "internal_baseline": 4}
STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "via", "using", "into", "real", "data", "on", "of", "do", "does"}


def _words(text: str) -> set[str]:
    """Lower-case content words with a light plural stem ("KANs" matches "KAN", "MLPs" matches "MLP")."""
    out = set()
    for w in re.findall(r"[a-z][a-z0-9]{1,}", (text or "").lower()):
        if w in STOP or len(w) < 3:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return out


def _dataset_name(ref: str) -> str:
    tail = re.split(r"[/\\]", ref.rstrip("/"))[-1]
    return re.sub(r"\.(csv|tsv|json|parquet|zip|txt)$", "", tail, flags=re.I)


def fetch_metadata(db: Session, services, run: Run) -> None:
    """Background fetch; failures are recorded as facts, never fatal."""
    for inp in db.scalars(select(Input).where(Input.project_id == run.project_id)):
        meta = dict(inp.meta_json or {})
        if meta.get("fetched"):
            continue
        try:
            if inp.kind == "paper" and inp.source == "url":
                aid = arxiv_id(inp.ref)
                if aid:
                    paper = services.web.arxiv_meta(aid)
                    if paper:
                        meta.update(arxiv_id=aid, title=paper.title, abstract=paper.abstract[:2000])
            elif inp.kind == "repo" and inp.source == "url":
                readme = services.web.github_readme(inp.ref)
                if readme:
                    meta.update(readme_excerpt=readme[:6000], readme_arxiv_ids=sorted(set(re.findall(r"\d{4}\.\d{4,5}", readme))))
            elif inp.kind == "dataset" and inp.source == "url":
                meta.update(head=services.web.head(inp.ref))
        except (FetchError, Exception) as exc:  # noqa: BLE001 - a failed fetch is a fact, not a crash
            meta["fetch_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        meta["fetched"] = True
        inp.meta_json = meta


def build_brief(db: Session, run: Run) -> dict:
    inputs = list(db.scalars(select(Input).where(Input.project_id == run.project_id).order_by(Input.created_at)))
    by_kind: dict[str, list[Input]] = {}
    for i in inputs:
        by_kind.setdefault(i.kind, []).append(i)
    facts: list[dict] = []
    papers, repos, datasets, questions = (by_kind.get(k, []) for k in ("paper", "repo", "dataset", "question"))

    for p in papers:
        m = p.meta_json or {}
        facts.append({"fact": "paper_present", "evidence": m.get("title") or p.ref, "input_id": p.id})
        if m.get("fetch_error"):
            facts.append({"fact": "paper_fetch_failed", "evidence": m["fetch_error"], "input_id": p.id})
    for r in repos:
        m = r.meta_json or {}
        facts.append({"fact": "repo_present", "evidence": r.ref, "input_id": r.id})
        for p in papers:
            aid = (p.meta_json or {}).get("arxiv_id") or arxiv_id(p.ref)
            if aid and aid in (m.get("readme_arxiv_ids") or []):
                facts.append({"fact": "repo_links_paper", "evidence": f"README cites arXiv {aid}", "input_id": r.id})
                break
        else:
            if papers:
                facts.append({"fact": "repo_not_linked_to_paper", "evidence": "README does not cite the supplied paper",
                              "input_id": r.id})
            elif m.get("readme_arxiv_ids"):
                facts.append({"fact": "repo_links_unsupplied_paper",
                              "evidence": f"README cites arXiv {m['readme_arxiv_ids'][0]}", "input_id": r.id})
    for d in datasets:
        facts.append({"fact": "dataset_present", "evidence": d.ref, "input_id": d.id})
        name = _dataset_name(d.ref).lower()
        for p in papers:
            text = ((p.meta_json or {}).get("title", "") + " " + (p.meta_json or {}).get("abstract", "")).lower()
            if name and len(name) > 2 and name in text:
                facts.append({"fact": "dataset_in_paper", "evidence": f"'{name}' appears in the paper abstract", "input_id": d.id})
            else:
                facts.append({"fact": "dataset_not_in_paper", "evidence": "dataset name absent from paper title and abstract",
                              "input_id": d.id})
    for q in questions:
        facts.append({"fact": "question_present", "evidence": q.ref[:200], "input_id": q.id})
        qw = _words(q.ref)
        for p in papers:
            m = p.meta_json or {}
            overlap = sorted(qw & _words(m.get("title", "") + " " + m.get("abstract", "")[:1500]))
            if overlap:
                facts.append({"fact": "question_about_paper",
                              "evidence": f"question shares terms with the paper: {overlap[:4]}", "input_id": q.id})
                break

    targets: list[dict] = []
    for p in papers:
        targets.append({"type": "paper_claim", "source": p.id})
    for r in repos:
        targets.append({"type": "repo_reported", "source": r.id})
    if datasets and not papers:
        targets += [{"type": "published_baseline", "source": d.id} for d in datasets]
    if questions and not papers:
        targets.append({"type": "internal_baseline", "source": questions[0].id})
    targets.sort(key=lambda t: TARGET_RANK[t["type"]])
    for rank, t in enumerate(targets, 1):
        t["rank"] = rank

    corpus = " ".join([run.goal or ""] + [i.ref for i in inputs] +
                      [str((i.meta_json or {}).get("title", "")) + " " + str((i.meta_json or {}).get("abstract", ""))[:500]
                       for i in inputs]).lower()
    scores = {d: sum(corpus.count(k) for k in kws) for d, kws in DOMAIN_KEYWORDS.items()}
    domain = max(scores, key=scores.get) if max(scores.values()) > 0 else "general"
    return {"entry_types": sorted(set(by_kind) - {"note"}), "goal": run.goal,
            "inputs": [{"id": i.id, "kind": i.kind, "source": i.source, "ref": i.ref,
                        "title": (i.meta_json or {}).get("title")} for i in inputs],
            "facts": facts, "domain": domain, "reference_targets": targets}


def run_intake(db: Session, services, run: Run) -> dict:
    fetch_metadata(db, services, run)
    brief = build_brief(db, run)
    run.brief_json = brief
    run.entry_types_json = brief["entry_types"]
    emit(db, run.id, "intake", "intake.brief", {"entry_types": brief["entry_types"], "facts_count": len(brief["facts"]),
                                                "reference_targets": brief["reference_targets"]})
    return brief
