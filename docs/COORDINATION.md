# COORDINATION

Version 0.2 (team of 3: two backend-side devs and one frontend dev). How three people build one system in about 24 hours without blocking each other. Names go in `logs/DEVLOG.md`.

## 1. The six rules

1. **Contract first.** API.md, the DB schema in ARCHITECTURE.md, and the JSON schemas in `shared/schemas/` are the contract. Freeze them early (gate M0). After the freeze, changes need a PR that edits the doc, updates the example JSON and gets a heads-up in the group.
2. **Mock everything at the seams.** Nobody waits for anybody. C builds against a **mock backend**. A builds against a **fake worker**. B builds against a **fake backend** that hands out a canned job. (Table in section 4.)
3. **One owner per module, anyone can review.** The owner decides; others raise concerns in review. Do not edit someone else's module without telling them.
4. **Thin vertical slice before depth.** Dashboard, backend, worker and back with a fake agent (gate M1) before anyone polishes anything.
5. **Decisions live in files, not chats.** If it was decided in WhatsApp, it is not decided until it is in `logs/DECISIONS.md`.
6. **Three people means no spare capacity.** Cut scope early using the ladder in PRD.md section 6a instead of working harder late. Every dev must be able to run the whole system locally and fix a broken demo path.

## 2. Roles (3 devs)

The earlier four-role plan had a separate integration and demo role (D). With three devs, D's duties are split across A, B and C below. The team already has one frontend dev; the two backend-side devs take A and B.

| Role | Owns | Primary files |
|---|---|---|
| **A: Backend, agents, deploy** | FastAPI app, orchestrator, agent runtime, LLM wrapper, Evolution engine, Librarian, Ledger, approvals, SSE; **plus** Voroa deploy, security hardening, UseShipReady scans and fixes, `.env.example` | `backend/`, deploy config, `docs/AGENTS.md` |
| **B: Worker, experiments, n8n** | `worker.py`, policy and jail, the KAN vs MLP experiment code, cached baseline results, seeded memory, dry runs, fake worker; **plus** n8n flows (phone approvals, alerts) after M2 | `worker/`, `experiments/`, `scripts/fake_worker.py` |
| **C: Frontend, mocks, demo** | All screens, SSE client, charts, tree, mobile layout, mock server and example JSON; **plus** demo script, fallback replay mode and recording, DEVLOG and docs hygiene | `frontend/`, `shared/examples/`, `scripts/mock_server.py` |

**Who verifies what** (replaces the old role D): A verifies M0 and M1 and runs the deploy and UseShipReady scans; B verifies M2; C runs the demo rehearsals; everyone verifies M3 and M4 together.

**Pairing at the start (bus factor).** A and B pair for the first hour on the pipe (job creation to worker pull to result back), so either can fix the other's side. C pairs with A for 30 minutes on the SSE event shapes. After that each works solo on their module.

Everyone owns the **tests of their own module**, and everyone must be able to start backend, worker and frontend locally from the README.

## 3. Repo and branching

- **Monorepo**, structure in ARCHITECTURE.md section 10.
- `main` is always runnable. Never push directly; open a PR. With three people, one quick review is enough, and the author may merge after it.
- **Branch names:** `a/<topic>`, `b/<topic>`, `c/<topic>` (owner letter first), e.g. `a/agent-loop`, `c/run-page`.
- **Small PRs**, under about 300 lines when possible, merged within an hour. Rebase on `main` before merging.
- **Commit messages:** `<area>: <what> (FR-12)`, e.g. `worker: add jail path check (FR-7)`. Reference FR ids from PRD.md.
- `.env.example` is committed with variable names and no values. **Real keys never go in git** (check the diff before pushing).
- Generated files (`openapi.yaml`) are committed so the frontend can read them without running the backend.

## 4. Contracts and mocks

| Contract | Source of truth | Mock | Mock owner |
|---|---|---|---|
| HTTP API | `docs/API.md` and `shared/openapi.yaml` | `scripts/mock_server.py` serving `shared/examples/*.json` | C |
| SSE events | API.md section 5 | `scripts/mock_sse.py` replays a recorded event stream | C |
| Agent I/O | `shared/schemas/<role>.json` | Canned outputs in `shared/examples/agents/` | A |
| Worker jobs | API.md section 9 | `scripts/fake_worker.py` (accepts jobs, returns canned logs and results) | B |
| DB schema | ARCHITECTURE.md section 4 and migrations | `scripts/seed_db.py` for demo data | A |

Rule: **when you change a payload, update the example JSON in the same PR**, so mocks never lie. If an example and API.md disagree, the example is the tiebreaker for *behaviour already built*, and API.md for anything not built yet; fix the loser in the same PR.

## 5. Integration gates

Everyone stops and integrates at these gates. If a gate slips, cut scope with the ladder, not the gate.

| Gate | Pass condition | Who verifies |
|---|---|---|
| **M0 Contracts frozen** | API, schema and agent I/O agreed; mock server and fake worker run | A |
| **M1 Pipe works** | Dashboard creates a run, a fake agent creates a job, the laptop worker runs a command, the live log appears in the UI | A (with B and C) |
| **M2 Real agents** | Paper Analyst through Executor produce a real baseline experiment on the laptop | B |
| **M3 Full loop** | Failure, Debugger fix, branches, evaluation, ledger, report | All three |
| **M4 Evolution and memory** | Rewards visible, spawn or refine visible, memory reuse proven | All three |
| **M5 Hardening** | Deployed on Voroa, UseShipReady findings fixed, rehearsed twice, fallback recorded | A (deploy), C (rehearsal) |

