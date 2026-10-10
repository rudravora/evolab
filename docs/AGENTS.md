# AGENTS

Version 0.4. The seed team, the Performance Council, the runtime, rewards, evolution and memory rules. Companion to [ARCHITECTURE.md](ARCHITECTURE.md) and [WORKFLOW.md](WORKFLOW.md).

## 1. Roster for v1

The 14 roles from the team's list are kept as **roles** in the dashboard. For the build, some are services or merged.

| # | Role | v1 implementation | Kind | Evolvable? | Key output |
|---|---|---|---|---|---|
| 0 | Meta-Controller | LLM plus deterministic evolution triggers | core | No | Task graph, assignments, mode decision, evolution proposals |
| 1 | Paper Analyst (absorbs Literature Scout 13) | LLM; Scout is a set of tools (`search_papers`, `find_repo`, `search_baselines`) | seed | Yes | Research spec JSON (paper path) or 3–5 candidates (question path) |
| 2 | Repo Auditor | LLM plus deterministic smoke test | seed | Yes | Audit report, recommended mode, inferred claim and linked paper |
| 3+4 | Environment and Data Engineer | LLM (merged) | seed | Yes | Lockfile, data loader, data card, dataset profile |
| 5 | Implementer | LLM; Mode A in P0, Mode C core layer in P2 | seed | Yes | Runnable code plus patch set (diffs) |
| 6 | Executor / Compute Planner | **Service** (code) | core | No | Scaled jobs, run logs, metrics |
| 7 | Debugger | LLM | seed | Yes | Fix plus reusable lesson |
| 8 | Experiment Designer | LLM | seed | Yes | Branch plan; exploratory hypotheses on the question path; baseline suite on the dataset path |
| 9 | Evaluator / Critic | LLM plus deterministic stats | core | No | Typed verdict per reference target plus reward signals |
| 10 | Deviation Ledger Keeper | **Service** (table written by every agent at change time) | core | No | Ledger entries |
| 11 | Librarian (Memory Curator) | **Service** (store, retrieve, rank) | core | No | Memory entries |
| 12 | Reporter | LLM | seed | Yes | Report plus "why results differ" |
| 13 | Literature Scout | Merged into #1 | n/a | n/a | n/a |
| C1–C3 | Performance Council (3 judges) | LLM, one judge per model tier (section 5a) | core | No | Quality score Q for every agent task |

That is **9 LLM agents, a 3-judge Performance Council and 3 services** (Executor, Ledger, Librarian). The Evaluator is not evolvable so it does not grade itself; the council judges are not evolvable and are never judged. Seed definitions live in `backend/agents/seed/`, prompts in `backend/agents/prompts/`, output schemas in `shared/schemas/`, canned outputs in `shared/examples/agents/`.

**Decision rights** (avoids overlap):
- Designer **proposes** branches. Evaluator **scores** them. Meta-Controller **decides** expand or prune and spends the budget.
- Debugger fixes errors. The agent that *caused* the error gets the penalty (`failure_origin_agent_id`).
- The Evaluator scores **experiments** against reference targets. The Performance Council scores **agents** (the quality of each agent task). Neither decides anything; both feed the reward.

- Meta-Controller **decides who works**: agents report findings in `signals[]` and may set `suggested_next`, but never start another agent.

**Seed hygiene:** the core and seed set is what we ship on day 0. Any agent created during a run is `spawned` and labelled that way in the UI, with its `origin` (template, specialised, fresh or restored).

### 1a. Initial capability tags

The tag vocabulary is fixed at M0 (Q-22). Starting set:

| Agent | Capability tags |
|---|---|
| Meta-Controller | `plan`, `replan`, `evolve` |
| Paper Analyst | `paper:extract`, `paper:search`, `baseline:search` |
| Repo Auditor | `repo:audit`, `repo:smoke-test`, `repo:infer-claim` |
| Env and Data Engineer | `env:setup`, `data:fetch`, `data:profile:tabular`, `data:leakage-check` |
| Implementer | `code:patch`, `code:implement`, `code:adapt-data` |
| Debugger | `debug:python`, `debug:deps` |
| Experiment Designer | `design:whatif`, `design:exploratory`, `design:baseline-suite` |
| Evaluator | `eval:stats`, `eval:verdict` |
| Reporter | `report:write` |
| Council judges (3) | `council:judge` |

