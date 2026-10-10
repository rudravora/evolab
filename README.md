# EvoLab

EvoLab is our hackathon project (placeholder name). See [docs/README.md](docs/README.md) for full project context, architecture, and API docs.

## How to run

### Backend
Python 3.12 or newer. On Windows, use `py` where these steps say `python`. All commands run inside `backend/`.

1. Install: `python -m pip install -r requirements-dev.txt`
2. Configure: copy `.env.example` to `.env` at the repo root (never commit it), then set:
   - `APP_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - `OWNER_PASSWORD_HASH`: `python scripts/hash_password.py` (prints the line to paste)
3. Create the database: `python -m alembic upgrade head`
4. Seed the agents: `python -m app.seed`
5. Run: `python -m uvicorn app.main:app --reload --port 8000`. Health is at `http://localhost:8000/api/v1/health` and API docs at `http://localhost:8000/docs`
6. Test: `python -m pytest tests`

The server runs the whole agent pipeline in-process: a scheduler (orchestrator) and a housekeeping sweeper start with it. A new project goes through background intake, then the Meta-Controller's plan waits in the approvals inbox (`GET /api/v1/approvals`). Nothing executes until a worker is paired and the plan is approved. Agents need `LLM_*` set; memory uses `SUPERMEMORY_API_KEY` when set (local keyword search otherwise); tracing needs `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`.

Deploy (Voroa or any container host): `docker build -f backend/Dockerfile -t evolab-backend .` from the repo root; the container runs `backend/start.sh` (migrate, seed, serve on `$PORT`). Run one instance.

After changing routes, regenerate the contract file with `python scripts/export_openapi.py` (a test fails if `shared/openapi.yaml` is stale). After changing `app/models.py`, add a migration with `python -m alembic revision --autogenerate -m "<what>"`.

### Worker
TODO: setup and run instructions for `worker/`.

### Frontend (dashboard)
Next.js app in `frontend/`. Node 20 or newer.

1. Install once: `npm --prefix frontend ci`
2. Run: `npm --prefix frontend run dev`, then open http://localhost:3000 and sign in with the owner password.

The browser only talks to the Next.js server; it proxies `/api/v1/*` to the backend (default `http://127.0.0.1:8000`, override with `EVOLAB_BACKEND_URL`). Pages: `/dashboard` (pair a worker, start a run, list runs), `/runs/<id>` (approvals, pipeline, experiment tree, Brief, report, ledger, team, live events, chat, task transcripts with council scores), `/agents`, `/memory`.

### Whole app in simulated mode (demo in about 3 minutes)
Same backend code with scripted AI replies and a built-in simulated laptop worker; the UI shows a SIMULATED banner.

1. Stop the live backend (Ctrl+C), then inside `backend/`: `py scripts/sim_server.py` (fresh `sim.db` each start; `--delay 2` to slow it down)
2. `npm --prefix frontend run dev`, open http://localhost:3000, sign in, click **Try the KAN example**, approve the plan and the evolution proposal.