Exact clock times come from the 24-hour timeline (not planned yet). Rule of thumb: M1 by hour 6 to 8, and **deploy to Voroa by hour 6** even if the app is ugly.

## 6. Communication rhythm

- **Group chat** for quick pings and blockers, not decisions.
- **Sync every 3 hours**, 10 minutes, standing: what shipped, what is blocked, what is next, whether the cut ladder needs to move. Write the result as one DEVLOG entry (C keeps the log; anyone can add).
- **Handoff rule:** when you stop for sleep or a break, add a DEVLOG entry with *state, next step, gotchas*, so another dev can continue.
- **Blockers:** post `BLOCKED:` plus what you need and from whom. The owner replies within 15 minutes or names someone who will.
- **Sleep plan (important with three people).** Never have two people asleep at once in the middle stretch, and never have the person who owns the agent loop *and* the person who owns the worker both offline. Suggested: one person sleeps first, then the second; the third sleeps after M4 so someone is always awake to own the pipe. Nobody does the final integration or deploy while exhausted; do that when at least two people are rested.

## 7. Logs: how to use the three files

| File | Purpose | Rule |
|---|---|---|
| [DEVLOG.md](logs/DEVLOG.md) | Chronological progress and handoffs | **Append only**, newest at the **bottom**, one entry per sync or handoff |
| [DECISIONS.md](logs/DECISIONS.md) | Decisions with reasons | One row per decision; do not delete, supersede with a new row |
| [OPEN_QUESTIONS.md](logs/OPEN_QUESTIONS.md) | Unresolved items with an owner | Move to DECISIONS when answered |

The DEVLOG entry template is at the top of that file. Keep entries short and factual.

## 8. Definition of done (per task or PR)

- Works on the demo path, not just in isolation
- Matches the contract (API.md or schema); examples updated
- Has at least a smoke test or a manual test note in the PR
- No secrets, no debug prints with sensitive data
- Errors return the standard error shape
- DEVLOG updated if it affects others

## 9. Code quality guardrails (cheap and worth it)

- **Typing and validation:** Pydantic models on the backend (they generate the OpenAPI), TypeScript types on the frontend generated from `openapi.yaml` if time permits.
- **Formatting:** one formatter per language (ruff or black, prettier). Run on commit; do not argue style.
- **Feature flags:** `FEATURE_N8N`, `FEATURE_EMBEDDINGS`, `FEATURE_MODE_C`, `AUTO_APPROVE_DEMO` as env flags so unfinished work never breaks the demo path.
- **Fail loudly in dev, gracefully in demo:** every external call (LLM, arXiv, n8n) has a timeout and a visible error state in the UI.

## 10. Risk management

- **Fallback assets (C, with B's data):** record a full successful run early (screen recording plus the saved event stream). Keep a **replay mode** that streams the saved events if live runs fail. Replays must be labelled as replays in the UI.
- **Cached baseline (B):** keep baseline results in the repo so the demo does not depend on a 60-minute run.
- **Pin versions (all):** `requirements.lock` for backend, worker and experiments. A broken `pip install` at 3 AM is the most likely killer.
- **Rate limits (A):** monitor LLM usage; agree on a cap per run and a fallback provider.
- **Scope police:** after M2, anything not on the P0 list needs a unanimous yes. Use the cut ladder, in order.
- **Load balancing:** A carries the heaviest module (agents, evolution, memory, deploy). B should pick up the Librarian's retrieval code or the Ledger service once the worker is stable, and C should take over the approvals UI and SSE contract tests early so A does not carry them.

## 11. Pre-kickoff checklist

- [ ] Names and roles filled into the DEVLOG header
- [ ] Repo created with the structure, `.env.example`, `main` protected
- [ ] LLM provider chosen, keys shared through a safe channel (not committed)
- [ ] Voroa project connected to the repo; first deploy of an empty health endpoint
- [ ] UseShipReady scan run once on that empty deploy to see the baseline
- [ ] n8n workspace created; webhook URL and signing secret agreed (can wait until after M2)
- [ ] `pykan` version pinned and a 5-minute smoke test run on at least two laptops
- [ ] Organizers asked: credits, Wi-Fi, power, internet restrictions, exact times
- [ ] Mock server, fake worker and `shared/examples/` skeletons committed

## 12. Mid-event pitfalls to watch for

- Frontend blocked because the backend was not ready: use the mock server.
- Backend and worker disagree on a payload: the example JSON in `shared/examples/` is the tiebreaker for built behaviour, then API.md.
- Everyone edits the same file (usually the run page or `orchestrator.py`): split into modules early.
- Nobody tests the failure path: schedule one deliberate failure (bad version) and watch the Debugger, memory and evolution events fire.
- Last-hour feature creep: freeze features at a fixed time and spend the rest on rehearsal and the fallback.
- One person becoming the only one who understands the agent loop: pair early and keep the agent loop file small and commented.