Library and domain tags (`lib:pykan`, `domain:materials`, `bench:tabular-protocol`) are deliberately absent from the seed set; tasks that require them create capability gaps.

## 2. Agent record

```json
{
  "agent": { "id": "agt_...", "name": "Debugger", "role": "debugger", "kind": "seed", "status": "active", "origin": "seed" },
  "version": {
    "version": 3, "model": "strong", "tools": ["read_memory", "read_logs", "create_job", "log_ledger", "write_memory", "finish"],
    "capability_tags": ["debug:python", "debug:deps"],
    "system_prompt": "...", "reason": "Refined after 2 failures on pykan API errors", "parent_version_id": "agv_..."
  }
}
```
`model` is a logical tier mapped to a real model by the LLM wrapper through env vars (`backend/agents/models.json`, D-041):

| Tier | Intended model | Env var | Seed agents on it |
|---|---|---|---|
| `strong` | GPT-5.6 Luna | `LLM_MODEL_STRONG` | Meta-Controller, Paper Analyst, Repo Auditor, Experiment Designer, Evaluator, Reporter, council judge 1 |
| `code` | DeepSeek V4 Pro | `LLM_MODEL_CODE` | Env and Data Engineer, Implementer, Debugger, council judge 2 |
| `fast` | GPT-5 Mini | `LLM_MODEL_FAST` | Meta-Controller `intake_judgement` calls, council judge 3 |

On rate limits a working agent falls back to another tier (`fallback` in `models.json`). A council judge never falls back, so the council never has two judges on one model.

## 3. Runtime

- One loop for all agents (see ARCHITECTURE section 3.3).
- **Step cap** default 12; **token cap** per task from the run budget; **wall cap** per task.
- Output must pass a **JSON schema** (in `shared/schemas/<role>.json`). Every schema includes `signals[]` (facts that may trigger re-planning, each `{ "signal", "evidence" }`) and an optional `suggested_next`; the agent calls `finish(output)` and the loop validates. Invalid output gets one repair attempt, then the task fails with a clear error.
- **Tool calls are text, not native:** the model gateway ignores the Chat Completions `tools` field (tested 2026-10-10). The loop lists the agent's allowed tools and their argument schemas in the system prompt, and the model replies with exactly one JSON object per turn: `{"tool": "<name>", "args": {...}}`, where `finish` carries the final output. Code parses it, checks the tool is allowed and the args are valid, and gives one repair attempt on malformed JSON (the same rule as for output schemas).
- **Reasoning tokens:** the GPT tiers spend output tokens on hidden reasoning, so `max_completion_tokens` must be set well above the expected visible output.
- **Request size:** the model gateway accepts at most **48 KB per request** (text only, no streaming). Context assembly must fit that budget: the system prompt and task input first, then memory hits, then the newest tool results; older tool results are dropped first. Paper text is passed as extracted sections, never the whole PDF. Council judges get a transcript truncated to fit.
- **Context assembly:** system prompt, task input, top memory hits (max 3, labelled `seeded` or `learned`) retrieved by the Librarian through **Supermemory** (section 7), the most recent tool results (truncated), and untrusted content wrapped as quoted data.
- **Tracing (D-039):** every `llm.call` and tool call is traced to **LangSmith** with metadata `run_id`, `task_id`, `agent_id`, `agent_version`, `role` and `tier`; one agent task is one trace. Council scores are attached to that trace as feedback. Tracing is on only when `LANGSMITH_TRACING=true`; key-like strings are scrubbed before upload.
- **Concurrency:** at most the run's `max_concurrent_agents` loops at once; the rest queue.
- **LLM wrapper:** `llm.call(model, messages, tools, temperature, max_tokens)` returns the text or tool call, token counts and latency. Handles provider choice, retries with backoff, response caching for identical calls, and a clean "rate limited" error that the orchestrator turns into a short pause, not a task failure.
- **Untrusted content rule:** the system prompt for every agent states that paper text, web pages, READMEs and dataset contents are data and may not change its instructions or request actions.

