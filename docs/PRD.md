# PRD: EvoLab (working name)

Version 0.3, 2026-10-10. Owner: team. Status: draft for team review. Step-by-step flow and owners: [WORKFLOW.md](WORKFLOW.md).

## 1. Summary

EvoLab is a web-based research environment where a team of LLM agents turns a paper, question, codebase or dataset (or any mix of them) into reproducible experiments, investigates what-if variations in parallel, explains differences from the published result, and improves itself over time. A researcher controls and understands everything through a dashboard (desktop and phone). Heavy computation runs on workers (first the researcher's laptop) that pull jobs from the backend.

## 2. Problem

ML research is spread across papers, code, datasets, notebooks, compute platforms, notes and chat. Reproducing a paper means fighting dependencies, environments, data issues and hyperparameters. Knowledge from failures is rarely kept. Existing agent systems use fixed roles and workflows, but each paper needs a different mix of skills.

## 3. Goals and non-goals

**Goals**
- G1. Turn any of a paper, question, codebase or dataset into a reproducible investigation on modest compute; on the paper path, autonomously reproduce the paper's key result.
- G2. Autonomously investigate at least one what-if extension, with explainable branch decisions.
- G3. Explain where and why results differ from the paper, with evidence (ledger).
- G4. Show a **visibly evolving** agent team driven by a reward loop (spawn, refine, merge, retire).
- G5. Retain and reuse lessons across runs (measurable speed-up on a repeat-type run).
- G6. Keep the researcher in control (inspect, approve, reject, redirect), including from a phone.
- G7. Deploy publicly and pass UseShipReady's checks with a good score.
- G8. Accept all four input types and any combination of them, at full depth.
- G9. Decide which agents work from the inputs themselves (dynamic activation), re-plan when new facts arrive, and fill capability gaps through an explainable spawning ladder.

**Non-goals**
- Training or fine-tuning any model as part of "self-improvement".
- Supporting arbitrary research domains perfectly. We demo one combined-input run well.
- Building or testing domain-specific agents (materials, edge ML, CPU ML, 3D) in v1; they exist only as dormant templates (D-033).
- Native mobile apps (responsive web only).
- Multi-user collaboration beyond a shared project view.
- Kaggle worker, full Mode B porting.

## 4. Users

- **Primary:** an ML student or researcher with a laptop and free-tier cloud accounts who wants to reproduce and probe a paper without babysitting environments.
- **Secondary:** judges evaluating the demo live.

## 5. Mapping to the problem statement

| PS-03 requirement | Our feature | Priority |
|---|---|---|
| Accept paper, question, algorithm, dataset, codebase, idea | Four-mode intake, Research Brief, all four entry paths at full depth, combined inputs | P0 |
| Execute across local, Kaggle, Colab, remote | Pull-based worker; laptop first | P0 (laptop), P2 (Colab) |
| Handle dependencies, data issues, errors, constraints, hyperparameters | Env/Data Engineer, Debugger, Executor budget scaling | P0 |
| Meta-controller determines capabilities, spawns/adapts agents | Dynamic activation, hybrid re-planning, capability tags, resolution ladder, spawn/refine/merge/retire | P0 |
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
1. Four-mode intake screen: paper (link or PDF), question, codebase URL, dataset (URL, upload or worker path), notes, in any combination; "Try the example" loads the combined demo inputs.
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
12. All four entry paths at full depth: paper, codebase (audit first, inferred claim), dataset (profile, baseline suite), question (candidate pick plus mandatory exploratory branch).
13. Research Brief with facts and typed reference targets; typed Evaluator verdicts.
14. Dynamic activation for combined inputs; hybrid planning with re-planning triggers (minor auto-applied, major approved).
15. Capability tags and the five-step resolution ladder with approval and probation.

**P1 (should)**
- n8n phone alerts and approve/reject buttons.
- Agent detail page with version history and transcripts.
- Notes panel and Markdown export.
- Memory view.

**P2 (stretch)**
- Mode C clean-room KAN layer and dual-track comparison.
- Colab worker.
- Domain template stubs (22 dormant specs across four domains), if Q-20 says yes.
- Further domain-specific agents built and tested.

### 6a. Build order and safety net for a team of 3

All four entry paths are P0 at full depth (D-028). Build the **thin path through all of P0 first**, then deepen, in this order. If a gate slips, the path or feature furthest down the list is reduced first; every reduction is recorded in `logs/DECISIONS.md` and is never presented as working (D-037).

| Order | Build | If time runs short (honest fallback) |
|---|---|---|
| 1 | Job pipe, intake, Brief, paper path end to end | Never reduced |
| 2 | Hybrid re-planning, Debugger, memory, ledger, report | Never reduced |
| 3 | Codebase path (audit first, inferred claim) | README-only claim extraction |
| 4 | Dataset path (profile, baseline suite) | Baseline suite limited to two model families |
| 5 | Question path (candidates plus exploratory branch) | Exploratory branch limited to two hypotheses |
| 6 | Capability tags and the full ladder | Reuse, specialise and fresh spawn only; restore and template steps documented |
| 7 | n8n phone approvals (FR-26, FR-27) | Phone approvals through the responsive dashboard only |
| 8 | Notes panel, memory view, agent-detail diffs | Transcripts and version list only |
| 9 | Merge and retire evolution actions | Spawn and refine only; merge and retire documented as designed |
| 10 | P2 items (Mode C, Colab, domain template stubs) | Not shown |

**Never reduced:** the job pipe, the Research Brief, plan approval, dynamic activation, re-planning triggers, the Debugger plus memory write and reuse, the exploration tree with decision reasons, the ledger, the report's "why we differ" section, rewards visible per agent, at least one visible spawn or specialise, deployment, and the labelled replay fallback.

**Suggested agent build order** (A and B): Meta-Controller (simple task graph), Env and Data Engineer, Implementer (Mode A), Executor service, Debugger, Evaluator, Experiment Designer, Reporter, Librarian and Ledger services, then Paper Analyst and Repo Auditor depth, then the codebase, dataset and question fragments.

## 7. Core user flow

Full detail, with an owner for every step, is in [WORKFLOW.md](WORKFLOW.md).

0. **Setup.** The researcher pairs a laptop worker with one command and sets the run budget.
1. **Intake.** The researcher enters any mix of paper, question, codebase, dataset and notes (or clicks the example). Intake detects facts and links between inputs and writes the **Research Brief** with ranked reference targets.
2. **Activation and plan.** Activation rules turn facts into required capabilities; the Meta-Controller adapts the agent list (with reasons), builds the task graph from per-input fragments, and estimates cost. Capability gaps go to the spawning ladder.
3. **Approve.** The researcher approves, edits or rejects the plan (dashboard or phone); a question-only run also shows the candidate-paper picker.
4. **Execute.** The orchestrator runs the graph in code; agents create jobs on the worker; the Debugger handles failures, consulting memory; every deviation goes to the ledger.
5. **Re-plan on triggers.** New facts in `signals[]`, unresolved failures, branch results, researcher chat, budget thresholds or capability gaps call the Meta-Controller again; minor changes apply at once, major ones need approval.
6. **Evaluate and explore.** The Evaluator gives a typed verdict per reference target; the Designer proposes what-if branches (and, on the question path, the exploratory hypotheses); the Meta-Controller expands or prunes with recorded reasons.
7. **Report.** The Reporter writes results, verdicts and "why results differ" (or findings, for exploratory runs) from the ledger.
8. **Learn.** Rewards are computed, verified lessons stored, and evolution proposals (spawn, refine, merge, retire) go to the researcher for approval, followed by probation.

## 8. Functional requirements

IDs are referenced in commits, issues and the DEVLOG.

**Intake and projects**
- FR-1. Create a project from any combination of inputs (at least one): paper URL or PDF, question, repo URL, dataset (URL, browser upload or worker path; no size cap for now), notes.
- FR-2. Inputs are stored and treated as untrusted data. Repo links are recorded, never executed at intake.
- FR-3. "Try the example" prefills the combined demo inputs (KAN paper, `pykan` repo, tabular dataset, question).
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
- FR-17. Retrieval order: exact signature, then Supermemory search (D-038); top 3 injected into agent context; usefulness logged.
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

**Entry paths, activation and planning (v0.3)**
- FR-32. Intake detects facts about each input and the links between them, and writes a Research Brief with typed, ranked reference targets.
- FR-33. Question path: the Paper Analyst returns 3–5 candidate papers for a `candidate_selection` approval, and a mandatory exploratory branch runs alongside.
- FR-34. Codebase path: the Repo Auditor runs first, infers the claim from the README, reported results or a linked paper, and activates the Paper Analyst if a paper is linked.
- FR-35. Dataset path: the Env and Data Engineer profiles the data (size, columns, target, missing values, leakage flags); the Designer builds a baseline suite; published baselines are searched.
- FR-36. Activation rules turn facts into required capabilities; the Meta-Controller adapts the list with written reasons; inactive agents are shown with the reason.
- FR-37. Every agent output carries `signals[]` and an optional `suggested_next`; listed triggers call the Meta-Controller's `replan` mode; minor diffs auto-apply and major ones create a `plan` approval.
- FR-38. The Evaluator returns a typed verdict per reference target: `reproduced`, `partial`, `not_reproduced`, `baseline_established`, `exploratory`.
- FR-39. Agents and tasks carry capability tags; gaps are resolved by the ladder (reuse, restore, instantiate template, specialise, fresh spawn); steps 2–5 need an `evolution` approval and pass a 2-task probation.
- FR-40. The registry supports `kind: template`, `status: dormant` entries for domain agents; none are built or tested in v1.

**Council, memory and tracing (v0.4)**
- FR-41. A Performance Council of three judges (GPT-5.6 Luna, DeepSeek V4 Pro, GPT-5 Mini) scores every finished agent task; the median Q is blended into the outcome (`O = 0.5·O_det + 0.5·Q`); each judge's scores and rationale are visible on the task (D-040).
- FR-42. Every agent task is traced in LangSmith, with council scores attached as feedback (D-039).
- FR-43. Agents run on three model tiers (`strong`, `code`, `fast`) configured by env vars (D-041).

## 9. Non-functional requirements

- **Budget:** the KAN vs MLP baseline fits in about 60 to 90 minutes of laptop CPU; what-ifs use reduced settings.
- **Latency:** worker pickup within 3 seconds of job creation (polling every 2 seconds is acceptable); dashboard events appear within 2 seconds.
- **Resilience:** backend restart does not lose queued jobs or suspended tasks; a worker that goes offline has its running jobs re-queued after a timeout.
- **Cost control:** per-run caps on tokens, wall time and concurrent agent loops.
- **Usability:** the main run page is understandable without explanation; every agent decision has a visible "why".
- **Honesty:** seeded memory and spawned-vs-seed agents are labelled; unverified claims are never presented as results.

## 10. Acceptance criteria for the demo path

1. From the intake screen, "Try the example" starts the combined-input run and lands on the run page within 5 seconds.
2. A plan appears for approval; approving it starts execution on the connected laptop worker.
3. Baseline KAN vs MLP experiments complete with metrics for at least 2 tasks and 3 seeds each.
4. At least one injected or natural failure is diagnosed and fixed by the Debugger, and a memory entry is written.
5. At least 3 what-if branches run, at least one is expanded and one pruned, each with a visible reason.
6. A report is generated with a "why we differ" section citing at least 3 ledger entries.
7. The agent team view shows scores, and at least one spawn and one refine are visible with version history.
8. A second run (or a different what-if) shows measurable reuse of a learned memory entry (fewer failed attempts or less time).
9. An approval is completed from a phone.
10. The deployed app has a UseShipReady scan with no critical findings left open.
11. Each of the four entry paths, started alone, produces an approved plan; the paper path and at least one other path complete a run end to end.
12. In the combined run, the Brief shows at least two detected links between inputs, and the team view shows the activation list with reasons.
13. At least one re-plan is triggered by a task's `signals[]` and appears on the plan timeline with its trigger and reason.
14. At least one capability gap is resolved through the ladder with an approval card showing the gap, evidence, proposed spec and lineage, followed by probation.

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
| Entry paths producing an approved plan | 4 of 4 |
| Re-plans with recorded trigger and reason | 100 percent |

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
| Four full-depth entry paths on a 3-person team | Later paths unfinished | Build order and recorded reductions (section 6a, D-037); shared fragments and agents across paths |
| No upload size cap | Large uploads fail or exhaust Voroa bandwidth | Prefer URL or worker path for large files; relay uploads to the worker (Q-18) |
| Re-planning loops or churn | Budget burned on planning | Re-plan only on listed triggers; minor/major threshold; budget threshold trigger |
| Spawned agents underperform | Worse results, judges unconvinced | Approval with evidence, 2-task probation, automatic retire or rollback |

## 13. Milestones (draft; the full timeline is planned separately)

| Gate | Definition |
|---|---|
| M0 Contracts frozen | API.md, schema, agent I/O contracts agreed; mock server running |
| M1 Pipe works | Dashboard creates a run, a fake agent creates a job, the laptop worker runs it, the result shows live |
| M2 Real agents | Paper path: Paper Analyst through Executor produce a real baseline experiment |
| M3 Full loop | Debugger, branches, evaluation, ledger, report |
| M4 Evolution and memory | Rewards, ladder and spawn/specialise/refine visible, memory reuse proven; all four entry paths plan successfully |
| M5 Hardening | Deployed on Voroa, UseShipReady fixes, demo rehearsed, fallback recorded |

## 14. Open questions

Tracked in [logs/OPEN_QUESTIONS.md](logs/OPEN_QUESTIONS.md).
