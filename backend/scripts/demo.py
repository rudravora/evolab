"""Guided live demo of the EvoLab backend. Narrates each step and waits for Enter between them.

Before running: the backend is running (py -m uvicorn app.main:app --port 8000, inside backend/).
Run from the repo root:   py backend/scripts/demo.py
Options: --url http://localhost:8000   --no-pause (no Enter prompts)   --minutes 10 (how long to watch)
The password is asked for (or read from EVOLAB_PASSWORD). Standard library only.
"""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = "/api/v1"
TIERS = {"strong": "GPT-5.6 Luna", "code": "DeepSeek V4 Pro", "fast": "GPT-5 Mini"}

C = {"h": "\033[1;36m", "ok": "\033[32m", "dim": "\033[2m", "warn": "\033[33m", "err": "\033[31m", "end": "\033[0m"}
if os.name == "nt":
    os.system("")          # enable ANSI colours in Windows terminals


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body=None, params: dict | None = None):
        url = self.base + API + path
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with self.op.open(req, timeout=120) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read())["error"]
                raise SystemExit(f"{C['err']}{method} {path} failed: {err['code']}: {err['message']}{C['end']}")
            except (ValueError, KeyError):
                raise SystemExit(f"{C['err']}{method} {path} failed: HTTP {e.code}{C['end']}")
        except urllib.error.URLError:
            raise SystemExit(f"{C['err']}Cannot reach {self.base}. Is the backend running?{C['end']}")
        except TimeoutError:
            raise SystemExit(f"{C['err']}{method} {path} timed out: the backend is busy. Re-run with "
                             f"--run <run_id> to continue where you left off.{C['end']}")


def banner(n: int, title: str, say: str) -> None:
    print(f"\n{C['h']}=== Step {n}: {title} ==={C['end']}")
    print(C["dim"] + "\n".join("  " + line for line in textwrap.wrap("Say: " + say, 100)) + C["end"])


def pause(enabled: bool) -> None:
    if enabled:
        input(f"{C['dim']}  [Press Enter to continue]{C['end']}")