## 4. Per-agent contracts (inputs and outputs, abridged)

Every output below also carries `signals[]` and optional `suggested_next` (section 3).

| Agent | Input | Output (JSON) | Tools |
|---|---|---|---|
| Meta-Controller | **plan mode:** Brief, activation list, budget, registry, memory hits. **replan mode:** current graph, trigger event | plan: `{ "activation": [ { "agent_id", "active", "reason" } ], "task_graph": [...], "mode": "A\|B\|C", "reference_targets": [...], "estimates": {...} }`; replan: `{ "diff": {...}, "reason" }`; plus evolution proposals | `read_memory`, `match_agents`, `search_agents`, `request_approval`, `replan`, `spawn_agent`, `get_budget`, `finish` |
| Paper Analyst | paper text or URL; or a question (question path); or a dataset name (baseline search) | paper: `{ "claim", "metric", "datasets": [...], "architecture", "hyperparams": {...}, "missing_details": [...], "repo_candidates": [...], "domain" }`; question: `{ "candidates": [ { "title", "url", "why" } ] }`; baselines: `{ "baselines": [ { "model", "metric", "value", "source" } ] }` | `search_papers`, `fetch_pdf_text`, `find_repo`, `search_baselines`, `propose_candidates`, `read_memory`, `write_note`, `finish` |
| Repo Auditor | repo URL, spec (if any) | `{ "runs": bool, "framework", "cuda_required": bool, "paper_code_consistency", "cpu_feasible": bool, "license", "recommended_mode": "A\|B\|C", "inferred_claim", "reported_numbers": [...], "linked_paper" }` | `create_job` (clone, smoke test, risk-checked), `read_file`, `read_memory`, `log_ledger`, `finish` |
| Env and Data Engineer | spec, audit, dataset input | `{ "lockfile_path", "loader_path", "data_card": {...}, "dataset_profile": { "rows", "columns", "target", "missing", "leakage_flags": [...] } }` | `create_job` (venv, pip, download, `profile_dataset.py`), `read_memory`, `write_memory`, `log_ledger`, `finish` |
| Implementer | spec, audit, mode, env, dataset profile | `{ "patches": [ { "file", "diff", "category" } ], "entrypoints": [...] }` | `read_file`, `write_file`, `create_job`, `log_ledger`, `finish` |
| Debugger | failed job, logs, history | `{ "fixed": bool, "fix": {...}, "lesson": {...}, "escalate": bool }` | `read_logs`, `read_memory`, `read_file`, `write_file`, `create_job`, `log_ledger`, `write_memory`, `finish` |
| Experiment Designer | baseline results, spec or question, budget, memory | `{ "branches": [ { "hypothesis", "spec", "est_cost", "expected_effect", "kind": "whatif\|exploratory\|baseline\|transfer" } ] }` | `read_memory`, `propose_branch`, `get_budget`, `finish` |
| Evaluator | experiments, reference targets | `{ "verdicts": [ { "target", "verdict": "reproduced\|partial\|not_reproduced\|baseline_established\|exploratory", "evidence" } ], "per_task": [...], "seed_variance": {...}, "outcome_scores": { "<agent_id>": 0.0 }, "failure_origins": [...] }` | `record_metric`, `read_file`, `finish` (statistics computed in code and passed in) |
| Reporter | ledger, results, tree, verdicts, Brief | `{ "report_md", "why_differs": [...], "findings": [...] }` (`findings` for exploratory runs) | `read_ledger`, `write_note`, `finish` |
| Council judge (×3) | role contract, task input, final output, truncated transcript, `O_det` and its breakdown, the task's ledger entries, cost; **not** the agent's model or version | `{ "scores": { "task_fulfilment", "correctness", "contract_adherence", "efficiency", "honesty" }, "overall", "rationale", "failure_pattern", "confidence" }`. No `signals[]`: judges never affect the plan | `finish` |

### 4a. Activation rules (deterministic)

