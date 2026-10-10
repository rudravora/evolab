# DEVLOG

Append-only. Newest entry at the **bottom**. Do not edit or delete old entries; correct them with a new entry.

## Team and owners (fill at kickoff)

| Role | Person | Contact |
|---|---|---|
| A: Backend, agents, deploy | _TBD_ | |
| B: Worker, experiments, n8n | _TBD_ | |
| C: Frontend, mocks, demo | _TBD_ | |

Team of 3 (decision D-023). The earlier role D was split across A, B and C; see COORDINATION.md section 2.

## Entry template

```
### YYYY-MM-DD HH:MM IST · <name> · <area>
- Done: ...
- State: what works, what is half-done (branch/PR links)
- Next: the very next step
- Blockers / gotchas: ...
- Touches contracts? yes/no (if yes, which doc and PR)
```

---

### 2026-10-10 · planning session (Rudra, with Claude) · all
- Done: Read the PS-03 problem statement. Clarified scope. Chose KAN vs MLP (Liu et al. 2024, `pykan`) as the demo paper. Defined architecture (web control plane, agents as backend LLM loops, pull-based workers), agent roster (9 LLM agents plus 3 services), reward formula, evolution rules, memory design, DB schema, API, safety rules and dashboard layout. Identified sponsor roles: Voroa for hosting, n8n for alerts and approvals, UseShipReady for readiness scoring.
- State: docs v0.1 drafted (this folder). No code written yet.
- Next: team reviews docs; fill owners above; resolve items in OPEN_QUESTIONS.md; plan the 24-hour timeline and work split.
- Blockers / gotchas: LLM provider and limits not chosen. Team size and names not recorded. Several facts are marked `VERIFY` (exact KAN function forms, `pykan` version, Voroa limits, event timing).
- Touches contracts? Initial creation of API.md, ARCHITECTURE.md schema, AGENTS.md.

### 2026-10-10 14:45 IST · planning session (Rudra, with Claude) · team and scope
- Done: Team confirmed as 3 developers, one of them frontend. Rewrote COORDINATION.md (v0.2) for three roles (A backend/agents/deploy, B worker/experiments/n8n, C frontend/mocks/demo). Added a cut ladder, build order and extra risks to PRD.md (section 6a and risks). Added decisions D-023 to D-027. Reassigned open-question owners. Updated CONTEXT.md assumption on team size.
- State: docs v0.2. No code yet. Names for roles A, B, C not filled in.
- Next: fill in names above; resolve Q-01 (names), Q-02 (LLM provider) and Q-04 (Voroa) first; then plan the 24-hour timeline against the three roles.
- Blockers / gotchas: A carries the heaviest module; see the load-balancing note in COORDINATION.md section 10.
- Touches contracts? No (API.md, ARCHITECTURE.md and AGENTS.md unchanged).

### 2026-10-10 · planning session (Dev A, with Claude) · entry paths, planning model, spawning
- Done: Requirement changed: a project can start from a paper, question, codebase or dataset, or any mix. Decided all four paths at full depth (paper first), mandatory exploratory mode on the question path, dynamic activation for combined inputs, hybrid plan-then-re-plan model, capability tags plus a five-step spawning ladder (domain agents as dormant templates, out of v1 build), datasets by URL/upload/worker path with no size cap for now, combined-input demo, and a revised work split. Recorded D-028 to D-037. Wrote WORKFLOW.md (step-by-step workflow with owners) and updated all docs to v0.3.
- State: docs v0.3. No code yet. Role names still TBD except Dev A (author of these changes).
- Next: team reviews v0.3; answer Q-18 (upload storage), Q-19 (demo datasets), Q-20 (template stubs), Q-22 (tag vocabulary) before M0; then the 24-hour timeline.
- Blockers / gotchas: four full-depth paths raise scope sharply; the build order in PRD 6a (D-037) is the safety net. A's load grows (intake, activation, re-planning, tags, ladder) despite the offloads to B and C.
- Touches contracts? Yes: API.md (intake, brief, activation, re-planning events, approvals), ARCHITECTURE.md (schema, flows), AGENTS.md (output schema, tags, verdicts, ladder). Contracts are not yet frozen (pre-M0).

