# API

Version 0.6. Base path: `/api/v1`. JSON everywhere unless noted. This file is the **contract between frontend, backend and worker**; change it by PR and tell the others (see COORDINATION.md). A machine-readable `shared/openapi.yaml` should be generated from the backend and committed.

## 1. Conventions

- **IDs:** opaque strings (`run_01H...`). Never parse them.
- **Timestamps:** UTC ISO-8601, e.g. `2026-10-10T18:30:00Z`.
- **Auth:**
  - Dashboard routes: session cookie or `Authorization: Bearer <user_token>`.
  - Worker routes (`/worker/*`): `Authorization: Bearer <worker_token>`.
  - n8n inbound hook: signed single-use token in the body (see section 9).
- **Errors:** HTTP status plus
  ```json
  { "error": { "code": "invalid_state", "message": "Run is not paused", "details": {} } }
  ```
  Codes: `unauthorized`, `forbidden`, `not_found`, `validation_error`, `invalid_state`, `conflict`, `rate_limited`, `policy_denied`, `budget_exceeded`, `internal_error`. Never return stack traces.
- **Pagination:** `?limit=50&cursor=<opaque>`; responses include `next_cursor` or `null`.
- **Idempotency:** `POST` routes that create things accept an `Idempotency-Key` header; worker result routes are idempotent by `job_id` plus `attempt`.
- **Status enums (shared with ARCHITECTURE.md):**
  - run: `planning`, `awaiting_approval`, `running`, `paused`, `done`, `failed`, `cancelled`
  - job: `awaiting_approval`, `pending`, `claimed`, `running`, `done`, `failed`, `timed_out`, `cancelled`
  - agent task: `queued`, `running`, `waiting_for_job`, `waiting_for_approval`, `done`, `failed`, `cancelled`
  - branch: `proposed`, `awaiting_approval`, `queued`, `running`, `done`, `expanded`, `pruned`, `killed`
  - approval: `pending`, `approved`, `rejected`, `edited`, `expired`
  - agent: `active`, `inactive`, `retired`, `dormant`; kind: `core`, `seed`, `spawned`, `template`
  - model tier: `strong`, `code`, `fast`
  - worker: `online`, `offline`
  - ledger category: `compute_adaptation`, `dependency_fix`, `bug_fix`, `hyperparameter_change`, `fidelity_deviation`
  - memory kind: `error_fix`, `config_outcome`, `audit`, `gotcha`, `lesson`, `dataset_profile`; source: `seeded`, `learned`
  - entry type: `paper`, `question`, `repo`, `dataset`
  - input kind: `paper`, `question`, `repo`, `dataset`, `note`; input source: `url`, `upload`, `worker_path`, `text`
  - approval type: `plan`, `expensive_run`, `risky_command`, `new_package`, `evolution`, `branch_expand`, `human_input`, `candidate_selection`
  - reference target type: `paper_claim`, `repo_reported`, `published_baseline`, `internal_baseline`
  - verdict: `reproduced`, `partial`, `not_reproduced`, `baseline_established`, `exploratory`
  - plan revision kind: `initial`, `minor`, `major`
  - ladder step: `reuse`, `restore`, `instantiate_template`, `specialise`, `fresh_spawn`

## 2. Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | No auth. `{ "status": "ok", "version": "...", "time": "...", "mode": "live\|simulated" }`. `simulated` = scripted AI and a simulated worker (`backend/scripts/sim_server.py`); the dashboard shows a banner (D-027, D-054) |

## 2a. Sign-in (dashboard, D-044)

One owner account. The password hash lives in `OWNER_PASSWORD_HASH` (backend env only).

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | No auth. `{ "password": "..." }` → `{ "user": { "id": "usr_owner" }, "token": "...", "expires_at": <unix s> }`. Also sets the `evolab_session` cookie (HttpOnly, SameSite=Lax, Secure behind https). Use the token as `Authorization: Bearer <token>` when cookies are not available. Wrong password `401`; more than 5 attempts per minute per IP `429 rate_limited`; sign-in not configured `403` |
| POST | `/auth/logout` | Clears the cookie. `204` |
| GET | `/auth/me` | `{ "id": "usr_owner" }`; `401` without a valid session |