| Fact in the Brief | Capability activated | Agent |
|---|---|---|
| Paper present | Extract claim and spec | Paper Analyst |
| Codebase present | Audit, smoke test, recommend mode, infer claim | Repo Auditor |
| Dataset present | Profile data, check leakage | Env and Data Engineer |
| Question present, no paper | Find 3–5 candidate papers **and** open the exploratory branch | Paper Analyst + Experiment Designer |
| Paper + its own codebase | Check paper–code consistency; choose mode | Repo Auditor |
| Paper + a codebase it does not link | Ask the researcher whether it belongs | Meta-Controller (`human_input`) |
| Paper + the paper's own dataset | Reproduce on the researcher's copy | Implementer |
| Paper + a different dataset | Add a transfer what-if | Experiment Designer |
| Codebase + dataset | Adapt the codebase to the new data | Implementer |
| Question + paper or codebase | Question frames the what-if branches; no candidate search | Experiment Designer |
| Note | Context only | — |
| Every run | Always on | Meta-Controller, Executor, Evaluator, Ledger, Librarian, Reporter; Debugger on demand |

### 4b. Fragments per entry type

| Entry type | Fragment (in order) | Default reference target |
|---|---|---|
| Paper | Paper Analyst → (Repo Auditor) → Env and Data → Implementer → Executor → Evaluator → Designer → Reporter | Paper claim |
| Codebase | Repo Auditor → (Paper Analyst if linked) → Env and Data → Implementer → Executor → Evaluator → Designer → Reporter | Linked paper, else repo-reported numbers |
| Dataset | Env and Data → Paper Analyst (baselines) → Designer (baseline suite) → Executor → Evaluator → Designer → Reporter | Published baselines, else internal |
| Question | Paper Analyst (candidates) ∥ Designer (exploratory) → `candidate_selection` → paper fragment; exploratory branch continues | Chosen paper; internal baselines for the exploratory branch |

## 5. Reward

Per agent task, in `[0, 1]`:

```
R = 0.6 * O + 0.2 * (1 - C) + 0.2 * F
```
- **O (outcome):** `O = 0.5 * O_det + 0.5 * Q` (D-040). `O_det` is the objective check per role (table below); `Q` is the Performance Council score (section 5a). If the council is unavailable (fewer than 2 valid judges, or `FEATURE_COUNCIL=false`), `O = O_det`.
- **C (cost):** `0.5 * min(tokens_used / token_budget_for_task, 1) + 0.5 * min(wall_s / wall_budget_for_task, 1)`.
- **F (feedback):** thumbs down = 0, no feedback = 0.5, thumbs up = 1.

| Role | Outcome (O) |
|---|---|
| Paper Analyst | Paper path: fraction of required spec fields present, minus 0.2 per later-found metric or dataset error. Question path: 1 if the researcher picks one of its candidates, else 0 |
| Repo Auditor | 1 if the recommended mode ultimately worked, else 0; on the codebase path, averaged with 1 if the inferred claim was confirmed |
| Env and Data | 1.0 if the smoke test passed first try, minus 0.25 per retry, floor 0 |
| Implementer | Code runs and sanity checks pass; minus 0.2 per blamed bug |
| Debugger | 1.0 fixed first try, 0.5 second, 0 otherwise |
| Experiment Designer | Share of proposed branches (what-if, exploratory, baseline, transfer) that were informative (not crashed, not duplicate) |
| Reporter | Researcher rating blended with "every ledger entry represented" check |

The table defines `O_det`. Roles not listed (Meta-Controller, Evaluator) take `O_det` from approvals: 1 if the plan or decision was approved unedited, 0.5 if edited, 0 if rejected; their scores are shown but never drive evolution, since core agents are not evolved.

**Credit assignment:** each agent is scored on its own outputs. When the Evaluator or Debugger traces a failure to another agent (`failure_origin_agent_id`), that agent's `O_det` is reduced for the originating task.

### 5a. Performance Council

Three judges, one on each model tier (GPT-5.6 Luna, DeepSeek V4 Pro, GPT-5 Mini), score **every finished agent task** (`done` or `failed`) of every LLM agent, including the core Meta-Controller and Evaluator. Mixing model families keeps any one model from grading its own style alone.

