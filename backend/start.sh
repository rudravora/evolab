#!/bin/sh
# Production start (Voroa or any container host): migrate, seed agents, serve.
# Environment comes from the host's settings (see .env.example); nothing secret lives here.
set -e
cd "$(dirname "$0")"
python -m alembic upgrade head
python -m app.seed
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