Sessions last 12 hours. Interactive docs (`/docs`) and `/api/v1/openapi.json` are served only when `PUBLIC_BASE_URL` is not https (local dev); the committed `shared/openapi.yaml` is the reference.

## 3. Projects and runs (dashboard)

### POST `/projects`
Create a project and start its first run in one call (intake). Any combination of inputs is accepted (D-031).
```json
// request (the combined demo)
{
  "goal": "Do KANs beat parameter-matched MLPs on real tabular data?",
  "inputs": [
    { "kind": "paper",    "source": "url",  "ref": "https://arxiv.org/abs/2404.19756" },
    { "kind": "repo",     "source": "url",  "ref": "https://github.com/KindXiaoming/pykan" },
    { "kind": "dataset",  "source": "url",  "ref": "https://example.org/tabular.csv" },
    { "kind": "question", "source": "text", "ref": "Do KANs beat parameter-matched MLPs on real tabular data?" }
  ],
  "budget": { "max_wall_min": 90, "max_tokens": 1500000 },
  "approval_policy": { "expensive_runs": true, "new_packages": true },
  "example": false
}
// response 201
{ "project_id": "proj_...", "run_id": "run_...", "status": "planning",
  "entry_types": ["paper", "repo", "dataset", "question"], "worker_online": true }
```
- `example: true` ignores other fields and creates the combined demo inputs.
- Validation: at least one input, or a `goal` that is a question (it becomes a `question` input). `goal` 1 to 2000 chars when given. `ref` for `paper`/`repo`/`dataset` with `source: "url"` must be an http(s) URL; URLs are never fetched synchronously.
- Datasets: `source: "url"`; `source: "upload"` via `POST /projects/{id}/inputs` (multipart) after creation; or `source: "worker_path"` with `ref` = a path inside an allowlisted folder on the worker (the file never leaves the laptop). **No size cap for now** (D-034); see Q-18 for storage.
- Intake runs facts detection in the background and emits `intake.brief` when the Research Brief is ready.

### GET `/projects` , GET `/projects/{project_id}`
Lists and details, including latest run summary.

### POST `/projects/{project_id}/inputs`
Add an input mid-run. Multipart form: `kind` plus either a `file` (paper `.pdf`, or a dataset in `.csv .tsv .json .parquet .txt .md .zip`; no size cap for now, D-034) or `ref` + `source` (`url`, `text`, `worker_path`, same rules as `POST /projects`). Returns `{ "id", "kind", "source", "ref", "size_bytes" }`. Adding an input is a re-planning trigger (`input_added`).

Uploaded datasets are relayed to the worker straight away (D-050): a `download` job with `approved: true`, pointing at `GET /api/v1/uploads/{input_id}?exp=&sig=` (HMAC-signed, expires after 1 hour, no session needed). The backend copy is deleted once the job is `done`. Uploaded PDFs stay on the backend; the Paper Analyst reads them by input id.

### POST `/projects` behaviour after M2
The response's `status` is `planning`. Intake runs in the background (metadata fetch, facts, Brief; emits `intake.brief` and one `agent.activation` per agent), then the Meta-Controller drafts the plan and a `plan` approval is created (`approval.requested`); the run moves to `awaiting_approval`. Approving moves it to `running`; rejecting re-plans with the comment; an expired plan approval cancels the run.

### POST `/projects/{project_id}/runs`
Start a new run in an existing project. Body: `{ "goal": "...", "budget": {...} }`.

### GET `/runs/{run_id}`
```json
{
  "id": "run_...", "project_id": "proj_...", "goal": "...", "status": "running",
  "budget": { "max_wall_min": 90, "max_tokens": 1500000 },
  "usage":  { "wall_min": 12.4, "tokens": 210334, "jobs": 14 },
  "counts": { "agents_active": 8, "branches": 5, "pending_approvals": 1 },
  "started_at": "...", "ended_at": null
}
```

