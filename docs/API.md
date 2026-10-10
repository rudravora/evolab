# API

Version 0.1. Base path: `/api/v1`. JSON everywhere unless noted. This file is the **contract between frontend, backend and worker**; change it by PR and tell the others (see COORDINATION.md). A machine-readable `shared/openapi.yaml` should be generated from the backend and committed.

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
  - agent: `active`, `inactive`, `retired`; kind: `core`, `seed`, `spawned`
  - worker: `online`, `offline`
  - ledger category: `compute_adaptation`, `dependency_fix`, `bug_fix`, `hyperparameter_change`, `fidelity_deviation`
  - memory kind: `error_fix`, `config_outcome`, `audit`, `gotcha`, `lesson`; source: `seeded`, `learned`

## 2. Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | No auth. `{ "status": "ok", "version": "...", "time": "..." }` |

## 3. Projects and runs (dashboard)

### POST `/projects`
Create a project and start its first run in one call (intake).
```json
// request
{
  "goal": "KAN vs MLP research",
  "inputs": [
    { "kind": "paper", "ref": "https://arxiv.org/abs/2404.19756" },
    { "kind": "repo",  "ref": "https://github.com/KindXiaoming/pykan" },
    { "kind": "note",  "ref": "Focus on small scientific functions" }
  ],
  "budget": { "max_wall_min": 90, "max_tokens": 1500000 },
  "approval_policy": { "expensive_runs": true, "new_packages": true },
  "example": false
}
// response 201
{ "project_id": "proj_...", "run_id": "run_...", "status": "planning", "worker_online": true }
```
- `example: true` ignores other fields and creates the KAN vs MLP example.
- Dataset files: `POST /projects/{id}/inputs` (multipart) after creation, or pass a URL as `kind: "dataset"`.
- Validation: `goal` required (1 to 2000 chars); `ref` for `paper`/`repo`/`dataset` must be an http(s) URL; URLs are never fetched synchronously.

### GET `/projects` , GET `/projects/{project_id}`
Lists and details, including latest run summary.

### POST `/projects/{project_id}/inputs`
Add an input mid-run. Multipart for files (size cap enforced; type allowlist: `.pdf .csv .tsv .json .txt .md .zip` `VERIFY`). Returns the `input`. The Meta-Controller is notified and may create work.

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
`Content-Type: text/event-stream`. Supports `Last-Event-ID` for resume. Each event: `id` (monotonic event id), `event` (type), `data` (JSON).

| Event type | Data (abridged) |
|---|---|
| `run.status` | `{ "status": "running" }` |
| `agent.task` | `{ "task_id", "agent_id", "agent_name", "status", "summary" }` |
| `agent.message` | `{ "task_id", "seq", "role", "content" }` (truncate large content; fetch full via transcript route) |
| `agent.evolution` | `{ "action": "spawn\|refine\|merge\|retire", "agent_id", "version", "reason" }` |
| `agent.score` | `{ "agent_id", "task_id", "reward", "outcome", "cost", "feedback" }` |
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

## 6. Agents, tasks, transcripts

| Method | Path | Notes |
|---|---|---|
| GET | `/agents` | All agents with current version, kind, status, rolling reward |
| GET | `/agents/{agent_id}` | Detail |
| GET | `/agents/{agent_id}/versions` | Version timeline with `reason` and `parent_version_id` |
| GET | `/agents/{agent_id}/versions/{version}` | Prompt and tools (diff against parent available via `?diff=1`) |
| GET | `/runs/{run_id}/tasks` | Tasks for a run (filter `?agent_id=&status=`) |
| GET | `/tasks/{task_id}` | Task detail including output and reward breakdown |
| GET | `/tasks/{task_id}/messages` | Full transcript (the "why") |
| POST | `/tasks/{task_id}/feedback` | `{ "value": "up\|down" }` |
| GET | `/runs/{run_id}/agent-graph` | Nodes and edges (spawned-from, merged-into) for the team view |

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
// type: risky_command
{ "command": "pip install pykan==0.2.8", "reason": "Required by official repo", "risk": "high" }
```
Approvals created by the system expire (`expires_at`); expired means rejected.

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
  "job_id": "job_...", "attempt": 1, "type": "shell",
  "payload": { "argv": ["python", "train_kan.py", "--seed", "0"], "cwd": "runs/kan_vs_mlp/code",
               "env": { "OMP_NUM_THREADS": "4" } },
  "timeout_s": 900, "max_output_bytes": 5000000
}
```
`type` values: `shell` (argv, never a shell string), `python_script`, `pip_install` (`{ "packages": ["pykan==0.2.8"] }`), `write_file` (`{ "path", "content" or "artifact_id" }`), `read_file`, `list_dir`, `git` (`{ "op": "init|commit|diff", "args": {...} }`), `download` (`{ "url", "dest", "sha256?" }`).

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
Multipart upload for result files referenced by a job. Size capped; type allowlisted.

Worker rules: poll `jobs/next` every `poll_interval_s` while idle; run at most the concurrency the capabilities allow; **re-check every command against the local policy** and return `status: failed` with `policy_denied` in `stderr_tail` if it violates it; never print the worker token.

## 10. Memory and notes

| Method | Path | Notes |
|---|---|---|
| GET | `/memory?q=&kind=&source=` | Search and list with counts |
| GET | `/memory/{id}` | Detail |
| GET | `/projects/{id}/notes` , POST, `PUT /notes/{id}` | Markdown notes; `source_ref` links to paper, experiment or task |

## 11. Integrations (n8n)

### Outbound (backend → n8n)
`POST {N8N_WEBHOOK_URL}` with header `X-Signature: sha256=<hmac of body using N8N_SIGNING_SECRET>`.
```json
{ "event": "approval_requested", "run_id": "run_...", "approval_id": "apr_...",
  "summary": "Expand W2 to 3 seeds (~6 min)", "decision_url": "https://.../approve/<token>",
  "expires_at": "..." }
```
Events: `approval_requested`, `job_failed`, `run_finished`.

### Inbound (n8n → backend)
`POST /hooks/n8n/decide`
```json
{ "approval_id": "apr_...", "decision": "approve", "token": "<single-use signed token>" }
```
Token is single-use, bound to the approval id and decision options, and expires with the approval. Invalid, used or expired tokens return `403`.

## 12. Rate limits (initial)

| Scope | Limit |
|---|---|
| Dashboard routes | 120 req/min per user |
| Chat | 20 messages/min per run |
| Worker log uploads | 10 req/s per worker |
| Hook endpoints | 30 req/min per IP |

## 13. Versioning

Breaking changes bump the path (`/api/v2`). Additive changes (new fields, new event types) are allowed in v1; clients must ignore unknown fields and unknown SSE event types.
