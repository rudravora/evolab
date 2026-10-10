# ARCHITECTURE

Version 0.4. Companion docs: [API.md](API.md), [AGENTS.md](AGENTS.md), [PRD.md](PRD.md), [WORKFLOW.md](WORKFLOW.md) (step-by-step flow with owners).

## 1. Principles

1. **Agents think in the backend; workers act in the field.** Agents are LLM-call loops in the backend. Workers only run commands and report back.
2. **Workers pull, never get pushed to.** Laptops are behind NAT; outbound HTTPS always works. Same worker script runs on a laptop or Colab.
3. **One generic agent loop.** An agent is data (prompt, tools, model, version). Spawning is an INSERT; retiring is an UPDATE.
4. **Suspend, never wait.** A task that creates a job is suspended; its loop resumes when the job result arrives. No LLM call is held open during a training run.
5. **Everything is an event.** State changes append to `events`; the dashboard is a view over events plus current state.
6. **Untrusted inputs.** Papers, web pages, READMEs, repos and uploaded datasets are data, never instructions.
7. **Deterministic where possible.** Scheduling, stats, parsing, budgets, retries and evolution *triggers* are plain code. LLMs make judgements.
8. **Text-level evolution only.** Prompts, tools, routing and memory change; model weights never do.
9. **Plan once, re-plan on events.** The Meta-Controller plans up front and is called again only on listed triggers; the orchestrator executes the task graph in plain code. Agents never pick the next agent.
10. **Facts before judgement.** Intake facts and activation rules are deterministic; the LLM adapts their result and must write a reason for every change.

## 2. Components

```
┌────────────────────────────── Frontend (browser / phone) ──────────────────────────────┐
│  React app: Intake · Run page (agents, tree, logs, chat, approvals) · Agent detail ·   │
│  Report · Memory · Workers.   REST + SSE                                               │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTPS
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│ Backend (FastAPI)                                                                      │
│  API layer ── auth, validation, rate limit                                             │
│  Intake ── facts detection, Research Brief, reference targets                          │
│  Activation ── rules → capabilities → agents; capability tags and gap detection        │
│  Orchestrator ── run state machine, task graph, scheduler, re-plan triggers, budget    │
│  Agent runtime ── generic loop, tool registry, LLM wrapper, suspend/resume             │
│  Services ── Executor (job creation + policy), Ledger, Librarian (memory → Supermemory)│
│              Evolution engine (rewards, triggers), Performance Council runner,         │
│              Approvals, Report builder                                                 │
│  Tracing ── LangSmith (every LLM and tool call; council scores as feedback)            │
│  Event bus ── DB events table + in-process pub/sub → SSE                               │
│  Storage ── SQLite (dev) / Postgres (deploy), artifact files                           │
└───────────────┬───────────────────────────────────────────────┬────────────────────────┘
                │ jobs pulled over HTTPS                        │ webhooks (signed)
        ┌───────▼────────┐                                ┌─────▼─────┐
        │ Worker process │                                │    n8n    │
        │ policy · jail  │                                │ phone I/O │
        │ subprocess run │                                └───────────┘
        └────────────────┘
        External: LLM providers (GPT-5.6 Luna, DeepSeek V4 Pro, GPT-5 Mini), Supermemory, LangSmith,
                  arXiv, PyPI, dataset hosts (allowlisted)
```

### 2.1 Frontend
React plus Vite plus TypeScript plus Tailwind (proposed; see DECISIONS). Talks only to the REST API and one SSE stream per run. No secrets in the frontend. Responsive from phone width.

### 2.2 Backend
Python FastAPI. Async. Runs the orchestrator and agent loops as background asyncio tasks. SQLAlchemy models. A single process is enough for the hackathon; keep code paths idempotent so a restart can resume.

### 2.3 Worker
Single Python file (`worker/worker.py`) with minimal dependencies (`requests`, optional `psutil`). Registers, heartbeats, claims jobs, runs them as subprocesses under the local policy, streams logs, uploads artifacts.

