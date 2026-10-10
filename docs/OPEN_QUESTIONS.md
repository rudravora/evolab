# OPEN QUESTIONS

Unresolved items. Each has an owner (role A, B or C, see COORDINATION.md) and a needed-by gate. When answered, add a row to DECISIONS.md and move the item to "Resolved" below.

## Open

| ID | Question | Why it matters | Owner | Needed by | Notes |
|---|---|---|---|---|---|
| Q-01 | Names of the three devs and which person takes which role (A, B, C)? | Ownership and branch names | Team | Kickoff | Team size resolved (3). Names and role assignment still open |
| Q-02 | Which free-tier LLM provider and models? Actual rate limits? | Decides concurrency, agent count, Debugger quality | A | M0 | Verify limits; plan a fallback provider and a local Ollama option |
| Q-03 | Do organizers or sponsors give LLM credits or compute? | Budget and model quality | A | Kickoff | Ask on the WhatsApp group or at registration |
| Q-04 | Voroa: free-tier limits, persistent storage, env vars, supported stacks, build config | Decides SQLite vs Postgres and deploy approach | A | M0 | Only the dashboard login page was visible; docs not read |
| Q-05 | UseShipReady: exact checks scored, when scoring happens, how to run scans | Hardening priorities | A | M0 | Event page says it provides production-readiness scoring |
| Q-06 | Exact start and end time of the offline round; Wi-Fi, power, allowed devices | Timeline, sleep plan, fallback plan | C | Kickoff | Event page lists 10 Oct 18:00 UTC to 12 Oct 03:00 UTC; text says 24 hours |
| Q-07 | Exact function definitions and settings used in the KAN paper for the three tasks; `pykan` version to pin | Reproduction target | B | M0 | Written from memory in CONTEXT.md; `VERIFY` |
| Q-08 | Is the "KAN or MLP: A Fairer Comparison" finding as we remember? | Sets honest expectations and the fairness what-if | B | M2 | Read the paper before writing the report |
| Q-09 | Which OS do the three team laptops run? | Resource limits and process-group kill differ on Windows | B | M0 | Affects worker implementation |
| Q-11 | Auto-approve mode for the demo? | Smooth demo vs showing the approval flow | Team | M4 | Suggest: manual approvals on stage, with the phone approval moment if n8n survives the cut ladder |
| Q-14 | Submission requirements: PPT or deck for Unstop, repo link, demo video? | Deliverables | C | Before round | Not yet planned |
| Q-15 | Repo name, license, and public vs private | Voroa deploys from GitHub | A | Kickoff | |
| Q-16 | Final product name (EvoLab is a placeholder) | Branding in UI and deck | Team | Before M5 | |
| Q-17 | Who presents the demo, and who rehearses fallback replays? | Demo reliability | C | M4 | |
| Q-18 | With no upload size cap (D-034), where do large browser uploads live? Voroa disk may be ephemeral and the free tier includes 5 GB bandwidth | Uploads could fail or exhaust bandwidth | A | M2 | Suggest: large files by URL or worker path; browser uploads relayed to the worker, then deleted from the backend |
| Q-19 | Which small tabular dataset for the combined demo (licence, size, a known KAN or MLP baseline)? Plus a second one for the memory-reuse run | Demo content | B | M2 | Must be CPU-friendly and public |
| Q-20 | Ship the 22 domain template stubs in v1 (about an hour), or leave the template library empty? | Ladder step 3 visibility vs scope | Team | M4 | Empty library keeps the tabular gap a genuine fresh spawn |
| Q-21 | Scope checkpoint: if the paper path is not end to end by M2, which later path is reduced first? | Four full-depth paths on a 3-person team | Team | M2 | Default order of reduction: question, then dataset (D-037) |
| Q-22 | Capability tag vocabulary: the fixed list of tags agents and tasks may use | Matching, gap detection and spawning depend on it | A | M0 | Start from the examples in WORKFLOW.md |
| Q-23 | Gateway rate limits | Concurrency cap | A | M0 | **Tested 2026-10-10:** all three models return 200, but the gateway drops the `tools` field (prompt tokens 13–15 with a tool attached; no `tool_calls`), so the agent loop uses a JSON-in-text tool protocol. No rate-limit headers are returned; limits must be asked of the organizers. GPT models spend most of `max_completion_tokens` on reasoning (64 of 74 tokens for a one-word answer), so caps must leave room for it. Also known: one gateway, `Authorization: Bearer <TEAM_API_KEY>`, OpenAI Chat Completions JSON, `stream: false`, text only, **48 KB max request**; IDs `gpt-5.6-luna`, `deepseek-v4-pro`, `gpt-5-mini`; output cap `max_completion_tokens` (GPT) / `max_tokens` (DeepSeek) |
| Q-24 | Supermemory: SDK version to pin, plan limits, and whether paper text and transcripts may be sent there | Librarian implementation and data policy | A | M0 | SDK docs show two API shapes (`container_tags`/`search.documents` vs `container_tag`/`search.memories`); `VERIFY` against the pinned version |
| Q-25 | LangSmith: plan, retention, and what is scrubbed from traces | Untrusted inputs and secrets leave the backend | A | M0 | `VERIFY` env var names (`LANGSMITH_TRACING` vs older `LANGCHAIN_TRACING_V2`) for the pinned SDK |
| Q-26 | Council cost: 3 extra LLM calls per agent task. Score every task, or sample when rate-limited? | Rate limits may bind before M3 | A | M2 | Default: every task, async, `FEATURE_COUNCIL` to turn off |

## Resolved

| ID | Question | Resolution | Date |
|---|---|---|---|
| Q-R1 | Which paper? | KAN vs MLP (D-001) | 2026-10-10 |
| Q-R2 | Laptop or cloud compute first? | Local laptop worker first (D-013) | 2026-10-10 |
| Q-R3 | Must the user supply a paper? | Paper path is P0; question-only entry is P1 (D-018, superseded by D-028) | 2026-10-10 |
| Q-R4 | Team size? | 3 developers, one frontend (D-023) | 2026-10-10 |
| Q-R5 | Second small paper to prove memory transfer? (was Q-12) | Replaced by a second short run on another tabular dataset (D-035) | 2026-10-10 |
| Q-R6 | Where do uploaded dataset files live? (was Q-13) | Datasets by URL, upload or worker path, no cap for now (D-034); storage detail continues as Q-18 | 2026-10-10 |
| Q-R7 | Which entry paths, at what depth? | All four at full depth, paper first (D-028) | 2026-10-10 |
| Q-R8 | How are agents chosen for combined inputs, and who decides the next agent? | Dynamic activation (D-031) and hybrid planning (D-032) | 2026-10-10 |
| Q-R9 | Embeddings for memory? (was Q-10) | Retrieval moves to Supermemory (D-038); no local embeddings | 2026-10-10 |
| Q-R10 | Which LLM models? (was part of Q-02) | GPT-5.6 Luna, DeepSeek V4 Pro, GPT-5 Mini in three tiers (D-041); IDs and limits continue as Q-23 | 2026-10-10 |
