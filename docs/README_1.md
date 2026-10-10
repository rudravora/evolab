# EvoLab — docs index

> **EvoLab is a placeholder name.** Rename it in one pass when the team picks a real one (`grep -ri evolab docs/`).

Project: **Elevate 1.0, Problem Statement 03: An Evolving AI Research Environment** (DJSCE Institution's Innovation Council).
Sponsors: **UseShipReady** (production-readiness scoring), **Voroa** (deploy from GitHub), **n8n** (workflow automation).

## Read in this order

| # | File | What it is | Read it if you are |
|---|------|-----------|--------------------|
| 1 | [CONTEXT.md](CONTEXT.md) | The problem, the idea, key decisions, vocabulary | Everyone, first |
| 2 | [PRD.md](PRD.md) | What we build, priorities (P0/P1/P2), acceptance criteria, demo | Everyone |
| 3 | [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data flow, state machines, DB schema, safety, deployment | Backend, worker, infra |
| 4 | [API.md](API.md) | Every HTTP route, payloads, SSE events, webhooks | Backend, frontend, worker |
| 5 | [AGENTS.md](AGENTS.md) | Agent roster, tools, reward formula, evolution rules, memory | Backend / agent owner |
| 6 | [COORDINATION.md](COORDINATION.md) | How we work together without blocking each other | Everyone |
| 7 | [logs/DEVLOG.md](logs/DEVLOG.md) | Append-only progress log | Everyone, at every handoff |
| 8 | [logs/DECISIONS.md](logs/DECISIONS.md) | Decisions and why | Everyone, before re-debating something |
| 9 | [logs/OPEN_QUESTIONS.md](logs/OPEN_QUESTIONS.md) | Unresolved items with owners | Everyone |

## Status of these docs

These were written from the planning conversation on 2026-10-10. They are a **starting contract, not scripture**. Anything marked `VERIFY` was written from memory or assumption and must be checked before it is relied on. Change a doc by PR, and record the reason in `logs/DECISIONS.md` if the change alters a decision.

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-10-10 | Initial set: CONTEXT, PRD, ARCHITECTURE, API, AGENTS, COORDINATION, logs |
| 0.2 | 2026-10-10 | Team of 3: COORDINATION rewritten (roles A, B, C; gates, sleep plan, load balancing); PRD gains the cut ladder (6a) and extra risks; CONTEXT assumptions; DECISIONS D-023 to D-027; OPEN_QUESTIONS owners reassigned; DEVLOG team table. **Unchanged:** ARCHITECTURE, API, AGENTS |

## Not yet planned (do these next)

- Hour-by-hour 24-hour timeline and work split (needs team size and names)
- Demo script and fallbacks
- Submission pieces (pitch deck, README for the repo)