### 2.4 Integrations
- **LLM providers** via `llm.call(tier, messages, tools)` wrapper; tiers `strong` (GPT-5.6 Luna), `code` (DeepSeek V4 Pro), `fast` (GPT-5 Mini) mapped to real models by env vars (D-041). All three are served by one gateway (`POST {LLM_BASE_URL}`, OpenAI Chat Completions JSON with a `model` field, `Authorization: Bearer <LLM_API_KEY>`, `"stream": false`, text only). The output-token cap is `max_completion_tokens` for the GPT models and `max_tokens` for DeepSeek (`backend/agents/models.json`). **Each request body is capped at 48 KB**, far below the models' context windows: the wrapper measures the serialized body and trims context (oldest tool results first, then memory hits) before sending, and large artifacts (paper text, logs, transcripts) are summarised or truncated rather than passed whole.
- **Supermemory** behind the Librarian for memory retrieval and context (D-038). Backend only; the key never reaches the worker or frontend.
- **LangSmith** for tracing every agent task and recording council scores as feedback (D-039).
- **n8n** receives outbound webhooks and calls the inbound decision hook.
- **arXiv** (paper search and fetch) from the backend, not the worker.

## 3. Key flows

### 3.0a Intake and the Research Brief

1. `POST /projects` accepts any combination of inputs (at least one): `paper`, `question`, `repo`, `dataset`, `note`. Datasets arrive as a URL, a browser upload or a `worker_path`. No size cap for now (D-034, Q-18).
2. Inputs are stored as untrusted data. URLs are queued for background fetch, never fetched in the request.
3. **Facts detection** (deterministic service): classify each input; fetch metadata (paper title and arXiv id, README text, dataset size and format); look for links (README cites the paper, paper names the dataset, question names the paper). Ambiguous items only go to the Meta-Controller's fast model.
4. Write the **Research Brief** to `runs.brief_json`: `entry_types[]`, `goal`, `inputs[]`, `facts[]`, `domain` tag, `reference_targets[]` ranked paper claim > repo-reported numbers > published baselines > internal baselines. Emit `intake.brief`.

### 3.0b Activation and planning

1. **Activation rules** (deterministic table in AGENTS.md section 4a) map facts to required capabilities and agents. Result stored in `runs.activation_json` with a reason per agent, including agents left inactive. Emit `agent.activation`.
2. The **Meta-Controller** receives Brief, activation, budget, memory hits and the registry. It returns the adapted activation (with reasons), the **task graph** built from per-entry-type **fragments** joined by the activation rules, the mode (A/B/C), confirmed reference targets and estimates.
3. Tasks carry `required_tags`; any task no active agent covers is a **capability gap** (section 3.10).
4. A `plan` approval is created. On reject the run re-plans with the comment; on approve the run goes to `running`.
5. Question-only runs also create a `candidate_selection` approval once the Paper Analyst returns 3–5 candidates; the exploratory branch starts without waiting for it.

### 3.1 Worker pairing
1. Dashboard `POST /workers/pairing` returns a one-time pairing code and a ready-made command.
2. User runs `BACKEND_URL=... PAIRING_CODE=... python worker.py`.
3. Worker `POST /worker/register` with the code; backend returns a long-lived **worker token** (stored hashed). The worker keeps it in a local file or env var.
4. Worker heartbeats every 10 seconds; backend marks it offline after 30 seconds of silence.

### 3.2 Job lifecycle
```
pending ──claim──▶ claimed ──start──▶ running ──┬──▶ done
                                               ├──▶ failed
                                               ├──▶ timed_out
                                               └──▶ cancelled
 pending/claimed/running ──worker offline too long──▶ pending (requeued, attempt+1, max 2 requeues)
```
- Claim is atomic (`UPDATE ... WHERE status='pending' ... RETURNING`), filtered by worker capability and owner.
- A job created with `risk='high'` is created as `awaiting_approval` (not claimable) until an approval is `approved`.

### 3.3 Agent task lifecycle and suspension
```
queued ─▶ running ─▶ waiting_for_job ─▶ running ─▶ done
              │                            │
              ├──▶ waiting_for_approval ───┘
              └──▶ failed / cancelled
```
Loop pseudocode:
```
load task, agent_version, context (inputs, memory hits)
while steps < max_steps and tokens < cap:
    reply = llm.call(system=agent_version.prompt, messages=history, tools=allowed_tools)
    store message
    if reply.tool_call:
        result = tools.run(reply.tool_call)          # backend tools run inline
        if result.kind == "job_created":              # worker tools
            task.status = waiting_for_job; persist history; return   # SUSPEND
        history += result
    else if reply.finish: validate output schema; task.status = done; return
```
On a job result, the orchestrator finds the waiting task, appends the tool result to its history, sets it `running`, and re-enters the loop.