### 2026-10-10 · Shourya, with Claude · agents, council, memory, tracing
- Done: Workflow changes recorded as D-038 to D-041: Supermemory behind the Librarian (memory_entries kept as audit record), LangSmith tracing, a 3-judge Performance Council (one judge per model; median Q; O = 0.5·O_det + 0.5·Q), three model tiers (strong = GPT-5.6 Luna, code = DeepSeek V4 Pro, fast = GPT-5 Mini). Created the 9 seed agents and 3 council judges as data: `backend/agents/seed/*.json`, prompts in `backend/agents/prompts/`, tool registry and tier map, output schemas in `shared/schemas/`, canned outputs in `shared/examples/agents/`, council aggregation and reward in `backend/agents/council.py`, tests in `backend/tests/` (49 passing).
- State: agent definitions and reward maths only. No LLM wrapper, Librarian, Supermemory or LangSmith client code yet.
- Next: answer Q-23 (model IDs, providers, limits) and Q-24/Q-25 (SDK versions to pin); then the LLM wrapper with tier mapping and LangSmith tracing; then the Librarian on Supermemory; then the council runner.
- Blockers / gotchas: the council triples LLM calls per task (Q-26). `docs/Workflow.pdf` is still v0.3.
- Touches contracts? Yes: AGENTS.md (council, tiers, reward, memory), ARCHITECTURE.md (schema: `council_scores`, new `agent_tasks` columns, `memory_entries.supermemory_id`; env vars), API.md (additive: `council.score` SSE, `agent.score` fields, `GET /tasks/{id}/council`), shared/schemas, shared/examples/agents.

### 2026-10-10 · Shourya, with Claude · LLM gateway details
- Done: Recorded the event's model gateway: one endpoint for all three models, `Authorization: Bearer <TEAM_API_KEY>` (stored as `LLM_API_KEY` in `.env`), OpenAI Chat Completions JSON, `stream: false`, text only, 48 KB max request. Updated `backend/agents/models.json`, `.env.example` (single `LLM_BASE_URL` / `LLM_API_KEY`), ARCHITECTURE and AGENTS (context must fit 48 KB). Local `.env` created (gitignored) with non-secret values filled.
- Next: confirm whether the gateway accepts the `tools` field and its rate limits (Q-23); then write the LLM wrapper.
- Blockers / gotchas: 48 KB per request (~12k tokens) is the real context limit, not the 1M windows. Council judges need truncated transcripts.
- Touches contracts? Yes: ARCHITECTURE env vars (`LLM_BASE_URL`, `LLM_API_KEY` replace `LLM_PROVIDER*`, `LLM_API_KEY_*`).

### 2026-10-10 · Dev A (Shourya), with Claude · worker contract
- Done: API.md section 9 (v0.5) updated from B's gap reports (D-042): `project_id` on every claimed job (top level, next to `job_id`); jail = `WORKSPACE_ROOT/<project_id>/`, payload paths relative to it, absolute and `..` rejected; payload table per job type including `git` args; dataset profiling and repo smoke test defined as `python_script`/`shell` conventions; max attempt 3; required worker behaviour (401 → exit and re-pair, cancelled on shutdown and cancel, backoff 1 s → 60 s, logs about every 1 s).
- Next: B updates `shared/examples/worker/*.json` on b/fake-worker (add `project_id`, make `cwd` jail-relative, e.g. `"code"` instead of `"runs/example_project/code"`) and the worker on b/worker-core (see gotchas). A builds the backend side of section 9.
- Blockers / gotchas (b/worker-core as of this entry): a 401 is retried forever, because `raise_for_status()` raises `HTTPError`, a `RequestException`, so `_backoff_request` swallows it; `run_job` returns a fixed success result and sends one log chunk at the end rather than streaming about every 1 s; `cancel_job_ids` is only printed, not acted on.
- Touches contracts? Yes: API.md section 9 (additive field plus clarifications); B's worker examples need the matching update.