def wait_for(fn, what: str, timeout_s: float, every: float = 3.0):
    start, dots = time.time(), 0
    while time.time() - start < timeout_s:
        value = fn()
        if value:
            print()
            return value
        print(f"\r  waiting for {what}{'.' * (dots % 4):<4}", end="", flush=True)
        dots += 1
        time.sleep(every)
    print()
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--no-pause", action="store_true")
    ap.add_argument("--minutes", type=float, default=10.0, help="how long step 6 watches the run")
    ap.add_argument("--workspace", default=str(REPO / "workspace"))
    ap.add_argument("--run", help="continue an existing run instead of starting a new one")
    ap.add_argument("--budget", type=int, default=90,
                    help="minutes of budget for a new run (smaller = fewer seeds, shorter experiments, earlier report)")
    args = ap.parse_args()
    paused = not args.no_pause
    c = Client(args.url)

    # --- 1. sign in and meet the team ---
    banner(1, "Meet the team", "EvoLab has twelve AI agents: nine specialists plus a council of three judges, each judge on a "
           "different AI model. Every agent is data (instructions, tools, model), so the system can rewrite or create agents.")
    health = c.call("GET", "/health")
    print(f"  backend {health['status']} (version {health['version']})")
    password = os.environ.get("EVOLAB_PASSWORD") or getpass.getpass("  Owner password: ")
    c.call("POST", "/auth/login", {"password": password})
    print(f"  {C['ok']}signed in{C['end']}\n")
    for a in c.call("GET", "/agents"):
        v = a["current_version"] or {}
        print(f"  {a['name']:<34} {a['kind']:<5} {TIERS.get(v.get('model'), '?'):<16} {', '.join(v.get('capability_tags', []))[:40]}")
    pause(paused)

    # --- 2. pair the laptop worker ---
    banner(2, "Connect the laptop", "The laptop worker only reaches out to the server, so it works behind any Wi-Fi. It runs "
           "jobs inside a locked folder and checks every command against safety rules.")
    worker = None
    online = [w for w in c.call("GET", "/workers") if w["status"] == "online" and not w["revoked"]]
    if online:
        print(f"  worker already online: {online[0]['name']}")
    else:
        code = c.call("POST", "/workers/pairing")["pairing_code"]
        Path(args.workspace).mkdir(parents=True, exist_ok=True)
        log = open(Path(args.workspace) / "worker.log", "a", encoding="utf-8")
        env = {**os.environ, "BACKEND_URL": args.url, "PAIRING_CODE": code, "WORKSPACE_ROOT": args.workspace,
               "WORKER_NAME": "demo-laptop"}
        worker = subprocess.Popen([sys.executable, str(REPO / "worker" / "worker.py")], env=env, stdout=log,
                                  stderr=subprocess.STDOUT, cwd=str(REPO))
        w = wait_for(lambda: [w for w in c.call("GET", "/workers") if w["status"] == "online" and not w["revoked"]],
                     "the worker to register", 60, 2)
        if not w:
            raise SystemExit(f"{C['err']}Worker did not come online; see {args.workspace}\\worker.log{C['end']}")
        print(f"  {C['ok']}worker online:{C['end']} {w[-1]['name']} ({w[-1]['platform']}, "
              f"{(w[-1]['capabilities'] or {}).get('cpu_cores')} cores)")
    pause(paused)

    # --- 3. start a run and show the Research Brief ---
    banner(3, "Give it a paper", "We give it the KAN paper, its official code and a research question. It fetches the real "
           "paper from arXiv and the README from GitHub, and works out how the inputs relate.")
    if args.run:
        run_id = args.run
        print(f"  continuing run {run_id} ({c.call('GET', f'/runs/{run_id}')['status']})")
    else:
        created = c.call("POST", "/projects", {"example": True, "budget": {"max_wall_min": args.budget,
                                                                            "max_tokens": 60_000 * args.budget // 4}})
        run_id = created["run_id"]
        print(f"  run started: {run_id}  (inputs: {', '.join(created['entry_types'])}; budget {args.budget} min)")
    brief = wait_for(lambda: (b := c.call("GET", f"/runs/{run_id}/brief"))["ready"] and b, "the Research Brief", 180)
    if brief:
        print(f"  domain: {brief['domain']}")
        for f in brief["facts"]:
            print(f"  fact   {f['fact']:<26} {f['evidence'][:70]}")
        for t in brief["reference_targets"]:
            print(f"  target #{t['rank']} {t['type']}")
        print("  agents chosen:")
        for a in brief["activation"]:
            mark = C["ok"] + "on " if a["active"] else C["dim"] + "off"
            print(f"    {mark}{C['end']} {a['agent_id'].removeprefix('agt_'):<22} {a['reason'][:70]}")
    pause(paused)

    # --- 4. the plan waits for approval ---
    banner(4, "Nothing runs without approval", "The Meta-Controller, the AI manager, drafted this plan. I approve it, and "
           "from then on plain code runs the plan: no AI decides who goes next.")
    def plan_ready():
        pending = [a for a in c.call("GET", "/approvals", params={"run_id": run_id, "status": "pending"}) if a["type"] == "plan"]
        if pending:
            return pending
        plans = [t for t in c.call("GET", f"/runs/{run_id}/tasks") if t["task_type"] == "plan"]
        if plans and plans[-1]["status"] == "failed":
            raise SystemExit(f"\n{C['err']}Planning failed: {plans[-1]['error']}{C['end']}\n"
                             f"  Check the internet connection, then start a fresh run: py backend/scripts/demo.py")
        if c.call("GET", f"/runs/{run_id}")["status"] in ("running", "done"):
            return [None]                       # already approved earlier
        return None

    plan = wait_for(plan_ready, "the plan (the AI manager is thinking; retries automatically if the AI service is busy)",
                    1200, 5)
    if plan == [None]:
        plan = []
    if not plan and c.call("GET", f"/runs/{run_id}")["status"] == "running":
        print("  plan already approved; skipping to the live view")
    elif not plan:
        raise SystemExit(f"{C['warn']}No plan yet (the AI service may be rate limiting). Re-run later or check "
                         f"GET /runs/{run_id}/tasks{C['end']}")
    if plan:
        p = plan[0]["payload"]
        print(f"  {p['summary']}")
        for t in p["plan"]["tasks"]:
            who = (t["agent_id"] or "Executor (code)").removeprefix("agt_")
            deps = ", ".join(t["depends_on"]) or "-"
            print(f"    {t['task_id']:<18} by {who:<22} after {deps}")
        pause(paused)
        c.call("POST", f"/approvals/{plan[0]['id']}/decide", {"decision": "approve"})
        print(f"  {C['ok']}plan approved: the run is now executing{C['end']}")

    # --- 5 and 6. watch the agents work ---
    banner(5, "Watch the agents work", "Each agent shows its status. Every step an agent takes is saved, so we can always see "
           "why it did something. Jobs run on this laptop.")
    seen, shown_msgs, deadline = {}, set(), time.time() + args.minutes * 60
    try:
        while time.time() < deadline:
            run = c.call("GET", f"/runs/{run_id}")
            for t in c.call("GET", f"/runs/{run_id}/tasks"):
                key = (t["task_type"], t["status"])
                if seen.get(t["id"]) != key:
                    seen[t["id"]] = key
                    colour = C["ok"] if t["status"] == "done" else C["err"] if t["status"] == "failed" else ""
                    err = f"  ({t['error'][:60]})" if t["error"] else ""
                    print(f"  {time.strftime('%H:%M:%S')}  {t['task_type']:<18} {colour}{t['status']}{C['end']}{err}")
                if t["agent_id"] and t["status"] in ("running", "waiting_for_job", "done"):
                    for m in c.call("GET", f"/tasks/{t['id']}/messages")[-4:]:
                        mk = (t["id"], m["seq"], m["role"])
                        if m["role"] == "assistant" and mk not in shown_msgs:
                            shown_msgs.add(mk)
                            print(f"{C['dim']}      {t['task_type']} -> {(m['content'] or '')[:110]}{C['end']}")
            for a in c.call("GET", "/approvals", params={"run_id": run_id, "status": "pending"}):
                print(f"\n  {C['warn']}Approval needed ({a['type']}): {a['payload'].get('summary', '')[:100]}{C['end']}")
                answer = input("  Approve? [y/n] ").strip().lower() if paused else "y"
                c.call("POST", f"/approvals/{a['id']}/decide", {"decision": "approve" if answer == "y" else "reject"})
            if run["status"] in ("done", "failed", "cancelled"):
                print(f"\n  run {run['status']}")
                break
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n  stopped watching (the run keeps going in the backend)")

    run = c.call("GET", f"/runs/{run_id}")
    print(f"\n{C['h']}Summary{C['end']}: run {run_id} is {run['status']}; {run['usage']['jobs']} job(s) on the laptop, "
          f"{run['usage']['tokens']} AI tokens, {run['usage']['wall_min']} min")
    print(f"  Details: {args.url}/docs  ->  GET /runs/{run_id}/tasks , /runs/{run_id}/report")
    if worker is not None:
        keep = input("  Keep the worker running so the run can continue? [Y/n] ").strip().lower() if paused else "y"
        if keep == "n":
            worker.terminate()
            print("  worker stopped")
        else:
            print(f"  worker keeps running (pid {worker.pid}); close this window or press Ctrl+C to stop it")
            try:
                worker.wait()
            except KeyboardInterrupt:
                worker.terminate()


if __name__ == "__main__":
    main()