### 3.4 Run lifecycle
```
planning ─▶ awaiting_approval ─▶ running ─▶ done
   │              │                 │  ├──▶ paused ─▶ running
   │              └─ rejected ─▶ planning (re-plan with comment)
   └──────────────────────────────── failed / cancelled
```

### 3.5 Branch lifecycle
```
proposed ─▶ awaiting_approval(optional) ─▶ queued ─▶ running ─▶ done ─▶ expanded | pruned
                                                          └──▶ killed (by user)
```
A decision (`expanded` or `pruned`) always stores `decision_reason` and the evidence (metric deltas, seed variance).

### 3.6 Approvals
Types: `plan` (full plan or a re-plan diff), `expensive_run`, `risky_command`, `new_package`, `evolution`, `branch_expand`, `human_input`, `candidate_selection`.
Status: `pending`, `approved`, `rejected`, `edited`, `expired`. Approvals created from the dashboard, optionally mirrored to n8n for phone decision. Expired approvals default to *reject*.

### 3.7 Evolution loop (after each completed task and each run)
0. The **Performance Council** (AGENTS.md section 5a) scores the finished task: three judges in parallel, one per model tier, off the critical path. Each judge output is stored in `council_scores` and sent to LangSmith as feedback; code aggregates them into `Q` and emits `council.score`.
1. Compute reward per agent task (formula in AGENTS.md: `O = 0.5·O_det + 0.5·Q`, `R = 0.6·O + 0.2·(1−C) + 0.2·F`).
2. Update rolling averages.
3. Evolution engine (deterministic triggers) emits **candidates**: refine, spawn, merge, retire. Spawn candidates and planning-time gaps go through the resolution ladder (section 3.10).
4. For each candidate, the Meta-Controller (LLM) drafts the change (new prompt, new agent spec, merge plan).
5. An `evolution` approval is created; on approval the change is applied (new `agent_versions` row, new `agents` row, status change) and an event is logged.
6. Probation (A/B window): a refined version, or a newly spawned, restored or instantiated agent, handles the next 2 matching tasks; if its mean reward is lower than the version or agent it replaces, it is rolled back or retired automatically.

### 3.8 Memory
- **Write:** only verified lessons (the fix was re-run and passed). Dedupe by `signature`; increment `success_count` or `fail_count`.
- **Store:** `memory_entries` is the audit record (verified flag, counts, labels); every entry is mirrored to Supermemory (container tags `evolab-global` and `evolab-proj-<project_id>`) and keeps its `supermemory_id` (D-038).
- **Read:** before an agent starts a task the Librarian returns up to 3 entries: exact signature in `memory_entries`, then Supermemory search filtered by `kind`; ranked by `relevance * success_rate * recency`. If Supermemory is down, signature match only.
- **Feedback:** after the task, record whether retrieved entries helped.
- **Labels:** `source` is `seeded` or `learned`. UI shows the label.

### 3.9 Re-planning (hybrid model)

The orchestrator executes the approved graph without LLM calls. It calls the Meta-Controller in `replan` mode (current graph + trigger) only on these triggers:

| Trigger | Source |
|---|---|
| New fact in a finished task's `signals[]` | Agent output |
| Data issue (leakage, missing target) | Env and Data Engineer `signals[]` |
| Same error class failed twice, not fixed | Debugger escalation |
| Branch results arrive | Evaluator |
| Researcher chat, rejected approval, input added mid-run | API |
| 70 percent of wall time or tokens used | Budget monitor |
| Capability gap | Activation service, evolution engine |

The returned diff is classified: **minor** (add a debug or data-fix task, reorder pending tasks, drop a crashed branch) applies at once and is logged as `plan.revised`; **major** (new agent activated, new reference target, budget increase, mode change) creates a `plan` approval showing the diff, while unaffected tasks continue. Every revision is a `plan_revisions` row.

### 3.10 Capability gaps and the resolution ladder

