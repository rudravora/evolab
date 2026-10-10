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

After changing routes, regenerate the contract file with `python scripts/export_openapi.py` (a test fails if `shared/openapi.yaml` is stale). After changing `app/models.py`, add a migration with `python -m alembic revision --autogenerate -m "<what>"`.

### Worker
TODO: setup and run instructions for `worker/`.

### Frontend
TODO: setup and run instructions for `frontend/` (React app).