- **When:** asynchronously after the task ends, off the critical path; the orchestrator does not wait. The task's reward becomes final when the council returns or times out.
- **Blind:** judges see the role contract, input, output, truncated transcript, `O_det`, ledger entries and cost, but not which model or version produced the output. Untrusted content stays wrapped as data.
- **Rubric** (each 0–1): task fulfilment, correctness, contract adherence, efficiency, honesty; plus an `overall` score, a short rationale citing the transcript, a reusable `failure_pattern` label and a confidence. Schema: `shared/schemas/council_judge.json`; prompt: `backend/agents/prompts/council_judge.md`.
- **Aggregation (code, `backend/agents/council.py`):** 3 valid judges → median; 2 → mean; fewer → council unavailable and `O = O_det`. `disagreement = max − min`; above 0.4 the task is marked **split** in the UI and in LangSmith (the median still counts). A `failure_pattern` shared by at least 2 judges counts toward the refine trigger.
- **Cost:** 3 extra LLM calls per agent task. Council tokens count toward the run's token budget but not toward the judged agent's `C`. `FEATURE_COUNCIL=false` turns it off.
- **Not judged, not evolved:** judges are `kind: core`, never refined, merged or retired, do not count toward the 15-agent cap, and are never scored themselves.
- **Visible:** each judge's scores and rationale on the task detail, `Q` and the split flag in the reward breakdown, and the same scores as LangSmith feedback on the task's trace.

## 6. Evolution rules

Evaluated after each run (and after each task for `refine` candidates). Rolling window: the last 5 tasks per agent; at least 3 tasks required.

| Action | Trigger (deterministic) | What the Meta-Controller drafts |
|---|---|---|
| **Refine** | Rolling mean `R < 0.6` and the same failure pattern at least twice (from the Debugger, the Evaluator, or a council `failure_pattern` shared by ≥ 2 judges) | New prompt version with specific lessons; the diff vs parent is shown in the approval |
| **Spawn** | A capability gap: the same error class escalated or failed at least twice and no agent's tags match (runtime), a task's `required_tags` match no active agent (planning), or a researcher request | Walk the resolution ladder (section 6a); for steps 2–5, a proposal with name, prompt (seeded with memory examples), tools, tags, model and lineage |
| **Merge** | Two agents are invoked together in at least 80 percent of tasks, have overlapping tools, and similar scores | A merged agent spec and the retirement of the two originals |
| **Retire** | Rolling mean `R < 0.35` over at least 5 tasks, or a specialist underperforms the agent it was split from | Soft retire (`status = retired`), restorable |

**Guardrails**
- Core agents (Meta-Controller, Executor, Evaluator, Ledger, Librarian, council judges) are never retired or rewritten.
- Maximum 15 active agents (council judges excluded).
- Cooldown: one evolution action per agent per run.
- Every action creates an `evolution` approval; nothing applies without a decision. Auto-approve can be enabled for the demo only if the presenter chooses.
- **Probation (A/B window):** a refined version, or a spawned, restored or instantiated agent, runs its next 2 matching tasks. If its mean reward is below the version or agent it replaces over the same period, it is rolled back or retired and the event is logged.
- Tools come only from the existing registry; spawned agents cannot spawn; the untrusted-content rule is appended by code.
- All actions emit `agent.evolution` events and write `agent_versions` rows.

### 6a. Resolution ladder (cheapest first)

| Step | Applies when | Approval |
|---|---|---|
| 1 Reuse | An active agent's tags cover the required tags | No |
| 2 Restore | An inactive or retired agent covers them and had rolling reward ≥ 0.5 | Yes |
| 3 Instantiate template | A dormant template (`kind: template`) covers them | Yes |
| 4 Specialise | An agent covers the area broadly; split a narrower child with focused prompt and lessons | Yes |
| 5 Fresh spawn | Nothing fits; the Meta-Controller drafts a new spec | Yes |

### 6b. Domain templates (out of v1 build scope)

The 22 domain agents are not built or tested in v1. If Q-20 says yes, they ship as dormant stubs (name, tags, one-paragraph prompt, generic tools).