- Agent versions carry `capability_tags`; tasks carry `required_tags`. An agent matches when its tags cover all required tags; ties are broken by rolling reward. Intake adds a `domain:*` tag (`materials`, `edge-ml`, `cpu-ml`, `3d`, `general`).
- Gap sources: planning time (activation), runtime (repeated unfixed failure class), researcher request (chat).
- Ladder, cheapest first, stopping at the first fit: **1 reuse** an active agent (no approval) → **2 restore** an inactive or retired agent with rolling reward ≥ 0.5 → **3 instantiate** a dormant template (`kind: template`) → **4 specialise** a broad agent into a narrower child → **5 fresh spawn** a spec drafted by the Meta-Controller.
- Steps 2–5 create an `evolution` approval (gap, evidence, proposed spec, lineage, expected effect), then probation (section 3.7).
- Guardrails: tools only from the existing registry; core agents never changed; spawned agents cannot spawn; at most 15 active agents; one evolution action per agent per run; the untrusted-content rule is appended to every prompt by code.
- Domain-specific agents (22 across materials, edge ML, CPU ML, 3D) are **out of v1 build scope**; the template library may hold dormant stubs (Q-20) or stay empty.

## 4. Data model

SQLite for development; Voroa managed Postgres for deployment. Memory search goes through Supermemory behind the Librarian interface; the database keeps the audit record only (D-038). IDs are text (UUID or ULID). Timestamps are UTC ISO strings. JSON columns are validated at the API layer.

```sql
workers(id, owner_id, name, token_hash, status, platform, last_heartbeat, cpu_pct, ram_pct, capabilities_json)
projects(id, owner_id, name, goal, workspace_path, created_at)
inputs(id, project_id, kind, ref, source, meta_json, created_at)
        -- kind: paper|question|repo|dataset|note ; source: url|upload|worker_path|text
runs(id, project_id, goal, status, entry_types_json, brief_json, activation_json, plan_version,
     budget_json, usage_json, started_at, ended_at)
plan_revisions(id, run_id, version, trigger, kind, diff_json, reason, approval_id, created_at)
        -- kind: initial|minor|major

agents(id, name, role, kind, status, origin, current_version_id, parent_ids_json, created_at)
        -- kind: core|seed|spawned|template ; status: active|inactive|retired|dormant
        -- origin: seed|template:<name>|specialised:<agent_id>|fresh|restored
agent_versions(id, agent_id, version, system_prompt, tools_json, capability_tags_json, model, reason,
               parent_version_id, probation_json, created_at)
agent_tasks(id, run_id, agent_version_id, task_type, required_tags_json, input_json, output_json, signals_json, status,
            tokens_in, tokens_out, wall_s, cost_norm, outcome_det, council_q, council_judges,
            council_disagreement, council_split, outcome_score, feedback, reward,
            failure_origin_agent_id, langsmith_trace_id, created_at, ended_at)
        -- outcome_score = 0.5*outcome_det + 0.5*council_q (or outcome_det if council_q is null)
council_scores(id, task_id, judge_agent_id, tier, scores_json, overall, rationale, failure_pattern,
               confidence, tokens_in, tokens_out, created_at)
agent_messages(id, task_id, seq, role, content, tool_name, tool_args_json, tool_result_json, ts)

jobs(id, run_id, task_id, worker_id, type, payload_json, risk, status, timeout_s, attempt,
     created_at, claimed_at, started_at, finished_at, exit_code, stdout_tail, stderr_tail)
job_logs(id, job_id, seq, stream, chunk, ts)

branches(id, run_id, parent_branch_id, hypothesis, spec_json, status, priority_score, decision, decision_reason)
experiments(id, branch_id, job_id, seed, config_json, commit_sha, metrics_json, cost_s, status)

ledger_entries(id, run_id, task_id, category, description, diff_ref, before_json, after_json, created_at)
        -- category: compute_adaptation|dependency_fix|bug_fix|hyperparameter_change|fidelity_deviation
memory_entries(id, kind, signature, context_json, content_json, supermemory_id, source,
               success_count, fail_count, last_used_at, created_at)
        -- kind: error_fix|config_outcome|audit|gotcha|lesson|dataset_profile ; source: seeded|learned
approvals(id, run_id, type, payload_json, status, requested_by, decided_via, comment, token_hash, expires_at, decided_at)
notes(id, project_id, title, markdown, source_ref, updated_at)
artifacts(id, run_id, kind, path, sha256, size, created_at)
events(id, run_id, ts, actor, type, payload_json)                -- append-only
```

Indexes that matter: `jobs(status, created_at)`, `jobs(worker_id, status)`, `events(run_id, id)`, `memory_entries(signature)`, `council_scores(task_id)`.

`events` is append-only: no UPDATE or DELETE from application code.

## 5. Tool registry

