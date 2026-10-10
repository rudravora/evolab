# EvoLab — docs index

> **EvoLab is a placeholder name.** Rename it in one pass when the team picks a real one (`grep -ri evolab docs/`).

Project: **Elevate 1.0, Problem Statement 03: An Evolving AI Research Environment** (DJSCE Institution's Innovation Council).
Sponsors: **UseShipReady** (production-readiness scoring), **Voroa** (deploy from GitHub), **n8n** (workflow automation).

## Read in this order

| # | File | What it is | Read it if you are |
|---|------|-----------|--------------------|
| 1 | [CONTEXT.md](CONTEXT.md) | The problem, the idea, key decisions, vocabulary | Everyone, first |
| 2 | [PRD.md](PRD.md) | What we build, priorities (P0/P1/P2), acceptance criteria, demo | Everyone |
| 3 | [WORKFLOW.md](WORKFLOW.md) | Step-by-step flow from inputs to report, with a runtime and build owner for every step; dynamic spawning; demo beats | Everyone |
| 4 | [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data flow, state machines, DB schema, safety, deployment | Backend, worker, infra |
| 5 | [API.md](API.md) | Every HTTP route, payloads, SSE events, webhooks | Backend, frontend, worker |
| 6 | [AGENTS.md](AGENTS.md) | Agent roster, tools, reward formula, evolution rules, memory | Backend / agent owner |
| 7 | [COORDINATION.md](COORDINATION.md) | How we work together without blocking each other | Everyone |
| 8 | [logs/DEVLOG.md](logs/DEVLOG.md) | Append-only progress log | Everyone, at every handoff |
| 9 | [logs/DECISIONS.md](logs/DECISIONS.md) | Decisions and why | Everyone, before re-debating something |
| 10 | [logs/OPEN_QUESTIONS.md](logs/OPEN_QUESTIONS.md) | Unresolved items with owners | Everyone |

## Status of these docs

These were written from the planning conversation on 2026-10-10. They are a **starting contract, not scripture**. Anything marked `VERIFY` was written from memory or assumption and must be checked before it is relied on. Change a doc by PR, and record the reason in `logs/DECISIONS.md` if the change alters a decision.

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-10-10 | Initial set: CONTEXT, PRD, ARCHITECTURE, API, AGENTS, COORDINATION, logs |
| 0.2 | 2026-10-10 | Team of 3: COORDINATION rewritten (roles A, B, C; gates, sleep plan, load balancing); PRD gains the cut ladder (6a) and extra risks; CONTEXT assumptions; DECISIONS D-023 to D-027; OPEN_QUESTIONS owners reassigned; DEVLOG team table. **Unchanged:** ARCHITECTURE, API, AGENTS |
| 0.3 | 2026-10-10 | Multi-input intake and dynamic team: all four entry paths (paper, question, codebase, dataset) at full depth with combined inputs; Research Brief and typed reference targets; dynamic activation; hybrid plan/re-plan; capability tags and five-step spawning ladder; domain agents as dormant templates (out of v1); combined-input demo; revised work split. **New:** WORKFLOW.md. **Updated:** CONTEXT, PRD (G8–G9, P0 12–15, build order 6a, FR-32 to FR-40, acceptance 11–14), ARCHITECTURE (3.0a, 3.0b, 3.9, 3.10, schema), API (combined intake, brief, plan routes, new SSE events and approval types), AGENTS (tags, signals, activation rules, fragments, ladder, templates), COORDINATION, DECISIONS (D-028 to D-037), OPEN_QUESTIONS (Q-18 to Q-22), DEVLOG |
| 0.4 | 2026-10-10 | Supermemory behind the Librarian for memory and context; LangSmith tracing; a 3-judge Performance Council (one per model) blended into the outcome term of the reward; three model tiers (GPT-5.6 Luna, DeepSeek V4 Pro, GPT-5 Mini). Seed agents created in `backend/agents/` with schemas in `shared/schemas/` and examples in `shared/examples/agents/`. **Updated:** AGENTS, ARCHITECTURE, API (additive), WORKFLOW, PRD (FR-17, FR-41 to FR-43), DECISIONS (D-038 to D-041), OPEN_QUESTIONS (Q-23 to Q-26), DEVLOG. `Workflow.pdf` is still v0.3 |
| 0.5 | 2026-10-10 | Backend M0 to M5 built (see DEVLOG). **Updated:** API (v0.6: sign-in, M1 job pipe, uploads and relay, experiment-job contract, new events, n8n one-token-per-decision), ARCHITECTURE (v0.5: schema, agent loop and orchestrator notes, 4000-token output cap, deploy), AGENTS (memory fallback, entry-point contract), DECISIONS D-042 to D-053, OPEN_QUESTIONS Q-27 to Q-29 |

## Not yet planned (do these next)

- Hour-by-hour 24-hour timeline against the build order in PRD 6a (needs names for A, B, C)
- Demo script and fallbacks
- Submission pieces (pitch deck, README for the repo)
