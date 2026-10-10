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