| Tool | Runs on | Notes |
|---|---|---|
| `finish` | Backend | Ends the task; output validated against the role's JSON schema |
| `search_papers` (arXiv), `fetch_pdf_text`, `find_repo`, `search_baselines` | Backend | Returns text; treated as untrusted. `search_baselines` looks up published results for a dataset |
| `read_memory`, `write_memory` | Backend (Librarian) | `write_memory` requires a verified flag |
| `log_ledger`, `read_ledger` | Backend (Ledger) | Category is mandatory on write |
| `record_metric` | Backend | Writes to `experiments.metrics_json` |
| `write_note` | Backend | Writes a Markdown note to `notes` |
| `read_logs` | Backend | Reads `job_logs` and `stdout_tail`/`stderr_tail` of a job |
| `search_agents` | Backend, Meta-Controller | Searches the agent registry by role, tools and score |
| `propose_branch`, `request_approval`, `get_budget` | Backend | |
| `spawn_agent` | Backend, Meta-Controller only | Creates an `evolution` approval; walks the ladder first |
| `match_agents` | Backend, Meta-Controller | Returns agents and dormant templates whose tags cover a tag set |
| `replan` | Backend, Meta-Controller only | Submits a graph diff; the orchestrator classifies it minor or major |
| `propose_candidates` | Backend, Paper Analyst | Creates a `candidate_selection` approval |
| `create_job` | Backend | Only way to touch the worker; policy-checked at creation. Takes a job `type` from the table below |
| `read_file`, `write_file` | Backend wrapper that creates a worker job | Jail-enforced on the worker |

**Worker job types** (the `type` field in API.md section 9). Agents reach them through `create_job`, `read_file` and `write_file`:

| Job `type` | What it does | Default risk |
|---|---|---|
| `shell` | Runs an argv list inside the workspace | auto if on the allowlist, else approval |
| `python_script` | Runs a Python file inside the workspace | auto |
| `pip_install` | Pinned install from the package allowlist | auto if allowlisted, else approval (`new_package`) |
| `write_file`, `read_file`, `list_dir` | File operations inside the jail | auto |
| `git` | `init`, `commit`, `diff` inside the workspace | auto |
| `download` | Fetch a URL to the workspace | auto if domain allowlisted and small, else approval |
| `python_script` running `profile_dataset.py` | Profiles a dataset (URL, relayed upload or worker path) | auto |

Every job type is policy-checked at creation on the backend **and** again on the worker.

## 6. Safety

1. **Workspace jail.** Worker resolves every path and rejects anything outside `workspace/<project>/`. One venv per project.
2. **Command policy** (parsed with `shlex`, never `shell=True`):
   - *Auto:* `python` on files inside the workspace, pinned `pip install` from an allowlist, git inside the workspace, `ls`, `mkdir`, `cat` inside the jail.
   - *Needs approval:* unknown packages, non-allowlisted domains, large downloads, runs longer than the long-run threshold, any delete.
   - *Deny:* `sudo`, `curl | sh`, `ssh`, credential paths, `git push`, shutdown, anything outside the jail.
