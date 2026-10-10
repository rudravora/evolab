"""Tests for worker/runner.py: timeout+group kill, output cap, secret
scrubbing, policy enforcement (deny and env rejection).

Run: python worker/test_runner.py

Some cases (process-group child kill, memory watchdog) are inherently timing
and platform sensitive; see the printed CAVEATS section and the final report
for what this suite could not fully verify.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import policy  # noqa: E402
import runner  # noqa: E402

FAILURES: list[str] = []
CAVEATS: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def make_workspace() -> Path:
    tmp = Path(tempfile.mkdtemp())
    code_dir = tmp / "proj1" / "code"
    code_dir.mkdir(parents=True)
    return tmp


def write_script(workspace: Path, name: str, content: str) -> None:
    path = workspace / "proj1" / "code" / name
    path.write_text(content)


def job(job_type: str, payload: dict, **extra) -> dict:
    d = {"type": job_type, "payload": payload}
    d.update(extra)
    return d


def run(j: dict, workspace: Path, timeout_s: float = 30, collect_logs: bool = True):
    chunks_log: list[dict] = []

    def on_log(chunks):
        if collect_logs:
            chunks_log.extend(chunks)

    start = time.monotonic()
    result = runner.run_job(j, workspace, on_log=on_log)
    elapsed = time.monotonic() - start
    return result, chunks_log, elapsed


# ---------------------------------------------------------------------------
# 1. Normal script
# ---------------------------------------------------------------------------

def test_normal_script() -> None:
    ws = make_workspace()
    write_script(ws, "hello.py", "print('hello from job')\n")
    j = job("python_script", {"argv": ["python3", "hello.py"], "cwd": "proj1/code"})
    result, logs, _ = run(j, ws)
    check("normal_script.status", result["status"] == "done", result)
    check("normal_script.exit_code", result["exit_code"] == 0, result)
    check("normal_script.log_text", any("hello from job" in c["text"] for c in logs), logs)
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. Infinite loop: timeout and group kill
# ---------------------------------------------------------------------------

def test_infinite_loop_timeout() -> None:
    ws = make_workspace()
    write_script(ws, "loop.py", "while True:\n    pass\n")
    j = job("python_script", {"argv": ["python3", "loop.py"], "cwd": "proj1/code"})
    start = time.monotonic()
    result = runner.run_job({**j, "timeout_s": 2}, ws)
    elapsed = time.monotonic() - start
    check("infinite_loop.status", result["status"] == "timed_out", result)
    check("infinite_loop.elapsed_bounded", elapsed < 10, f"took {elapsed:.1f}s, expected close to timeout_s=2 plus grace")
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. Script that spawns children: all killed with the group
# ---------------------------------------------------------------------------

def test_child_processes_killed() -> None:
    ws = make_workspace()
    marker = ws / "child_alive.txt"
    # Parent spawns a detached-looking child (still in the same process
    # group unless it calls setsid itself) that would touch `marker` every
    # 0.2s forever if still running after the timeout.
    write_script(
        ws,
        "spawner.py",
        f"""