### 2026-10-10 · Dev A (Shourya), with Claude · M0 backend skeleton
- Done: FastAPI app in `backend/app/` (settings from `.env`, standard error shape, security headers, strict CORS); SQLAlchemy models for every table in ARCHITECTURE section 4 plus `worker_pairings`; Alembic migration `0001`; `/api/v1/health`; owner sign-in (`/auth/login`, `/logout`, `/me`) with scrypt hash, signed session cookie or Bearer, login rate limit; read-only `/agents` routes; agent seeding (`python -m app.seed`); `shared/openapi.yaml` generated; tag vocabulary frozen (`backend/agents/tags.json`, D-043); activation examples in `shared/examples/activation/`. D-043 to D-045 recorded, Q-22 resolved. 73 tests pass; smoke-tested with uvicorn over HTTP.
- State: M0 code complete except the gate's other half: the mock server (C) and fake worker (B, on b/fake-worker) must also run for M0 to pass.
- Next: M1 job pipe: pairing and worker routes, job creation with policy check, run state machine, SSE, a fake agent that creates one job. Pair with B.
- Blockers / gotchas: set `APP_SECRET` and `OWNER_PASSWORD_HASH` in `.env` before starting the server (it refuses to start without `APP_SECRET`). Schema additions vs the old ARCHITECTURE text (now updated): `worker_pairings`, `jobs.project_id/max_output_bytes/metrics_json/files_json`, `job_logs.attempt`, `branches.kind`, agent flags, `agent_versions.output_schema/max_steps`, `created_at` on a few tables.
- Touches contracts? Yes: API.md section 2a (sign-in routes, additive), `/agents` item shape; ARCHITECTURE section 4 schema; `shared/openapi.yaml`; `shared/examples/activation/`.