### GET `/runs/{run_id}/brief`
```json
{
  "entry_types": ["paper", "repo", "dataset", "question"],
  "goal": "Do KANs beat parameter-matched MLPs on real tabular data?",
  "domain": "cpu-ml",
  "facts": [
    { "fact": "repo_links_paper", "evidence": "README cites arXiv 2404.19756" },
    { "fact": "dataset_not_in_paper", "evidence": "dataset name absent from paper text" },
    { "fact": "question_about_paper", "evidence": "question names KAN and MLP" }
  ],
  "reference_targets": [
    { "type": "paper_claim", "source": "inp_paper", "rank": 1 },
    { "type": "repo_reported", "source": "inp_repo", "rank": 2 }
  ],
  "activation": [
    { "agent_id": "agt_paper", "active": true, "reason": "paper supplied" },
    { "agent_id": "agt_scout_mode", "active": false, "reason": "not required: paper supplied" }
  ]
}
```

The response also carries `inputs` (with fetched titles) and `ready` (false until intake has finished).

### GET `/runs/{run_id}/plan` , GET `/runs/{run_id}/plan/revisions`
Plan: `{ "version", "mode", "pending_approval", "proposed" (the graph awaiting approval, else null), "tasks": [ { "task_id", "id", "task_type", "agent_id", "status", "required_tags", "depends_on" } ], "estimates" }`. A task with `agent_id: null` that is not an Executor task is a capability gap waiting for the ladder. Revisions: `{ "version", "trigger", "kind": "initial|minor|major", "diff", "reason", "approval_id", "created_at" }`.

Task types in the graph (D-047): `extract_spec`, `find_candidates`, `search_baselines`, `audit_repo`, `setup_env`, `implement`, `design_exploratory`, `design_baseline_suite`, `run_baseline` (Executor), `evaluate`, `design_branches`, `select_branches` (Meta-Controller picks branches), `run_branches` (Executor), `evaluate_final`, `decide_branches` (Meta-Controller expands or prunes with evidence), `write_report`. Outside the graph: `intake`, `plan`, `replan`, `evolution_draft`, `debug`.

### POST `/runs/{run_id}/pause` , `/resume` , `/cancel`
`pause` stops creating new jobs and suspends agent loops at the next step; running jobs finish. `cancel` also cancels jobs. Returns the run. `invalid_state` if the transition is illegal.

## 4. Chat

### POST `/runs/{run_id}/chat`
```json
{ "message": "try noisy data", "target_agent_id": null }
```
Response `202`: `{ "message_id": "msg_..." }`. The reply and any consequences arrive over SSE as `chat.message` and other events. `target_agent_id` is optional (default: Meta-Controller routes).

### GET `/runs/{run_id}/chat?limit=...`
Chat history.

## 5. Streaming (SSE)

### GET `/runs/{run_id}/stream`
`Content-Type: text/event-stream`. Supports `Last-Event-ID` (or `?after_id=`) for resume. Each event: `id` (monotonic event id), `event` (type), `data` (JSON). Global events with no run (`worker.status`) appear in every run's stream. A `: keepalive` comment is sent after 15 s of silence. The stream **closes** once the run is `done`, `failed` or `cancelled` and every event has been sent; reconnecting with the last id then returns nothing. Auth is the session cookie (EventSource cannot set headers).

The same events are available as JSON from `GET /runs/{run_id}/events?after_id=&limit=` (limit 1–1000, default 200).

