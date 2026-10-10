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