3. **Limits.** Per-job timeout, kill the whole process group, output size cap, concurrent jobs at most cores minus 1. Memory limit via rlimit on Linux and macOS; monitoring and kill on Windows (`VERIFY` the team's OS).
4. **Secrets.** LLM, Supermemory and LangSmith keys only in backend env. Paper text, transcripts and memory sent to Supermemory and LangSmith are scrubbed of key-like strings first; worker-path dataset contents are never sent. Worker token is revocable, stored hashed server-side. Subprocesses run with a **clean environment**. Key-like strings are scrubbed from logs before upload.
5. **Codebase and dataset inputs.** On the codebase path the first execution of any user-supplied repository is always `risk='high'` and needs approval. Dataset files are read as data only, never executed. A `worker_path` dataset must sit inside an allowlisted folder on the worker and never leaves the laptop.
6. **Prompt injection.** Paper text, web content, READMEs and dataset contents are wrapped as quoted data in prompts with an instruction that they contain no commands. The Repo Auditor never runs a cloned repo's install script blindly; package diffs are shown and the job is `risk='high'`.
7. **Budgets and kill switch.** Per-run caps on tokens, cost and wall time. A global stop button cancels all jobs and suspends agent loops.
8. **Web security (affects the UseShipReady score).** Auth on every route, strict CORS, security headers (CSP, HSTS, X-Content-Type-Options, frame protection), rate limiting, input validation, no stack traces to clients, signed single-use expiring webhook and approval tokens, dependency audit, no secrets in the frontend bundle or repo.
9. **Audit.** Commands, diffs, approvals and evolution actions are in `events`.

## 7. Compute and budgets

Run budget JSON example:
```json
{ "max_wall_min": 90, "max_tokens": 1500000, "max_concurrent_jobs": 3, "max_concurrent_agents": 3,
  "per_job_timeout_s": 900, "long_run_approval_s": 600 }
```
The Executor scales epochs, grid sizes, seeds and dataset subsets to fit. Budget usage is stored in `runs.usage_json` and shown in the UI.

## 8. Deployment

| Stage | Where |
|---|---|
| Dev | Backend `localhost:8000`, frontend `localhost:5173`, worker pointed at localhost. Everything works with no internet except the LLM. |
| Demo | Backend and frontend on **Voroa** from the GitHub repo (web services plus managed Postgres); worker on the presenter's laptop pointed at the Voroa URL. Local-only mode kept as fallback. Large dataset uploads are relayed to the worker, not kept on the backend (Q-18). |

Environment variables (all in `.env.example`, never committed with values):
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_STRONG`, `LLM_MODEL_CODE`, `LLM_MODEL_FAST`, `SUPERMEMORY_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, `FEATURE_COUNCIL`, `DATABASE_URL`, `APP_SECRET`, `ALLOWED_ORIGINS`, `N8N_WEBHOOK_URL`, `N8N_SIGNING_SECRET`, `PUBLIC_BASE_URL`.

## 9. Observability

- `events` table and the Events tab on the run page.
- Structured backend logs with `run_id` and `task_id`.
- Token and cost counters per task.
- **LangSmith** traces: one trace per agent task (LLM calls and tool calls as child runs), tagged with `run_id`, `task_id`, `agent_id`, version, role and tier; council judge scores and `Q` attached as feedback. `agent_tasks.langsmith_trace_id` links the dashboard to the trace. The dashboard stays the researcher's view; LangSmith is the developers' view.
- `/api/v1/health` for uptime checks (UseShipReady monitoring and Voroa).

## 10. Repo layout (proposed)

```
evolab/
  backend/      FastAPI app, orchestrator, agent runtime, services, migrations, tests
  worker/       worker.py, policy.py, tests
  frontend/     React app
  shared/       openapi.yaml, JSON schemas for agent I/O, example payloads
  experiments/  KAN vs MLP seed code, seeded memory entries (JSON)
  docs/         these files (including WORKFLOW.md)
  scripts/      dev helpers (seed DB, run mock worker)
```

## 11. Technology choices (proposed, confirm in DECISIONS)

| Area | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI, SQLAlchemy | Same language as ML code and worker; fast to build |
| DB | SQLite (dev), Voroa managed Postgres (deploy) | Zero setup locally; FTS5 locally, Postgres full-text in deployment |
| Realtime | Server-Sent Events | Simpler than WebSockets, enough for one-way updates |
| Frontend | React, Vite, TypeScript, Tailwind | Fast iteration, mobile-friendly |
| Charts and tree | A charting library plus a tree/graph component (e.g., React Flow) `VERIFY` | Experiment tree is a key visual |
| LLM | Wrapper over three tiers: GPT-5.6 Luna (`strong`), DeepSeek V4 Pro (`code`), GPT-5 Mini (`fast`) | Models the team has access to (D-041) |
| Memory retrieval | Supermemory behind the Librarian | Managed retrieval and context (D-038) |
| Tracing and eval feedback | LangSmith | Per-task traces and council scores (D-039) |
| ML | PyTorch (CPU), `pykan`, scikit-learn | Paper's stack |

## 12. Known gaps and risks

- Multi-user and auth are minimal (single owner account is enough for the demo).
- Mode C and Colab are stretch and shape no P0 interface; keep the worker `capabilities` field so a Colab worker can be added without API changes.
- Evolution quality depends on the LLM; deterministic triggers, the ladder, approvals and probation bound the damage.
- Four full-depth entry paths widen the surface; fragments share agents and the build order in PRD 6a is the safety net.
- No upload size cap (D-034) is a deployment risk until Q-18 is answered.
- The council triples LLM calls per agent task; rate limits may bind (Q-26). The council is off the critical path and can be disabled with `FEATURE_COUNCIL`.
- Supermemory and LangSmith are third-party services that receive paper text and transcripts (Q-24, Q-25).