| Event type | Data (abridged) |
|---|---|
| `run.status` | `{ "status": "running" }` |
| `agent.task` | `{ "task_id", "agent_id", "agent_name", "status", "summary" }` |
| `agent.message` | `{ "task_id", "seq", "role", "content" }` (truncate large content; fetch full via transcript route) |
| `agent.evolution` | `{ "action": "spawn\|refine\|merge\|retire\|restore", "ladder_step", "origin", "agent_id", "version", "reason" }` |
| `agent.score` | `{ "agent_id", "task_id", "reward", "outcome", "outcome_det", "council_q", "council_split", "cost", "feedback" }` (`outcome = 0.5·outcome_det + 0.5·council_q`; `council_q` null when the council was unavailable) |
| `council.score` | `{ "task_id", "agent_id", "judges": [ { "judge_agent_id", "tier", "overall" } ], "q", "disagreement", "split" }` |
| `job.status` | `{ "job_id", "status", "worker_id" }` |
| `job.log` | `{ "job_id", "seq", "stream", "chunk" }` |
| `branch.update` | `{ "branch_id", "status", "decision", "decision_reason", "priority_score" }` |
| `experiment.metrics` | `{ "experiment_id", "branch_id", "metrics": {...} }` |
| `ledger.entry` | `{ "id", "category", "description" }` |
| `memory.hit` | `{ "task_id", "entry_id", "kind", "source" }` |
| `approval.requested` | `{ "approval_id", "type", "summary" }` |
| `approval.decided` | `{ "approval_id", "status" }` |
| `worker.status` | `{ "worker_id", "status", "cpu_pct", "ram_pct" }` |
| `chat.message` | `{ "id", "role", "content" }` |
| `report.ready` | `{ "artifact_id" }` |
| `budget.warning` | `{ "metric", "used", "limit" }` |
| `intake.brief` | `{ "entry_types", "facts_count", "reference_targets" }` (full Brief via `GET /runs/{id}/brief`) |
| `agent.activation` | `{ "agent_id", "active", "reason" }` |
| `plan.revised` | `{ "version", "trigger", "kind", "reason", "approval_id" }` |
| `candidates.ready` | `{ "approval_id", "count" }` |
| `capability.gap` | `{ "task_id", "required_tags", "source": "planning\|runtime\|researcher" }` |
| `agent.probation` | `{ "agent_id", "version", "result": "passed", "mean", "baseline" }` (a failed probation emits `agent.evolution` with `rollback` or `retire`) |
| `memory.write` | `{ "entry_id", "kind", "source" }` |
| `job.requeued` | `{ "job_id", "attempt", "reason" }` |
| `job.denied` | `{ "type", "reason", "task_id" }` (policy refused to create the job) |
| `replan.skipped` , `evolution.blocked` , `evolution.dropped` , `candidates.none` | Diagnostics: replan limit reached, 15-agent cap reached, empty draft, no candidate chosen |

## 6. Agents, tasks, transcripts

| Method | Path | Notes |
|---|---|---|
| GET | `/agents` | All agents with current version, kind, status, origin, capability tags, rolling reward. `?kind=template` lists dormant templates. Item shape: `{ "id", "name", "role", "kind", "status", "origin", "evolvable", "council_evaluated", "parent_ids", "current_version": { "id", "version", "model", "tools", "capability_tags", "reason", "parent_version_id", "created_at" }, "rolling_reward" }` |
| GET | `/agents/{agent_id}` | Detail |
| GET | `/agents/{agent_id}/versions` | Version timeline with `reason` and `parent_version_id` |
| GET | `/agents/{agent_id}/versions/{version}` | Prompt and tools (diff against parent available via `?diff=1`) |
| GET | `/runs/{run_id}/tasks` | Tasks for a run (filter `?agent_id=&status=`) |
| GET | `/tasks/{task_id}` | Task detail including output and reward breakdown (`outcome_det`, `council_q`, `council_split`, cost, feedback, reward) and `langsmith_trace_url` when tracing is on |
| GET | `/tasks/{task_id}/council` | The three judges' outputs: `[ { "judge_agent_id", "tier", "scores", "overall", "rationale", "failure_pattern", "confidence" } ]` plus `q`, `disagreement`, `split` |
| GET | `/tasks/{task_id}/messages` | Full transcript (the "why") |
| POST | `/tasks/{task_id}/feedback` | `{ "value": "up\|down" }` |
| GET | `/runs/{run_id}/agent-graph` | Nodes and edges (spawned-from, specialised-from, instantiated-from, merged-into) plus each node's activation state and reason, for the team view |

## 7. Experiments

| Method | Path | Notes |
|---|---|---|
| GET | `/runs/{run_id}/tree` | Branch tree with status, decision and reason, key metrics |
| GET | `/branches/{branch_id}` | Detail with experiments |
| POST | `/branches/{branch_id}/pause` , `/kill` | User control |
| POST | `/branches/{branch_id}/expand` | User override: `{ "reason": "..." }` |
| GET | `/runs/{run_id}/jobs` | List jobs (`?status=`) |
| GET | `/jobs/{job_id}` | Detail |
| GET | `/jobs/{job_id}/logs?after_seq=` | Log chunks |
| GET | `/runs/{run_id}/ledger` | Deviation ledger |
| GET | `/runs/{run_id}/events?after_id=` | Raw event timeline |
| GET | `/runs/{run_id}/report` | Latest report Markdown plus metadata |
| GET | `/runs/{run_id}/artifacts` , `/artifacts/{id}/download` | Files |