### 2026-10-10 · Dev A (Shourya), with Claude · M1 backend job pipe
- Done: projects and runs (`POST /projects` incl. `example: true`, list, detail, new run, pause, resume, cancel); worker pairing, list, revoke; worker API (register, heartbeat with cancel ids, atomic claim with `project_id` and `approved`, start, logs with scrub and dedupe, result idempotent per attempt); job creation through a backend policy that mirrors B's `worker/policy.py`; job approvals (`risky_command`, `new_package`, `expensive_run`) with approve/reject and 30-minute expiry; sweeper (worker offline after 30 s, requeue up to attempt 3); events timeline and SSE stream; an M1 fake agent that writes `m1/hello.py` into the jail and runs it. Migration `0002`. D-046. 126 tests pass.
- Verified live: uvicorn + B's `scripts/fake_worker.py` (b/fake-worker): pair, claim, start, logs, result, run `done`.
- State: M1 backend complete. Not yet shown: a real command on a laptop and the live log in the UI (needs C's run page).
- Next: run B's real worker against this backend on a Linux/macOS laptop; C points the run page at `/runs/{id}/stream`; then M2 (LLM wrapper, agent loop, intake, paper path).
- Blockers / gotchas: B's `worker/runner.py` (b/runner) is POSIX-only (`import resource`, `os.killpg`, `start_new_session`); it crashes on import on Windows. Q-09 (team OS) decides whether it needs a Windows path. B should also read `project_id` from the claim to jail jobs under `WORKSPACE_ROOT/<project_id>/`, and honour `approved`. Not built yet: `POST /worker/artifacts`, browser uploads (`POST /projects/{id}/inputs`), Brief and plan approval (M2).
- Touches contracts? Yes: API.md section 9 (`approved` on claim), section 5 (stream behaviour, events route), section 8 (job approval payload, expiry, edit not supported yet); ARCHITECTURE section 4 (`jobs.approved`, `cancel_requested`, `policy_reason`); `shared/openapi.yaml`.

### 2026-10-10 · Dev A (Shourya), with Claude · backend M2 to M5
- Done (M2, real agents): LLM wrapper over the gateway (tiers, 48 KB trimming, 4000-token output cap, retries with backoff, tier fallback, cache, LangSmith hook); JSON-in-text tool protocol; generic agent loop with suspend/resume and schema repair; 22 backend tools; background intake (arXiv, GitHub README, dataset HEAD through an SSRF-guarded fetcher) writing the Research Brief; deterministic activation and per-entry-type fragments; Meta-Controller plan with `plan` approval (approve, edit, reject re-plans, expiry cancels); orchestrator walking the graph in code; Executor service (seeds by budget, entry-point templates, `results_path`, B's harness shape).
- Done (M3, full loop): Debugger on failed experiments (max 2 cycles, failure attribution, verified `error_fix` lessons); Ledger; Librarian on Supermemory with a keyword fallback; statistics in code for the Evaluator; Designer branches, Meta-Controller `select_branches` and `decide_branches` with evidence; re-planning triggers (signals, task failure, unresolved failure, budget 70 percent, chat, input added) with minor/major diffs and plan revisions; chat; Reporter and the report artifact.
- Done (M4, evolution and memory): rewards per task (O_det per role, council blend, cost, feedback; finalised at run end); Performance Council runner (3 judges, blind, retried when rate-limited); evolution triggers (refine, retire, merge, runtime and planning gaps), resolution ladder (reuse, restore, template, specialise, fresh spawn), guardrails in code, evolution approvals with prompt diffs, 2-task probation with rollback; all four entry paths and combined inputs plan; question path candidate pick.
- Done (M5, hardening, code side): n8n outbound signed webhooks and the inbound decision hook (one single-use token per decision); per-user, chat and hook rate limits; 1 MB JSON body cap; dataset upload relay to the worker with signed links; worker artifact uploads; Postgres URL support; `backend/Dockerfile` and `backend/start.sh`. Migration `0003`. D-047 to D-053. 186 tests pass.
- Verified live (real gateway, arXiv, GitHub; throwaway DB): intake facts correct; the Meta-Controller planned in one step; a failed task triggered a real re-plan; the council judged with real models. Found and fixed: gateway output cap of 4000 tokens (HTTP 400 above it), the gateway rate-limits per minute (longer backoff; council retries instead of dropping judges), a double-decompression bug in the fetcher, and the Paper Analyst reading the paper page by page (added a search option).
- State: the backend is feature-complete for the gates on our side. A run cannot finish end to end until a real worker runs experiment code.
- Next: B, see Q-27 (harness `--out-file`), Q-28 (Windows worker), the `approved` and `project_id` claim fields, n8n flow against D-051. C: run page on `/runs/{id}/stream`, approvals inbox (plan edit, evolution card with `prompt_diff` and lineage, candidate picker with `edited_payload.chosen`). A: deploy on Voroa (one instance, Q-29), UseShipReady scan, rehearse.
- Blockers / gotchas: gateway rate limits are unknown and bite with the council on (Q-23, Q-26); set `FEATURE_COUNCIL=false` if a demo stalls. KAN-sized papers need the search option; `extract_spec` has 12 steps.
- Touches contracts? Yes: API.md v0.6 (inputs upload, relay route, plan shape, new events, experiment-job contract, n8n format change in section 11), ARCHITECTURE v0.5 (schema, deploy), AGENTS (memory fallback, entry points, council retry), `shared/schemas/implementer.json` (`workdir`), `shared/openapi.yaml`.

### 2026-10-11 · Dev A (Shourya), with Claude · dashboard, simulated mode, demo fixes
- Done: dashboard in `frontend/` using C's design system: sign-in (owner password), `/dashboard` (worker pairing with copy-paste command, new run form or KAN example, runs list, approvals count), `/runs/<id>` (approval cards for plan, evolution with lineage and prompt diff, candidate pick, agent questions, risky jobs; pipeline; experiment tree with deltas and decision reasons; Brief and activation reasons; report; ledger; agent team with rolling rewards and spawned agents; live events over SSE; chat; task drawer with transcript, reward breakdown, three council judges, feedback), `/agents`, `/memory`. Next.js proxy for `/api/v1`. `backend/scripts/sim_server.py` (scripted AI, simulated worker; full KAN combined run with a Debugger fix and a fresh-spawn evolution in about 3 minutes). `/health` reports `mode`. D-054.
- Fixed during live demos: council and agent loop held the SQLite write lock across AI calls (approvals timed out; regression test added); network drops on a hotspot failed whole runs (now pause and retry); failed README fetch produced a false "not linked" fact; dashboard polling exceeded the rate limit (event-driven refresh, limit 300/min); SSE reconnect loop after a run ends.
- Verified: 189 backend tests; frontend type-check and production build; end to end in the browser against the simulated backend (sign in, start, approve plan, approve evolution, run done in 2.75 min, tree, report, task drawer, agents, memory, phone width).
- Next: C reviews the frontend (it is C's module) and merges with the landing page work; B fixes `pip_install` and `download` in the worker so live runs can complete.
- Touches contracts? Yes: `/health` adds `mode`; dashboard rate limit 300/min (API.md 12).
