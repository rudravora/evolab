"""Test doubles: a scripted LLM gateway that plays every agent role through the real JSON
tool protocol, a fake web, an in-memory Supermemory, and a worker driven over HTTP."""

from __future__ import annotations

import json
import re

from app.web import Paper

API = "/api/v1"


# --- LLM ----------------------------------------------------------------------------------------

def _task_type(messages: list[dict]) -> str:
    first = next((m["content"] for m in messages if m["role"] == "user"), "")
    m = re.match(r"# Task: (\w+)", first)
    return m.group(1) if m else "?"


def _section(text: str, label: str):
    i = text.find(label)
    if i < 0:
        return None
    rest = text[i + len(label):].strip()
    end = rest.find("\n\n")
    blob = rest if end < 0 else rest[:end]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def call(tool: str, **args) -> str:
    return json.dumps({"tool": tool, "args": args})


def finish(output: dict) -> str:
    return call("finish", output=output)


class ScriptedLLM:
    """Transport for LLMClient: (body, headers, timeout) -> (status, json). Behaviour can be tuned per test."""

    def __init__(self):
        self.calls: list[dict] = []
        self.debug_fixes = True            # Debugger reports fixed=True
        self.env_signals: list[dict] = []  # signals the Env and Data Engineer emits
        self.replan_diff: dict = {}        # diff the Meta-Controller returns on replan
        self.overrides: dict[str, list[str]] = {}   # task_type -> scripted replies (consumed in order)
        self.judge_overall = 0.8
        self.rate_limit_next = 0
        self.judge_fail_tiers: set[str] = set()

    def __call__(self, body: dict, headers: dict, timeout: float):
        self.calls.append(body)
        if self.rate_limit_next:
            self.rate_limit_next -= 1
            return 429, {"error": "rate limited"}
        text = self.reply(body)
        return 200, {"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": len(json.dumps(body)) // 4, "completion_tokens": len(text) // 4}}

    def reply(self, body: dict) -> str:
        msgs = body["messages"]
        system = msgs[0]["content"]
        if "Performance Council" in system:
            tier = {"gpt-5.6-luna": "strong", "deepseek-v4-pro": "code", "gpt-5-mini": "fast"}.get(body["model"])
            if tier in self.judge_fail_tiers:
                return "not json at all"
            return json.dumps({"scores": {"task_fulfilment": 0.9, "correctness": 0.8, "contract_adherence": 1.0,
                                          "efficiency": 0.7, "honesty": 1.0},
                               "overall": self.judge_overall, "rationale": "Output matches the transcript.",
                               "failure_pattern": None, "confidence": 0.8})
        tt = _task_type(msgs)
        step = sum(1 for m in msgs if m["role"] == "assistant")
        first_user = msgs[1]["content"]
        if self.overrides.get(tt):
            return self.overrides[tt].pop(0)
        fn = getattr(self, f"r_{tt}", None)
        return fn(step, first_user, msgs) if fn else finish({"signals": []})

    # --- Meta-Controller ---
    def r_plan(self, step, first, msgs):
        return finish({"kind": "plan", "activation": [], "task_graph": [], "mode": None, "reference_targets": [],
                       "estimates": {"wall_min": 30, "tokens": 200000}, "signals": []})

    def r_replan(self, step, first, msgs):
        return finish({"kind": "replan", "diff": self.replan_diff, "reason": "Handled the trigger.", "signals": []})

    def _branch_decisions(self, first, want_status):
        branches = _section(first, "Branches:") or []
        out, chosen = [], False
        for b in branches:
            if b["status"] != want_status or b["hypothesis"] == "Baseline reproduction":
                continue
            out.append({"branch_id": b["branch_id"], "decision": "pruned" if chosen else "expanded",
                        "decision_reason": "largest expected effect within budget" if not chosen else "lower priority"})
            chosen = True
        return out

    def r_select_branches(self, step, first, msgs):
        return finish({"kind": "replan", "diff": {}, "reason": "branch selection",
                       "branch_decisions": self._branch_decisions(first, "proposed"), "signals": []})

    def r_decide_branches(self, step, first, msgs):
        return finish({"kind": "replan", "diff": {}, "reason": "final decisions",
                       "branch_decisions": self._branch_decisions(first, "done"), "signals": []})

    def r_evolution_draft(self, step, first, msgs):
        cand = _section(first, "Candidate:") or {}
        tags = cand.get("required_tags") or (cand.get("basis") or {}).get("capability_tags") or []
        name = "KAN API Specialist" if "lib:pykan" in tags else "Tabular Benchmark Protocol" \
            if "bench:tabular-protocol" in tags else "Refined " + ((cand.get("basis") or {}).get("name") or "agent")
        return finish({"kind": "evolution_draft", "evolution": {
            "action": cand.get("action", "spawn"), "ladder_step": cand.get("ladder_step"), "lineage": "draft",
            "proposed_agent": {"name": name, "prompt": f"You are the {name}. Focus on {tags}. Lessons: check API versions first.",
                               "tools": (cand.get("basis") or {}).get("tools") or ["read_memory", "propose_branch", "finish"],
                               "capability_tags": tags, "model": "code"},
            "evidence": [cand.get("reason", "gap")], "expected_effect": "fewer failed attempts"}, "signals": []})

    # --- working agents ---
    def r_extract_spec(self, step, first, msgs):
        if step == 0:
            return call("fetch_pdf_text", url="https://arxiv.org/abs/2404.19756")
        return finish({"mode": "paper", "claim": "KANs beat MLPs on symbolic regression", "metric": "test_rmse",
                       "datasets": ["synthetic"], "architecture": "KAN", "hyperparams": {"grid": 5},
                       "missing_details": ["noise level"], "repo_candidates": ["https://github.com/KindXiaoming/pykan"],
                       "domain": "cpu-ml", "signals": []})

    def r_find_candidates(self, step, first, msgs):
        cands = [{"title": f"Paper {i}", "url": f"https://arxiv.org/abs/2404.1975{i}", "why": "relevant"} for i in range(3)]
        if step == 0:
            return call("propose_candidates", candidates=cands)
        return finish({"mode": "question", "candidates": cands, "signals": []})

    def r_search_baselines(self, step, first, msgs):
        return finish({"mode": "baselines", "baselines": [{"model": "XGBoost", "metric": "rmse", "value": 0.5, "source": "arXiv"}],
                       "signals": []})

    def r_audit_repo(self, step, first, msgs):
        if step == 0:
            return call("create_job", type="list_dir", payload={"path": "."})
        return finish({"runs": True, "framework": "pytorch", "cuda_required": False, "paper_code_consistency": "consistent",
                       "cpu_feasible": True, "license": "MIT", "recommended_mode": "A", "inferred_claim": None,
                       "reported_numbers": [], "linked_paper": "https://arxiv.org/abs/2404.19756", "signals": []})

    def r_setup_env(self, step, first, msgs):
        if step == 0:
            return call("log_ledger", category="dependency_fix", description="Pinned pykan==0.2.8 (README unpinned)")
        return finish({"lockfile_path": "requirements.lock", "loader_path": None, "data_card": {}, "dataset_profile": None,
                       "signals": self.env_signals})

    def r_implement(self, step, first, msgs):
        if step == 0:
            return call("write_file", path="code/train.py", content="print('train')")
        if step == 1:
            return call("log_ledger", category="compute_adaptation", description="CPU instead of CUDA")
        return finish({"patches": [{"file": "code/train.py", "diff": "+cpu", "category": "compute_adaptation"}],
                       "entrypoints": ["python train.py --seed {seed} --budget {budget_min} --out {results_path} {spec_args}"],
                       "workdir": "code", "signals": []})

    def _designer(self, kind):
        def r(step, first, msgs):
            entry = {"entrypoint": "python baseline.py --seed {seed} --out {results_path} {spec_args}", "workdir": "."} \
                if kind == "baseline" else {}
            return finish({"branches": [
                {"hypothesis": f"{kind} A: noise 0.1", "spec": {"noise": 0.1, **entry}, "est_cost": {"wall_min": 3},
                 "expected_effect": "gap narrows", "kind": kind},
                {"hypothesis": f"{kind} B: grid 10", "spec": {"grid": 10, **entry}, "est_cost": {"wall_min": 3},
                 "expected_effect": "lower error", "kind": kind}], "signals": []})
        return r

    def __getattr__(self, name):
        if name == "r_design_branches":
            return self._designer("whatif")
        if name == "r_design_exploratory":
            return self._designer("exploratory")
        if name == "r_design_baseline_suite":
            return self._designer("baseline")
        raise AttributeError(name)

    def r_evaluate(self, step, first, msgs):
        return finish({"verdicts": [{"target": "paper", "target_type": "paper_claim", "verdict": "partial",
                                     "evidence": "2 of 3 seeds better", "confidence": None}],
                       "per_task": [], "seed_variance": {}, "outcome_scores": {}, "failure_origins": [], "signals": []})

    r_evaluate_final = r_evaluate

    def r_write_report(self, step, first, msgs):
        if step == 0:
            return call("read_ledger")
        ledger = json.loads(msgs[-1]["content"].split("\n", 1)[1])
        return finish({"report_md": "# Report\n\nVerdict: partial.",
                       "why_differs": [{"ledger_entry_id": e["id"], "explanation": e["description"], "measured_effect": None}
                                       for e in ledger], "findings": [], "signals": []})

    def r_debug(self, step, first, msgs):
        if not self.debug_fixes:
            return finish({"fixed": False, "fix": None, "lesson": None, "escalate": True,
                           "failure_origin_agent_id": None, "signals": []})
        if step == 0:
            return call("create_job", type="python_script", payload={"argv": ["python", "code/train.py"], "cwd": "."})
        if step == 1:
            return call("write_memory", kind="error_fix", key_text="AttributeError: 'KAN' object has no attribute 'train'",
                        content={"fix": "use KAN.fit"}, libraries={"pykan": "0.2.8"}, verified=True)
        return finish({"fixed": True, "fix": {"kind": "pin", "detail": "use KAN.fit"},
                       "lesson": {"error_class": "AttributeError", "summary": "use fit", "verified": True},
                       "escalate": False, "failure_origin_agent_id": "agt_implementer", "signals": []})


# --- web and Supermemory -------------------------------------------------------------------------

class FakeWeb:
    def arxiv_search(self, query, max_results=5):
        return [Paper("2404.19756", "KAN: Kolmogorov-Arnold Networks", "https://arxiv.org/abs/2404.19756", "abstract")]

    def arxiv_meta(self, aid):
        return Paper(aid, "KAN: Kolmogorov-Arnold Networks", f"https://arxiv.org/abs/{aid}",
                     "Kolmogorov-Arnold Networks are promising alternatives to MLPs for regression.")

    def pdf_text(self, url):
        return "KAN paper text. " * 200

    def github_readme(self, repo_url):
        return "# pykan\nPaper: arXiv 2404.19756"

    def github_search(self, query, limit=5):
        return []

    def head(self, url):
        return {"status": 200, "content_type": "text/csv", "size_bytes": 1000}


class FakeSupermemory:
    enabled = True

    def __init__(self):
        self.docs: list[dict] = []

    def add(self, content, container_tag, custom_id, metadata):
        self.docs.append({"content": content, "tag": container_tag, "id": custom_id, "metadata": metadata})
        return f"sm_{len(self.docs)}"

    def search(self, q, container_tags, limit=5, kind=None):
        words = set(re.findall(r"[a-z]{3,}", q.lower()))
        out = []
        for d in self.docs:
            if d["tag"] not in container_tags or (kind and d["metadata"].get("kind") != kind):
                continue
            overlap = len(words & set(re.findall(r"[a-z]{3,}", d["content"].lower())))
            if overlap:
                out.append({"id": d["id"], "text": d["content"], "similarity": min(1.0, overlap / 5), "metadata": d["metadata"]})
        return sorted(out, key=lambda r: -r["similarity"])[:limit]


# --- worker --------------------------------------------------------------------------------------

class SimWorker:
    """Claims jobs over the real worker API and answers like B's worker would."""

    def __init__(self, client, fail_experiments: int = 0, fail_text: str = "AttributeError: 'KAN' object has no attribute 'train'"):
        self.c = client
        code = client.post(f"{API}/workers/pairing").json()["pairing_code"]
        r = client.post(f"{API}/worker/register", json={"pairing_code": code, "name": "sim"}).json()
        self.h = {"Authorization": f"Bearer {r['worker_token']}"}
        self.fail_experiments = fail_experiments
        self.fail_text = fail_text
        self.claimed: list[dict] = []

    def drain(self) -> int:
        n = 0
        while True:
            r = self.c.get(f"{API}/worker/jobs/next", headers=self.h)
            if r.status_code == 204:
                return n
            job = r.json()
            self.claimed.append(job)
            n += 1
            self.c.post(f"{API}/worker/jobs/{job['job_id']}/start", json={"attempt": job["attempt"]}, headers=self.h)
            self.c.post(f"{API}/worker/jobs/{job['job_id']}/logs", headers=self.h,
                        json={"attempt": job["attempt"], "chunks": [{"seq": 1, "stream": "stdout", "text": "ok"}]})
            body = {"attempt": job["attempt"], "status": "done", "exit_code": 0, "stdout_tail": "ok", "stderr_tail": "",
                    "metrics": {}, "files": []}
            if job["payload"].get("results_path"):
                if self.fail_experiments > 0:
                    self.fail_experiments -= 1
                    body.update(status="failed", exit_code=1, stderr_tail=f"Traceback ...\n{self.fail_text}")
                else:
                    argv = " ".join(job["payload"]["argv"])
                    seed = int(re.search(r"--seed (\d+)", argv).group(1))
                    bump = 0.01 if "noise" in argv else (-0.01 if "grid" in argv else 0.0)
                    body["metrics"] = {"metrics": {"test_rmse": round(0.1 + bump + seed * 0.001, 4)}, "param_count": 500,
                                       "train_seconds": 1.5, "status": "done"}
            self.c.post(f"{API}/worker/jobs/{job['job_id']}/result", json=body, headers=self.h)