Tree response shape:
```json
{
  "root": {
    "id": "br_base", "hypothesis": "Baseline reproduction", "status": "expanded",
    "metrics": { "kan_rmse": 0.0031, "mlp_rmse": 0.0042 },
    "decision_reason": "Reproduced on 2/3 tasks across 3 seeds",
    "children": [
      { "id": "br_w1", "hypothesis": "Noise sigma=0.1", "status": "running", "children": [] }
    ]
  }
}
```

## 8. Approvals

| Method | Path | Notes |
|---|---|---|
| GET | `/approvals?status=pending&run_id=` | Inbox |
| GET | `/approvals/{id}` | Detail with payload |
| POST | `/approvals/{id}/decide` | `{ "decision": "approve\|reject\|edit", "comment": "...", "edited_payload": {...} }` |

Payloads by type (examples):
```json
// type: plan
{ "summary": "Reproduce KAN vs MLP on 3 functions + 1 tabular dataset, 3 seeds, ~45 min CPU",
  "plan": { "tasks": [...], "estimated_wall_min": 45, "mode": "A" } }
// type: evolution
{ "action": "spawn", "proposed_agent": { "name": "KAN API Specialist", "prompt": "...", "tools": [...] },
  "evidence": ["Debugger failed 2x on pykan API errors"], "expected_effect": "Fewer failed attempts" }
// type: plan (a major re-plan carries a diff instead of a full plan)
{ "summary": "Add tabular baseline suite and activate a new agent", "trigger": "capability_gap",
  "diff": { "add_tasks": [...], "activate": ["agt_..."], "targets_added": [] } }
// type: candidate_selection
{ "summary": "Pick a paper for: Do KANs beat MLPs on tabular data?",
  "candidates": [ { "title": "...", "url": "https://arxiv.org/abs/...", "why": "..." } ] }
// type: evolution (ladder)
{ "action": "spawn", "ladder_step": "fresh_spawn", "gap": { "required_tags": ["bench:tabular-protocol"] },
  "proposed_agent": { "name": "Tabular Benchmark Protocol", "prompt": "...", "tools": [...], "capability_tags": [...] },
  "lineage": "fresh", "evidence": ["No active agent or template covers bench:tabular-protocol"],
  "expected_effect": "Fair, reproducible tabular baselines", "probation_tasks": 2 }
// type: risky_command
{ "command": "pip install pykan==0.2.8", "reason": "Required by official repo", "risk": "high" }
```
Approvals created by the system expire (`expires_at`, 30 minutes); expired means rejected. Job approvals (`risky_command`, `new_package`, `expensive_run`) carry `{ "summary", "job_id", "job_type", "payload", "reason", "risk" }`; approving makes the job claimable with `approved: true`, rejecting or expiring cancels it. `edit` is not yet supported for job approvals (`409 invalid_state`); approve or reject instead. Deciding an already-decided approval returns `409 invalid_state`.

## 9. Workers

### POST `/workers/pairing` (dashboard)
Returns `{ "pairing_code": "ABCD-1234", "expires_at": "...", "command": "BACKEND_URL=... PAIRING_CODE=ABCD-1234 python worker.py" }`.

### GET `/workers` (dashboard)
List workers and status. `DELETE /workers/{id}` revokes the token.

### POST `/worker/register`
```json
// request
{ "pairing_code": "ABCD-1234", "name": "Laptop-1", "platform": "linux-x86_64",
  "capabilities": { "cpu_cores": 8, "ram_gb": 16, "gpu": false, "python": "3.11" } }
// response
{ "worker_id": "wrk_...", "worker_token": "<shown once>", "poll_interval_s": 2, "heartbeat_interval_s": 10 }
```

### POST `/worker/heartbeat`
`{ "status": "idle|busy", "cpu_pct": 41.2, "ram_pct": 63.0, "running_job_ids": ["job_..."] }` → `{ "cancel_job_ids": [], "stop": false }`. The response is how the backend tells a worker to cancel jobs.