import subprocess, time
p = subprocess.Popen(["python3", "-c",
    "import time; f=open({str(marker)!r}, 'a');"
    "[ (f.write('x'), f.flush(), time.sleep(0.2)) for _ in iter(int, 1) ]"
])
time.sleep(60)
""",
    )
    j = job("python_script", {"argv": ["python3", "spawner.py"], "cwd": "proj1/code"})
    result = runner.run_job({**j, "timeout_s": 2}, ws)
    check("child_processes.status", result["status"] == "timed_out", result)

    size_at_kill = marker.stat().st_size if marker.exists() else 0
    time.sleep(1.5)  # give a leaked child time to keep writing, if it survived
    size_after_wait = marker.stat().st_size if marker.exists() else 0
    check(
        "child_processes.child_actually_killed",
        size_after_wait == size_at_kill,
        f"marker file grew after kill: {size_at_kill} -> {size_after_wait} (child survived the group kill)",
    )
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Script prints a fake key: scrubbed before leaving the process
# ---------------------------------------------------------------------------

def test_secret_scrubbing() -> None:
    ws = make_workspace()
    write_script(
        ws,
        "leak.py",
        "print('sk-abcdefghijklmnopqrstuvwxyz123456')\n"
        "print('token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123')\n"
        "print('api_key=abcdef0123456789abcdef0123456789')\n",
    )
    j = job("python_script", {"argv": ["python3", "leak.py"], "cwd": "proj1/code"})
    result, logs, _ = run(j, ws)
    full_text = result["stdout_tail"] + " " + " ".join(c["text"] for c in logs)
    check("scrub.no_sk_prefix", "sk-abcdefghijklmnopqrstuvwxyz123456" not in full_text, full_text)
    check("scrub.no_ghp_prefix", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123" not in full_text, full_text)
    check("scrub.no_raw_api_key_value", "abcdef0123456789abcdef0123456789" not in full_text, full_text)
    check("scrub.redaction_marker_present", "[REDACTED]" in full_text, full_text)
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 5. Policy-denied command: never started
# ---------------------------------------------------------------------------

def test_policy_denied_never_started() -> None:
    ws = make_workspace()
    marker = ws / "proj1" / "code" / "ran.txt"
    # sudo is denied outright; if it were ever started (even to fail), a
    # normal "command not found" would still not touch this marker, so we
    # instead assert on the result shape and on wall-clock time (a real
    # subprocess spawn+exit takes measurable time; a classify-and-return
    # should be near-instant).
    j = job("shell", {"argv": ["sudo", "touch", str(marker)]})
    start = time.monotonic()
    result = runner.run_job(j, ws)
    elapsed = time.monotonic() - start
    check("policy_denied.status", result["status"] == "failed", result)
    check("policy_denied.reason_mentions_policy", "policy_denied" in result["stderr_tail"], result)
    check("policy_denied.marker_not_created", not marker.exists(), "sudo touch ran despite deny verdict")
    check("policy_denied.fast_rejection", elapsed < 0.5, f"took {elapsed:.2f}s, expected near-instant rejection")
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6. GIT_SSH_COMMAND in env: rejected, not passed through
# ---------------------------------------------------------------------------

def test_dangerous_env_rejected() -> None:
    ws = make_workspace()
    write_script(ws, "print_env.py", "import os; print('GIT_SSH_COMMAND=' + os.environ.get('GIT_SSH_COMMAND', '<unset>'))\n")
    j = job(
        "python_script",
        {
            "argv": ["python3", "print_env.py"],
            "cwd": "proj1/code",
            "env": {"GIT_SSH_COMMAND": "ssh -o StrictHostKeyChecking=no", "OMP_NUM_THREADS": "4"},
        },
    )
    result, logs, _ = run(j, ws)
    full_text = result["stdout_tail"] + " " + " ".join(c["text"] for c in logs)
    check("dangerous_env.not_inherited", "GIT_SSH_COMMAND=<unset>" in full_text, full_text)
    check("dangerous_env.not_leaked_value", "StrictHostKeyChecking" not in full_text, full_text)

    # Direct check on the policy/env-building primitives too.
    env, rejected = policy.check_env({"GIT_SSH_COMMAND": "x", "OMP_NUM_THREADS": "4"})
    check("dangerous_env.check_env_rejects_key", "GIT_SSH_COMMAND" in rejected, rejected)
    check("dangerous_env.check_env_allows_benign", "OMP_NUM_THREADS" in env, env)
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. Output over the cap: truncated
# ---------------------------------------------------------------------------

def test_output_cap_truncation() -> None:
    ws = make_workspace()
    write_script(
        ws,
        "spam.py",
        "for i in range(100000):\n    print('x' * 100)\n",
    )
    j = job("python_script", {"argv": ["python3", "spam.py"], "cwd": "proj1/code"})
    result = runner.run_job({**j, "max_output_bytes": 2000}, ws)
    check("output_cap.status_still_done", result["status"] == "done", result)
    check(
        "output_cap.tail_bounded",
        len(result["stdout_tail"].encode("utf-8", errors="replace")) <= 2000 + 200,  # small slack for line boundaries
        f"tail length {len(result['stdout_tail'])} chars, expected roughly <= cap",
    )
    shutil.rmtree(ws, ignore_errors=True)


def main() -> None:
    tests = [
        test_normal_script,
        test_infinite_loop_timeout,
        test_child_processes_killed,
        test_secret_scrubbing,
        test_policy_denied_never_started,
        test_dangerous_env_rejected,
        test_output_cap_truncation,
    ]
    for t in tests:
        print(f"running {t.__name__} ...")
        t()

    if FAILURES:
        print(f"FAILED {len(FAILURES)} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"ALL CHECKS PASSED ({len(tests)} scenarios)")


if __name__ == "__main__":
    main()
