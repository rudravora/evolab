# CONTEXT

Version 0.3. Everything a new teammate needs to understand the project in ten minutes. For the step-by-step flow and who owns each step, read [WORKFLOW.md](WORKFLOW.md).

## 1. The hackathon

- **Event:** Elevate 1.0, DJ Sanghvi College of Engineering (DJS NSDC / Institution's Innovation Council).
- **Format (from the UseShipReady event page):** Round 0 online on Unstop (pick a problem, submit a PPT, top 30 shortlisted). Round 1 is an offline hackathon at campus building an MVP, described as 24 hours. Teams of 2 to 4.
- **Timing:** the event page lists 10 Oct 2026 18:00 UTC to 12 Oct 2026 03:00 UTC. That is about 23:30 IST on 10 Oct to 08:30 IST on 12 Oct. `VERIFY` the real start and end with the organizers.
- **Our problem:** PS-03, *An Evolving AI Research Environment*.

## 2. The problem in one paragraph

Build a research environment run by a **dynamic team of AI agents** that supports the whole ML research lifecycle. Given a paper, question, algorithm, dataset, codebase or idea (**any one of them, or any mix**), it sets up the environment, gets the data, implements or patches the code, runs experiments on modest compute (laptop CPU, free Colab or Kaggle), debugs failures, investigates "what if?" variations, compares against the paper, and explains differences. A **meta-controller** decides which capabilities each task needs and **spawns, refines, merges or retires agents** using a **reward loop** (research outcome, compute cost, researcher feedback). What it learns is retained and reused. The researcher can inspect, approve, reject and redirect everything, including from a phone. The **interface** (what agents are doing, why, how well, how the team is evolving) is a major part of the challenge, and it must not collapse into a notebook or chat box.

## 3. What judges will look for (minimum deliverable)

1. Runs on modest compute (laptop CPU or free-tier Colab or Kaggle).
2. Takes at least one paper and **reproduces its key result autonomously**.
3. Runs at least one meaningful **"what if?" extension**.
4. **Explains where and why** our results differ from the paper.
5. Shows a dashboard of the **evolving agent team**.

Plus: any of paper, question, codebase or dataset as the starting point; meta-controller with spawn/adapt, reward loop, memory that makes future runs better, researcher control (including mobile), execution across environments.

## 4. Our solution in one picture

```
 Researcher (browser / phone)
        │
        ▼
 ┌──────────────── Control plane (web app + backend) ────────────────┐
 │  Dashboard  ·  Meta-Controller + agents (LLM loops)  ·  Memory    │
 │  Job queue  ·  Approvals  ·  Ledger  ·  Events (SSE)  ·  DB       │
 └───────▲───────────────────────────────────────────▲───────────────┘
         │ workers PULL jobs, push logs/results      │ webhooks
 ┌───────┴────────┐                           ┌──────┴──────┐
 │ Worker (laptop,│                           │ n8n: phone  │
 │ later Colab)   │                           │ alerts and  │
 │ runs the code  │                           │ approvals   │
 └────────────────┘                           └─────────────┘
```

Key idea: **agents think in the backend (LLM API calls), workers do in the field (run commands).** The backend never connects to the laptop; the laptop polls outward, so it works behind any router.

## 5. Demo (locked)

The demo is **one combined-input run** (D-035): the KAN paper, the official `pykan` repository, one small real tabular dataset (choice pending, Q-19), and the question *"Do KANs beat parameter-matched MLPs on real tabular data?"* A short second run on another tabular dataset shows memory reuse. The walkthrough is in WORKFLOW.md.

### Demo paper

**Liu et al., "KAN: Kolmogorov-Arnold Networks" (2024)**, with the official `pykan` library.

- **Claim to reproduce:** on small smooth scientific functions, KANs reach lower test error than MLPs at similar parameter counts and scale better with parameters.
- **Tasks:** `x*y`, `exp(sin(pi*x) + y^2)`, a 4-variable composite (`VERIFY` exact forms against the paper), plus one small real tabular dataset as an extension.
- **What-ifs:** noise level, training-set size, KAN grid size, non-smooth targets, a stronger/tuned MLP (fairness check), the tabular dataset.
- **Honest expectation:** later work (as far as we recall, "KAN or MLP: A Fairer Comparison", `VERIFY`) found MLPs match or beat KANs under matched parameters and FLOPs on many tasks. A partial reproduction with a well-explained difference is a **good** outcome, not a failure.

## 6. Key design decisions (summary; full list in logs/DECISIONS.md)

| Decision | Choice |
|---|---|
| App shape | Web app (control plane) plus pull-based workers |
| First worker | Local laptop, started by one terminal command; Colab later |
| Agents | Rows in a DB (prompt, tools, version) executed by one generic loop in the backend |
| Evolution | Text-level only: prompts, tools, routing, memory. **No model training.** |
| LLM | Provider-agnostic wrapper, free tier first (`VERIFY` limits) |
| Memory | SQLite with FTS5, optional small embeddings, entries labelled `seeded` vs `learned` |
| Safety | Workspace jail, command policy, approvals, keys only on the backend |
| Scope | Mode A (patch official code) fully; Mode C (clean-room) for the core KAN layer only, as a stretch |
| Entry paths | Paper, question, codebase and dataset, all at full depth; built in that order: paper, codebase, dataset, question (D-028) |
| Question path | Candidate papers for the researcher to pick, plus a mandatory exploratory branch (D-030) |
| Combined inputs | Dynamic activation: facts detected, rules pick capabilities, Meta-Controller adapts (D-031) |
| Planning model | Hybrid: plan up front, execute in code, re-plan only on triggers (D-032) |
| Spawning | Capability tags plus a five-step ladder (reuse, restore, template, specialise, spawn); domain agents dormant, out of v1 (D-033) |
| Datasets | URL, browser upload or worker path; no size cap for now (D-034) |

## 7. Vocabulary

| Term | Meaning |
|---|---|
| **Project** | One research topic's workspace (DB rows plus a folder on the worker) |
| **Run** | One end-to-end attempt on a goal inside a project |
| **Agent** | A stored prompt plus tool list plus model, executed by the generic agent loop |
| **Agent version** | An immutable snapshot of an agent's prompt/tools; refine = new version |
| **Core / seed / spawned** | Core: fixed. Seed: shipped at start, evolvable. Spawned: created at runtime by the Meta-Controller |
| **Task** | One agent's unit of work within a run (`agent_tasks` row) |
| **Job** | A command or script a worker executes (`jobs` row) |
| **Worker** | Process on a machine with compute that pulls and runs jobs |
| **Branch** | One hypothesis in the exploration tree |
| **Experiment** | One concrete execution (config, seed) belonging to a branch |
| **Ledger** | Append-only list of every deviation from the paper or official code, tagged by category |
| **Mode A / B / C** | A: minimal patches to official code. B: port or re-implement the core. C: clean-room version alongside official code (dual-track) |
| **Approval** | A human gate (plan, expensive run, risky command, agent evolution) |
| **Memory entry** | A stored lesson (error to fix, config to outcome, audit, gotcha, dataset profile) |
| **Entry type** | Which kind of input started the run: `paper`, `question`, `repo`, `dataset`; a run can have several |
| **Research Brief** | The normalised record built at intake: inputs, detected facts, reference targets (`runs.brief_json`) |
| **Fact** | Something intake detects about the inputs, e.g. "repo links paper", "dataset not in paper" |
| **Reference target** | What results are compared against: paper claim, repo-reported numbers, published baselines, or internal baselines |
| **Activation** | The list of agents switched on for a run, each with a reason (`runs.activation_json`) |
| **Fragment** | The sub-graph of tasks one entry type contributes to the plan |
| **Signals** | Facts an agent reports in its output (`signals[]`) that can trigger re-planning |
| **Capability tag** | A label on agents and tasks (`repo:audit`, `lib:pykan`) used to match work to agents and detect gaps |
| **Template** | A dormant agent spec (`kind: template`) that can be instantiated when its tags match a gap |
| **Probation** | The first 2 tasks of a new or refined agent, compared against the agent it replaces |
| **Exploratory mode** | Question-path branch that turns the question into testable hypotheses and runs them without a paper |

## 8. Sponsors and how we use them

| Sponsor | What we know | Our use |
|---|---|---|
| **UseShipReady** | Scans a deployed app for security, reliability and launch blockers and gives a readiness report. The event page says it provides production-readiness scoring for this hackathon. | Deploy early, scan early and often, fix findings. Treat the score as part of judging. |
| **Voroa** | Deploys from GitHub to a live URL, hosted in Mumbai. Web services, background workers, cron jobs, managed Postgres and Redis-compatible key-value; WebSockets supported; free tier with up to 15 services, 5 GB bandwidth and 500 build minutes a month. `VERIFY` instance sizes and whether disk is persistent. | Host the backend and dashboard; Postgres for state. Not for training. |
| **n8n** | Workflow automation (webhooks, triggers, app integrations). | Phone alerts and approvals, paper discovery, report sync. **Not** the core agent logic. |

## 9. Assumptions to confirm

- Team: **3 developers** (one frontend, two backend-side). Roles A, B, C are in COORDINATION.md; names still to be filled in `logs/DEVLOG.md`
- Free-tier LLM provider and rate limits
- Voroa persistent storage and environment-variable support
- Whether organizers provide LLM credits or compute
- Exact `pykan` version and the paper's exact function definitions
- Demo tabular datasets (Q-19) and the capability tag vocabulary (Q-22)
- Where large uploads are stored with no size cap (Q-18)