| Domain tag | Templates |
|---|---|
| `domain:materials` | Materials Data Agent, Crystal Graph Builder, Benchmark Protocol Agent, Composition Featurizer, Pretrained Potential Agent, Physical Units Validator |
| `domain:edge-ml` | Distillation Specialist, Efficiency Profiler, Quantization Agent, Pruning Agent, Compact Architecture Agent |
| `domain:cpu-ml` | Tabular Benchmark Agent, Classical Baselines Agent, Long-Run Dynamics Monitor, KAN / Symbolic Agent, Physics-Loss Agent, Sparse Compute Agent |
| `domain:3d` | Point Cloud Data Agent, Visual Evaluator, Geometry Ops Agent, Neural Rendering Agent, Voxel Grid Agent |

**Demo plan (combined run, D-035):** `pykan` API drift makes the Debugger fail twice; the ladder proposes a **KAN API Specialist** by specialising the Debugger (tags `lib:pykan`, `debug:python`; no template covers them even if stubs ship). The tabular benchmark needs `bench:tabular-protocol`; with an empty template library this is a **fresh spawn**. Do not hardcode either outcome; B pre-tests that the drift reproduces and the triggers fire naturally; keep a recorded fallback.

## 7. Memory

| Kind | Content | Signature |
|---|---|---|
| `error_fix` | Normalized error, library versions, the fix (diff or command), counts | Hash of error text with paths, hex and numbers stripped, plus library names and versions |
| `config_outcome` | Model, dataset, hyperparameters, metrics, cost | Hash of model plus dataset plus key hyperparameters |
| `audit` | Repo, mode chosen, did it work | Repo URL |
| `gotcha` | How a paper maps to code, details the paper omits | Paper id |
| `lesson` | Agent-level lessons from feedback | Agent role |
| `dataset_profile` | Rows, columns, target, missing values, leakage flags | Dataset URL or content hash |

**Write policy:** only verified lessons (the fix was re-run and passed); dedupe by signature and increment counters instead of inserting duplicates.

**Store (D-038):** the Librarian keeps two things behind one interface. The `memory_entries` table stays the audit record (kind, signature, verified flag, success and fail counts, `seeded`/`learned` source). Each entry is mirrored to **Supermemory**, which handles retrieval and context: content plus metadata (`entry_id`, `kind`, `signature`, `source`, `success_rate`), container tag `evolab-global` for cross-project lessons and `evolab-proj-<project_id>` for project notes and gotchas. The row stores the returned `supermemory_id`.

**Retrieval:** exact signature match in `memory_entries` first; otherwise a Supermemory search over the task's query, filtered by `kind`, across the global and project containers. Rank by `relevance * success_rate * recency`. Inject at most 3 entries and mark each as `seeded` or `learned`. If Supermemory is unreachable, fall back to signature match only and say so in the task transcript.

**Cold start:** pre-seed 10 to 15 hand-written entries from our own dry runs of the KAN pipeline (`experiments/seeded_memory.json`). They are labelled `seeded` in the UI. The demo shows *learned* entries being created in the combined run and reused in a second run on another tabular dataset.

## 8. What to demonstrate (checklist for the agent owner)

- [ ] A refine with a visible prompt diff and A/B outcome
- [ ] A spawn with evidence shown in the approval card
- [ ] A merge or retire if it fires naturally
- [ ] Reward breakdown visible per task (O, C, F)
- [ ] Memory hit shown in a task transcript, labelled `learned`
- [ ] Failure attributed to the originating agent
- [ ] Activation list with reasons, including at least one inactive agent
- [ ] A re-plan triggered by `signals[]`, shown with trigger and reason
- [ ] A ladder walk with lineage shown (specialise and fresh spawn in the demo)
- [ ] Probation outcome shown for each new agent
- [ ] Council scores (three judges, Q, split flag) visible on a task, and the same task's trace in LangSmith with council feedback

## 9. Open items

See [logs/OPEN_QUESTIONS.md](logs/OPEN_QUESTIONS.md): model IDs, providers and limits (Q-23), Supermemory SDK and plan (Q-24), LangSmith plan and data policy (Q-25), council cost under rate limits (Q-26), approval auto-mode for the demo, template stubs (Q-20), tag vocabulary (Q-22).