### GET `/worker/jobs/next`
Atomic claim. `204` if nothing; otherwise `200`:
```json
{
  "job_id": "job_...", "project_id": "proj_...", "attempt": 1, "type": "shell",
  "payload": { "argv": ["python", "train_kan.py", "--seed", "0"], "cwd": "code",
               "env": { "OMP_NUM_THREADS": "4" } },
  "approved": false,
  "timeout_s": 900, "max_output_bytes": 5000000
}
```
- **`approved`** (always present) is `true` when the researcher approved this job through a `risky_command`, `new_package` or `expensive_run` approval. The worker's own policy may run a `needs_approval` job only when `approved` is true; a `deny` verdict never runs.
- Jobs of runs that are paused, cancelled or finished are not handed out.
- **`project_id`** (always present) selects the jail: every job runs inside `WORKSPACE_ROOT/<project_id>/` on the worker.
- **Paths:** `cwd` and every path in a payload (`path`, `dest`, `paths`) are relative to that jail. The worker rejects absolute paths and any `..` segment with `policy_denied`. The backend applies the same check when the job is created.
- **Attempts and retries:** `attempt` starts at 1. A job lost to a worker that goes offline is requeued with `attempt + 1`, at most 2 times (max attempt 3); after that it is `failed`.

Uploaded datasets are relayed to the worker as a `download` job from a short-lived signed backend URL and then removed from the backend (Q-18). `worker_path` datasets are read in place.

`type` values and payloads:

| `type` | `payload` |
|---|---|
| `shell` | `{ "argv": [...], "cwd", "env" }`; argv list, never a shell string |
| `python_script` | `{ "argv": ["python", "<file>.py", ...], "cwd", "env" }` |
| `pip_install` | `{ "packages": ["pykan==0.2.8"] }` |
| `write_file` | `{ "path", "content" or "artifact_id" }` |
| `read_file`, `list_dir` | `{ "path" }` |
| `git` | `{ "op": "init", "args": {} }` · `{ "op": "commit", "args": { "message": "..." } }` · `{ "op": "diff", "args": { "paths": [] } }` (empty `paths` = whole jail) |
| `download` | `{ "url", "dest", "sha256?" }` |

Two job kinds are conventions on existing types, not new `type` values:

- **Dataset profiling** is a `python_script` job running `profile_dataset.py` (`argv: ["python", "profile_dataset.py", "--path", "<dataset path>"]`). Its result `metrics` carry the profile summary and `files` carry the full profile JSON.
- **Repo smoke test** (WORKFLOW 3.2) is a `python_script` or `shell` job. Its result `metrics` must carry `{ "import_ok": bool, "tests_passed": int, "tests_failed": int }`. The first run of a user-supplied repository is `risk='high'` and needs approval (ARCHITECTURE section 6).

### POST `/worker/jobs/{job_id}/start`
Marks `running`. `{ "attempt": 1 }`.

### POST `/worker/jobs/{job_id}/logs`
`{ "attempt": 1, "chunks": [ { "seq": 41, "stream": "stdout", "text": "epoch 40 loss 0.0031" } ] }`. Backend scrubs key-like strings again and rate-limits.

### POST `/worker/jobs/{job_id}/result`
```json
{ "attempt": 1, "status": "done", "exit_code": 0,
  "stdout_tail": "...", "stderr_tail": "...",
  "metrics": { "rmse": 0.0031, "params": 5200, "train_s": 41.2 },
  "files": [ { "path": "results/seed0.json", "sha256": "..." } ] }
```
`status`: `done`, `failed`, `timed_out`, `cancelled`. Idempotent per `job_id` plus `attempt`.

### POST `/worker/artifacts`
Multipart: `job_id`, `attempt`, `path` (jail-relative), `file`. 50 MB cap; types `.json .csv .tsv .txt .md .log .png .svg .pdf`. Returns `{ "artifact_id", "sha256", "size" }`.

### Experiment jobs (Executor, D-048)
The Executor fills the Implementer's entry-point template (or a branch's `spec.entrypoint`) with `{seed}`, `{budget_min}`, `{results_path}` and `{spec_args}` (branch overrides as `--key value`), and sends `payload.results_path` (`results/<experiment_id>.json`). The worker reads that JSON back as the job's `metrics` (B's runner). B's harness result shape `{ "metrics": {...}, "param_count", "train_seconds", "status" }` is unwrapped by the backend; a flat `{ "metric": number }` also works. A `done` job with no numeric metrics counts as failed and goes to the Debugger (at most 2 debug cycles per experiment).

