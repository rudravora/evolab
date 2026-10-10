"""Run the real backend in SIMULATED mode: scripted AI replies, fake web and memory, and a
built-in simulated laptop worker. The whole pipeline (Brief, plan, agents, experiments, a
Debugger fix, a fresh-spawn evolution, council scores, report) finishes in a few minutes.

Everything you see is produced by the real orchestrator, agent loop, Executor, council and
evolution code; only the AI replies and the worker's job results are scripted. /health
reports mode "simulated" and the dashboard shows a SIMULATED banner (D-027).

Run from backend/ (stop the live backend first, or use another --port):
    py scripts/sim_server.py                 # http://localhost:8000, fresh sim.db each start
    py scripts/sim_server.py --delay 2       # slower, easier to follow on stage
Sign in with your normal owner password (read from .env).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))          # the scripted AI and fakes used by the test suite

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import seed_agents  # noqa: E402
from app.services import build_services  # noqa: E402
from fakes import FakeSupermemory, FakeWeb, ScriptedLLM  # noqa: E402

PYKAN_ERR = "AttributeError: 'KAN' object has no attribute 'train' (pykan 0.2.8)"


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


class SlowScripted:
    """Scripted AI with a per-call delay, so the dashboard shows agents working step by step."""

    def __init__(self, delay_s: float):
        self.llm, self.delay_s = ScriptedLLM(), delay_s

    def __call__(self, body, headers, timeout):
        time.sleep(self.delay_s)
        return self.llm(body, headers, timeout)


def sim_worker(base: str, db_session, stop: threading.Event, fail_first: int = 1) -> None:
    """A laptop worker that answers jobs the way B's worker would, with plausible metrics."""
    from app.ids import new_id
    from app.models import WorkerPairing

    code = "SIMU-LATE"
    with db_session() as db:
        exp = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        db.add(WorkerPairing(id=new_id("pair"), owner_id="usr_owner", code_hash=hashlib.sha256(code.encode()).hexdigest(),
                             expires_at=exp))
        db.commit()
    c = httpx.Client(base_url=base + "/api/v1", timeout=30)
    while not stop.is_set():
        try:
            r = c.post("/worker/register", json={"pairing_code": code, "name": "simulated-laptop", "platform": "simulated",
                                                 "capabilities": {"cpu_cores": 8, "ram_gb": 16, "gpu": False}})
            break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        return
    h = {"Authorization": f"Bearer {r.json()['worker_token']}"}
    last_beat = 0.0
    while not stop.is_set():
        try:
            if time.time() - last_beat > 8:
                c.post("/worker/heartbeat", json={"status": "idle", "cpu_pct": 23.0, "ram_pct": 41.0}, headers=h)
                last_beat = time.time()
            r = c.get("/worker/jobs/next", headers=h)
            if r.status_code == 204:
                time.sleep(0.5)
                continue
            job = r.json()
            jid, att, p = job["job_id"], job["attempt"], job["payload"]
            c.post(f"/worker/jobs/{jid}/start", json={"attempt": att}, headers=h)
            lines = _log_lines(job)
            for i, line in enumerate(lines):
                c.post(f"/worker/jobs/{jid}/logs", json={"attempt": att, "chunks": [{"seq": i, "stream": "stdout", "text": line}]},
                       headers=h)
                time.sleep(0.25)
            body = {"attempt": att, "status": "done", "exit_code": 0, "stdout_tail": "\n".join(lines[-5:]),
                    "stderr_tail": "", "metrics": {}, "files": []}
            if p.get("results_path"):
                if fail_first > 0:
                    fail_first -= 1
                    body.update(status="failed", exit_code=1, stderr_tail=f"Traceback (most recent call last):\n  ...\n{PYKAN_ERR}")
                else:
                    argv = " ".join(p["argv"])
                    seed = int(argv.split("--seed ")[1].split()[0]) if "--seed " in argv else 0
                    bump = 0.012 if "noise" in argv else (-0.008 if "grid" in argv else 0.0)
                    body["metrics"] = {"metrics": {"test_rmse": round(0.105 + bump + seed * 0.0015, 4)}, "param_count": 520,
                                       "train_seconds": 2.4, "status": "done"}
            c.post(f"/worker/jobs/{jid}/result", json=body, headers=h)
        except httpx.HTTPError:
            time.sleep(1)


def _log_lines(job: dict) -> list[str]:
    p = job["payload"]
    if p.get("results_path"):
        return [f"$ {' '.join(p.get('argv', []))}", "loading data", "epoch 10  loss 0.0412", "epoch 20  loss 0.0213",
                "epoch 40  loss 0.0118", f"wrote {p['results_path']}"]
    if job["type"] == "write_file":
        return [f"wrote {p.get('path')}"]
    return [f"{job['type']} ok", json.dumps(p)[:120]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds per scripted AI reply")
    ap.add_argument("--db", default=str(BACKEND / "sim.db"))
    args = ap.parse_args()

    for f in Path(args.db).parent.glob(Path(args.db).name + "*"):
        f.unlink()                                   # every start is a clean simulation
    base_env = Settings(app_secret="x" * 32)         # reads APP_SECRET and OWNER_PASSWORD_HASH from .env
    settings = Settings(_env_file=None, app_secret=base_env.app_secret, owner_password_hash=base_env.owner_password_hash,
                        database_url=f"sqlite:///{Path(args.db).as_posix()}", public_base_url=f"http://localhost:{args.port}",
                        allowed_origins=base_env.allowed_origins, artifacts_dir=str(BACKEND / "sim_artifacts"),
                        simulation=True, pipeline="agents", feature_council=True, langsmith_tracing=False,
                        llm_base_url="http://simulated", llm_api_key="simulated", llm_model_strong="gpt-5.6-luna",
                        llm_model_code="deepseek-v4-pro", llm_model_fast="gpt-5-mini")
    if not settings.owner_password_hash:
        sys.exit("Set OWNER_PASSWORD_HASH in .env first (py scripts/hash_password.py).")
    migrate(settings.database_url)
    services = build_services(settings, None, transport=SlowScripted(args.delay), web=FakeWeb(), supermemory=FakeSupermemory())
    app = create_app(settings, services)
    with app.state.db.sessionmaker() as db:
        seed_agents(db)

    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)   # the simulated worker polls often; keep the console readable
    stop = threading.Event()
    threading.Thread(target=sim_worker, args=(f"http://127.0.0.1:{args.port}", app.state.db.sessionmaker, stop),
                     daemon=True).start()
    print(f"\n  EvoLab SIMULATED backend on http://localhost:{args.port}  (scripted AI, simulated laptop worker)\n")
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
