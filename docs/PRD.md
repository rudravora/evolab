# PRD: EvoLab (working name)

Version 0.1, 2026-10-10. Owner: team. Status: draft for team review.

## 1. Summary

EvoLab is a web-based research environment where a team of LLM agents turns a paper, question or idea into reproducible experiments, investigates what-if variations in parallel, explains differences from the published result, and improves itself over time. A researcher controls and understands everything through a dashboard (desktop and phone). Heavy computation runs on workers (first the researcher's laptop) that pull jobs from the backend.

## 2. Problem

ML research is spread across papers, code, datasets, notebooks, compute platforms, notes and chat. Reproducing a paper means fighting dependencies, environments, data issues and hyperparameters. Knowledge from failures is rarely kept. Existing agent systems use fixed roles and workflows, but each paper needs a different mix of skills.

## 3. Goals and non-goals

**Goals**
- G1. Autonomously reproduce the key result of one real paper on modest compute.
- G2. Autonomously investigate at least one what-if extension, with explainable branch decisions.
- G3. Explain where and why results differ from the paper, with evidence (ledger).
- G4. Show a **visibly evolving** agent team driven by a reward loop (spawn, refine, merge, retire).
- G5. Retain and reuse lessons across runs (measurable speed-up on a repeat-type run).
- G6. Keep the researcher in control (inspect, approve, reject, redirect), including from a phone.
- G7. Deploy publicly and pass UseShipReady's checks with a good score.

**Non-goals**
- Training or fine-tuning any model as part of "self-improvement".
- Supporting arbitrary research domains perfectly. We demo one paper well.
- Native mobile apps (responsive web only).
- Multi-user collaboration beyond a shared project view.
- Kaggle worker, full Mode B porting.

## 4. Users

- **Primary:** an ML student or researcher with a laptop and free-tier cloud accounts who wants to reproduce and probe a paper without babysitting environments.
- **Secondary:** judges evaluating the demo live.

## 5. Mapping to the problem statement

| PS-03 requirement | Our feature | Priority |
|---|---|---|
| Accept paper, question, algorithm, dataset, codebase, idea | Intake screen (paper path complete, question path via "find candidate papers" step) | P0 / P1 |
| Execute across local, Kaggle, Colab, remote | Pull-based worker; laptop first | P0 (laptop), P2 (Colab) |
| Handle dependencies, data issues, errors, constraints, hyperparameters | Env/Data Engineer, Debugger, Executor budget scaling | P0 |
| Meta-controller spawns/adapts agents | Meta-Controller with spawn/refine/merge/retire | P0 |
| Reward loop (outcome, cost, feedback) | Reward formula and per-agent scoring | P0 |
| Go beyond reproduction (diagnose, repair, compare, explain differences) | Evaluator, Ledger, Reporter | P0 |
| What-if investigation of multiple possibilities | Experiment Designer and exploration tree | P0 |
| Knowledge retained across experiments | Memory (Librarian) | P0 |
| Notes, Markdown, datasets, code, documents, records | Notes panel, project workspace, report, experiment records | P1 |
| Remote and mobile control | Responsive dashboard plus n8n phone approvals | P0 (responsive), P1 (n8n) |
| Autonomy with human control | Approval gates and branch controls | P0 |
| Demonstrate on modest compute | CPU-sized KAN vs MLP plan | P0 |
| UI shows what agents do, why, performance, evolution | Run page, agent detail, tree, transcripts | P0 |
| Not just a notebook or chat | Panels beyond chat | P0 |

## 6. Scope and priorities

**P0 (must work in the demo)**
1. Intake screen: goal text, paper link or PDF, optional repo, optional dataset, "Try the KAN vs MLP example".
2. Worker pairing and job pull loop (laptop, started via one command).
3. Agent loop with tool calling, suspension while jobs run, resume on result.
4. Agents: Meta-Controller, Paper Analyst, Repo Auditor, Env and Data Engineer, Implementer (Mode A), Debugger, Experiment Designer, Evaluator, Reporter. Services: Executor, Ledger, Librarian.
5. Plan approval gate before expensive work.
6. Live run page: agent team with scores, experiment tree, logs and metrics, chat, approvals.
7. Reward scoring and at least one **visible** evolution event of each kind that the demo path can trigger (spawn and refine at minimum; merge or retire if it fires).
8. Memory with seeded and learned entries; one demonstrable reuse.
9. Deviation ledger and "why results differ" report section.
10. Safety basics: workspace jail, command policy, timeouts, keys only on backend.
11. Deployed to Voroa; UseShipReady scan run and findings addressed.

**P1 (should)**
- n8n phone alerts and approve/reject buttons.
- Question-only entry ("find candidate papers, you pick").
- Agent detail page with version history and transcripts.
- Notes panel and Markdown export.
- Memory view.

**P2 (stretch)**
- Mode C clean-room KAN layer and dual-track comparison.
- Colab worker.
- Second small paper to demonstrate memory transfer (e.g., trees vs deep learning on tabular data).
- Dataset-only and repo-only entries.

### 6a. Capacity plan for a team of 3

With three developers (A: backend, agents and deploy; B: worker, experiments and n8n; C: frontend, mocks and demo), not everything in P0 can be built at full depth. Build the **thin path through all of P0 first**, then deepen. If a gate slips, cut in this order (cut from the top first). Anything cut must be recorded in `logs/DECISIONS.md` and must not be presented as working in the demo.

| Cut order | What to cut or simplify | Honest fallback |
|---|---|---|
| 1 | P2 items (Mode C, Colab, second paper, dataset-only and repo-only entry) | Not shown |
| 2 | n8n phone approvals (FR-26, FR-27) | Phone approvals through the responsive dashboard only |
| 3 | Notes panel, memory view, agent-detail diffs (parts of FR-21) | Show transcripts and version list only |
| 4 | Question-only entry (P1) | Paper link entry only |
| 5 | Repo Auditor as a live LLM agent | Lightweight audit: deterministic smoke test plus a stored audit for the demo repo, labelled as seeded |
| 6 | Paper Analyst live extraction | Run live if possible, but keep a pre-extracted reproduction spec for the demo paper as a **labelled fallback** |
| 7 | Merge and retire evolution actions | Spawn and refine only (these are the visible ones); document merge and retire as designed but not triggered |

**Never cut:** the job pipe (worker pull), plan approval, the Debugger plus memory write and reuse, the exploration tree with decision reasons, the ledger, the report's "why we differ" section, rewards visible per agent, at least one visible spawn or refine, deployment, and the replay fallback.

**Suggested agent build order** (A and B): Meta-Controller (simple task graph), Env and Data Engineer, Implementer (Mode A), Executor service, Debugger, Evaluator, Experiment Designer, Reporter, Librarian and Ledger services, then Paper Analyst and Repo Auditor depth. This gets a real baseline running before the less visible agents.

## 7. Core user flow

1. **Intake.** User enters goal "KAN vs MLP research" (or clicks the example), optionally adds a paper, repo, dataset or notes. A worker must be connected to execute; the intake shows the pairing command if none is online.
2. **Plan.** The Meta-Controller builds a task graph. Paper Analyst extracts the reproduction spec. Repo Auditor audits official code and recommends a mode. The Designer drafts a CPU-sized experiment plan.
3. **Approve.** The user approves, edits or rejects the plan (dashboard or phone).
4. **Execute.** Env and Data Engineer set up the environment and data (jobs on the worker). Implementer patches code. Executor runs baseline experiments. Debugger handles failures, consulting memory.
5. **Evaluate.** Evaluator compares results with the paper's claim across seeds and writes the verdict and reward signals.
6. **Explore.** Designer proposes what-if branches. Branches run in parallel within budget. The Meta-Controller expands or prunes with recorded reasons. Risky or expensive steps ask for approval.
7. **Report.** Reporter produces a Markdown report with results, the "why we differ" section built from the ledger, and links to commits.
8. **Learn.** Rewards are computed, memory is updated, and the Meta-Controller proposes evolution actions, which the user approves.

## 8. Functional requirements

IDs are referenced in commits, issues and the DEVLOG.

**Intake and projects**
- FR-1. Create a project with a goal and optional inputs (paper URL or PDF, repo URL, dataset upload or URL, notes).
- FR-2. Inputs are stored and treated as untrusted data. Repo links are recorded, never executed at intake.
- FR-3. "Try the example" prefills the KAN vs MLP project.
- FR-4. If no worker is online, show the pairing command; planning may proceed, execution waits.

**Workers**
- FR-5. Generate a worker token and a copy-paste start command.
- FR-6. Worker registers, heartbeats (status, CPU, RAM), claims jobs atomically, streams logs, and reports results.
- FR-7. Worker enforces the workspace jail, command policy, timeouts and output caps locally as well as the backend enforcing them at job creation.

**Agents**
- FR-8. Agents are stored with versioned prompts, tools and a model. One generic loop executes any agent.
- FR-9. The loop suspends a task while it waits for a job and resumes on the job result.
- FR-10. Every agent message and tool call is stored and viewable (the "why" transcript).
- FR-11. The Meta-Controller can spawn an agent (new row plus version), propose a refinement, merge, or retire, subject to the guardrails in AGENTS.md.
- FR-12. Per-task reward is computed and stored per agent per task.

**Experiments**
- FR-13. Branch tree with statuses and recorded decision reasons.
- FR-14. Experiments record config, seed, commit SHA, metrics and cost.
- FR-15. Executor scales epochs and data subsets to the run budget and kills runaway jobs.

**Memory and ledger**
- FR-16. Memory entries of types error_fix, config_outcome, audit, gotcha and lesson, with success and fail counts.
- FR-17. Retrieval order: exact signature, then FTS keyword, then optional embedding similarity; top 3 injected into agent context; usefulness logged.
- FR-18. Every deviation from the paper or official code is written to the ledger **at the moment of change** with a category.

**Dashboard**
- FR-19. Run page with agent team, experiment tree, logs, metrics, notes, ledger, chat and approvals.
- FR-20. Live updates through Server-Sent Events.
- FR-21. Agent detail page: version timeline, scores over time, task transcripts.
- FR-22. Approval inbox with approve, edit and reject.
- FR-23. Report view with results tables, plots and the "why we differ" section.
- FR-24. Responsive layout that is usable on a phone for the run summary, approvals and chat.
- FR-25. Pause, resume, cancel a run; pause or kill a branch.

**Integrations**
- FR-26. Outbound webhooks to n8n for `approval_requested`, `job_failed`, `run_finished`.
- FR-27. Inbound n8n decision webhook using signed, single-use, expiring tokens.

**Safety and security**
- FR-28. LLM keys exist only in backend environment variables.
- FR-29. Auth on all dashboard routes, worker token on worker routes, signed tokens on hooks.
- FR-30. Security headers, locked CORS, rate limits, input validation, no stack traces to clients.
- FR-31. Append-only `events` table records commands, diffs, approvals and evolution actions.

## 9. Non-functional requirements

- **Budget:** the KAN vs MLP baseline fits in about 60 to 90 minutes of laptop CPU; what-ifs use reduced settings.
- **Latency:** worker pickup within 3 seconds of job creation (polling every 2 seconds is acceptable); dashboard events appear within 2 seconds.
- **Resilience:** backend restart does not lose queued jobs or suspended tasks; a worker that goes offline has its running jobs re-queued after a timeout.
- **Cost control:** per-run caps on tokens, wall time and concurrent agent loops.
- **Usability:** the main run page is understandable without explanation; every agent decision has a visible "why".
- **Honesty:** seeded memory and spawned-vs-seed agents are labelled; unverified claims are never presented as results.

## 10. Acceptance criteria for the demo path

1. From the intake screen, "Try the example" starts a run and lands on the run page within 5 seconds.
2. A plan appears for approval; approving it starts execution on the connected laptop worker.
3. Baseline KAN vs MLP experiments complete with metrics for at least 2 tasks and 3 seeds each.
4. At least one injected or natural failure is diagnosed and fixed by the Debugger, and a memory entry is written.
5. At least 3 what-if branches run, at least one is expanded and one pruned, each with a visible reason.
6. A report is generated with a "why we differ" section citing at least 3 ledger entries.
7. The agent team view shows scores, and at least one spawn and one refine are visible with version history.
8. A second run (or a different what-if) shows measurable reuse of a learned memory entry (fewer failed attempts or less time).
9. An approval is completed from a phone.
10. The deployed app has a UseShipReady scan with no critical findings left open.

## 11. Success metrics

| Metric | Target |
|---|---|
| Baseline reproduction completes unattended | Yes |
| What-if branches explored | 3 or more |
| Failures auto-fixed without human help | At least 1 |
| Run-2 vs run-1 failed attempts or time | Visibly lower |
| Branch decisions with recorded reasons | 100 percent |
| Ledger entries cited in report | 3 or more |
| UseShipReady critical findings | 0 |

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Free-tier LLM rate limits | Agents stall mid-demo | Provider wrapper with fallback, caching, concurrency cap of 2 or 3, deterministic code for non-LLM work, pre-recorded fallback run |
| `pykan` API drift or install trouble | Reproduction blocked | Pin a known version early; treat drift as a feature (Debugger and spawn demo) but have a tested lockfile |
| CPU too slow | Demo runs too long | Reduced grids, fewer seeds, cached baseline results |
| Evolution looks fake | Judges unimpressed | Real triggers, visible diffs between prompt versions, logged reasons, approvals |
| LLM-written code harms laptop | Safety incident | Jail, policy, approvals, clean env, timeouts |
| Scope too big for 24 hours with only 3 developers | Nothing works end to end | Thin end-to-end path first, strict P0/P1/P2, the cut ladder in section 6a, and cuts recorded in DECISIONS |
| Backend load concentrated on A (agents, evolution, memory, deploy) | A becomes the bottleneck | B takes the Librarian retrieval and Ledger once the worker is stable; C takes approvals UI and SSE contract tests; A and B pair on the job pipe early |
| Sleep gaps with only 3 people | Nobody can fix the pipe at a critical moment | Staggered sleep plan in COORDINATION.md section 6; no one sleeps through the middle stretch alongside another owner of the pipe |
| Network failure at venue | Live demo fails | Local-only mode (backend on localhost), recorded fallback |
| Deployment issues late | Lose UseShipReady score | Deploy in the first hours, scan early |

## 13. Milestones (draft; the full timeline is planned separately)

| Gate | Definition |
|---|---|
| M0 Contracts frozen | API.md, schema, agent I/O contracts agreed; mock server running |
| M1 Pipe works | Dashboard creates a run, a fake agent creates a job, the laptop worker runs it, the result shows live |
| M2 Real agents | Paper Analyst through Executor produce a real baseline experiment |
| M3 Full loop | Debugger, branches, evaluation, ledger, report |
| M4 Evolution and memory | Rewards, spawn/refine visible, memory reuse proven |
| M5 Hardening | Deployed on Voroa, UseShipReady fixes, demo rehearsed, fallback recorded |

## 14. Open questions

Tracked in [logs/OPEN_QUESTIONS.md](logs/OPEN_QUESTIONS.md).