Worker rules: poll `jobs/next` every `poll_interval_s` while idle; run at most the concurrency the capabilities allow; **re-check every command against the local policy** and return `status: failed` with `policy_denied` in `stderr_tail` if it violates it; never print the worker token.

Required worker behaviour:

| Situation | Behaviour |
|---|---|
| Backend unreachable or connection error | Retry with exponential backoff: 1 s, doubling, capped at 60 s. Never crash on a network error |
| Stored token rejected (`401`, e.g. revoked or stale) | The worker exits with a message. Re-pairing needs a **new pairing code** from the dashboard (`PAIRING_CODE=... python worker.py`); the old token is not reused |
| Log streaming | stdout and stderr are batched and sent about every 1 s via `/logs` |
| Worker shutdown (Ctrl+C, `stop: true` from heartbeat) | Running jobs are killed (whole process group) and each is reported with `status: "cancelled"` via `/worker/jobs/{job_id}/result` before exit |
| Cancel request (`cancel_job_ids` from heartbeat) | The job is killed and reported with `status: "cancelled"` |

## 10. Memory and notes

| Method | Path | Notes |
|---|---|---|
| GET | `/memory?q=&kind=&source=` | With `q`: Librarian search, `{ "retrieved_by": "signature\|supermemory\|keyword", "entries": [...] }`. Without: latest 200 with `counts` of seeded and learned. Entry: `{ "id", "kind", "signature", "source", "content", "context", "success_count", "fail_count", "last_used_at", "created_at", "mirrored" }` |
| GET | `/memory/{id}` | Detail |
| GET | `/projects/{id}/notes` , POST, `PUT /notes/{id}` | Markdown notes; `source_ref` links to paper, experiment or task |

## 11. Integrations (n8n)

### Outbound (backend → n8n)
`POST {N8N_WEBHOOK_URL}` with header `X-Signature: sha256=<hmac of body using N8N_SIGNING_SECRET>`.
```json
{ "event": "approval_requested", "run_id": "run_...", "approval_id": "apr_...", "type": "plan",
  "summary": "13 tasks, 8 agents, ~45 min",
  "decisions": {
    "approve": { "token": "<signed token>", "decision_url": "https://<backend>/api/v1/hooks/n8n/decide" },
    "reject":  { "token": "<signed token>", "decision_url": "https://<backend>/api/v1/hooks/n8n/decide" } },
  "expires_at": "..." }
```
One token **per decision** (D-051): each is bound to the approval id and that one decision, expires after 30 minutes, and only its hash is stored. Using either token invalidates both. `job_failed` carries `{ "run_id", "job_id", "status", "summary" }`; `run_finished` carries `{ "run_id", "status", "summary" }`. Delivery is best effort and never blocks a run. Outbound calls are off unless `N8N_WEBHOOK_URL` and `N8N_SIGNING_SECRET` are set.

### Inbound (n8n → backend)
`POST /hooks/n8n/decide`
```json
{ "approval_id": "apr_...", "decision": "approve", "token": "<the token from decisions.approve>" }
```
Token is single-use, bound to the approval id and one decision, and expires with the approval. Invalid, used, mismatched or expired tokens return `403`. Rate limit 30 requests per minute per IP.

## 12. Rate limits (initial)

| Scope | Limit |
|---|---|
| Dashboard routes | 300 req/min per user (raised from 120: the live dashboard polls several routes, D-054) |
| Chat | 20 messages/min per run |
| Worker log uploads | 10 req/s per worker |
| Hook endpoints | 30 req/min per IP |

All implemented (M5). Over-limit responses are `429 rate_limited` with `Retry-After`. JSON bodies over 1 MB are refused with `413` (uploads exempt). Worker, hook, upload-relay and health routes are outside the per-user dashboard limit.

## 13. Versioning

Breaking changes bump the path (`/api/v2`). Additive changes (new fields, new event types) are allowed in v1; clients must ignore unknown fields and unknown SSE event types.
