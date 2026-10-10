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
| Q-10 | Embeddings for memory: use or skip in v1? | Time vs value | A | M2 | Keyword search plus exact signatures may be enough; lean to skip with only 3 devs |
| Q-11 | Auto-approve mode for the demo? | Smooth demo vs showing the approval flow | Team | M4 | Suggest: manual approvals on stage, with the phone approval moment if n8n survives the cut ladder |
| Q-12 | Second small paper to prove memory transfer? | Strengthens self-improvement story | Team | M3 | P2 and first on the cut ladder |
| Q-13 | Where do uploaded dataset files live in deployment (Voroa disk may be ephemeral)? | Data intake | A | M2 | May store on the worker side only |
| Q-14 | Submission requirements: PPT or deck for Unstop, repo link, demo video? | Deliverables | C | Before round | Not yet planned |
| Q-15 | Repo name, license, and public vs private | Voroa deploys from GitHub | A | Kickoff | |
| Q-16 | Final product name (EvoLab is a placeholder) | Branding in UI and deck | Team | Before M5 | |
| Q-17 | Who presents the demo, and who rehearses fallback replays? | Demo reliability | C | M4 | |

## Resolved

| ID | Question | Resolution | Date |
|---|---|---|---|
| Q-R1 | Which paper? | KAN vs MLP (D-001) | 2026-10-10 |
| Q-R2 | Laptop or cloud compute first? | Local laptop worker first (D-013) | 2026-10-10 |
| Q-R3 | Must the user supply a paper? | Paper path is P0; question-only entry is P1 (D-018) | 2026-10-10 |
| Q-R4 | Team size? | 3 developers, one frontend (D-023) | 2026-10-10 |
