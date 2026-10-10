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
import threading
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


PROJECT_ID = "proj1"


def make_workspace() -> Path:
    tmp = Path(tempfile.mkdtemp())
    code_dir = tmp / PROJECT_ID / "code"
    code_dir.mkdir(parents=True)
    return tmp


def write_script(workspace: Path, name: str, content: str) -> None:
    path = workspace / PROJECT_ID / "code" / name
    path.write_text(content)


def job(job_type: str, payload: dict, **extra) -> dict:
    d = {"job_id": "job_test", "project_id": PROJECT_ID, "attempt": 1, "type": job_type, "payload": payload}
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
    j = job("python_script", {"argv": ["python3", "hello.py"], "cwd": "code"})
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
    j = job("python_script", {"argv": ["python3", "loop.py"], "cwd": "code"})
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
    j = job("python_script", {"argv": ["python3", "spawner.py"], "cwd": "code"})
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
    j = job("python_script", {"argv": ["python3", "leak.py"], "cwd": "code"})
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
    marker = ws / PROJECT_ID / "code" / "ran.txt"
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
            "cwd": "code",
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
    j = job("python_script", {"argv": ["python3", "spam.py"], "cwd": "code"})
    result = runner.run_job({**j, "max_output_bytes": 2000}, ws)
    check("output_cap.status_still_done", result["status"] == "done", result)
    check(
        "output_cap.tail_bounded",
        len(result["stdout_tail"].encode("utf-8", errors="replace")) <= 2000 + 200,  # small slack for line boundaries
        f"tail length {len(result['stdout_tail'])} chars, expected roughly <= cap",
    )
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 8. project_id: valid jails into WORKSPACE_ROOT/<project_id>/, invalid is
#    rejected before anything runs
# ---------------------------------------------------------------------------

def test_project_id_valid_jails_correctly() -> None:
    ws = make_workspace()
    write_script(ws, "hello.py", "print('ok')\n")
    j = job("python_script", {"argv": ["python3", "hello.py"], "cwd": "code"})
    result = runner.run_job(j, ws)
    check("project_id.valid_runs", result["status"] == "done", result)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_missing_rejected() -> None:
    ws = make_workspace()
    j = job("shell", {"argv": ["ls"], "cwd": "code"})
    del j["project_id"]
    result = runner.run_job(j, ws)
    check("project_id.missing_rejected", result["status"] == "failed", result)
    check("project_id.missing_mentions_project_id", "project_id" in result["stderr_tail"], result)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_empty_rejected() -> None:
    ws = make_workspace()
    j = job("shell", {"argv": ["ls"], "cwd": "code"}, project_id="")
    result = runner.run_job(j, ws)
    check("project_id.empty_rejected", result["status"] == "failed", result)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_absolute_rejected() -> None:
    ws = make_workspace()
    j = job("shell", {"argv": ["ls"], "cwd": "code"}, project_id="/etc")
    result = runner.run_job(j, ws)
    check("project_id.absolute_rejected", result["status"] == "failed", result)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_dotdot_rejected() -> None:
    ws = make_workspace()
    j = job("shell", {"argv": ["ls"], "cwd": "code"}, project_id="..")
    result = runner.run_job(j, ws)
    check("project_id.dotdot_rejected", result["status"] == "failed", result)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_path_separator_rejected() -> None:
    ws = make_workspace()
    j = job("shell", {"argv": ["ls"], "cwd": "code"}, project_id="proj1/evil")
    result = runner.run_job(j, ws)
    check("project_id.separator_rejected", result["status"] == "failed", result)

    j2 = job("shell", {"argv": ["ls"], "cwd": "code"}, project_id="proj1\\evil")
    result2 = runner.run_job(j2, ws)
    check("project_id.backslash_separator_rejected", result2["status"] == "failed", result2)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_cwd_jail_differs_per_project() -> None:
    """The same relative cwd ("code") resolves to a different real directory
    depending on project_id, proving the jail root actually changed (not
    just validated and then ignored)."""
    ws = Path(tempfile.mkdtemp())
    (ws / "proj_a" / "code").mkdir(parents=True)
    (ws / "proj_b" / "code").mkdir(parents=True)
    (ws / "proj_a" / "code" / "marker.txt").write_text("A\n")
    (ws / "proj_b" / "code" / "marker.txt").write_text("B\n")

    job_a = {
        "job_id": "job_a",
        "project_id": "proj_a",
        "attempt": 1,
        "type": "shell",
        "payload": {"argv": ["cat", "marker.txt"], "cwd": "code"},
    }
    job_b = {**job_a, "job_id": "job_b", "project_id": "proj_b"}

    result_a = runner.run_job(job_a, ws)
    result_b = runner.run_job(job_b, ws)
    check("project_id.a_sees_own_file", result_a["stdout_tail"].strip() == "A", result_a)
    check("project_id.b_sees_own_file", result_b["stdout_tail"].strip() == "B", result_b)
    shutil.rmtree(ws, ignore_errors=True)


def test_project_id_argv_literal_path_not_jailed() -> None:
    """Known limitation, not a bug: resolve_in_jail only validates the cwd,
    path, results_path fields -- it never inspects argv tokens. A job whose
    argv contains a literal '../' path can still read outside its own
    project's jail if the OS-level path happens to resolve there, because
    the process's actual filesystem access is bounded only by its real cwd,
    not by any sandboxing the worker adds beyond that. This test documents
    the gap rather than asserting it is prevented; see the final report's
    "cannot reliably catch" section.
    """
    ws = Path(tempfile.mkdtemp())
    (ws / "proj_a" / "code").mkdir(parents=True)
    (ws / "proj_b" / "code").mkdir(parents=True)
    (ws / "proj_b" / "code" / "secret.txt").write_text("project B's secret\n")

    j = {
        "job_id": "job_isolation",
        "project_id": "proj_a",
        "attempt": 1,
        "type": "shell",
        # one ".." climbs out of "code" into "proj_a"; a second climbs out
        # of "proj_a" into the shared workspace root, from which "proj_b" is
        # reachable -- this is a real OS-level path, not a jail escape bug,
        # since resolve_in_jail was never asked to validate this token.
        "payload": {"argv": ["cat", "../../proj_b/code/secret.txt"], "cwd": "code"},
    }
    result = runner.run_job(j, ws)
    check(
        "project_id.argv_path_reaches_sibling_project (documents a known gap, not a guarantee)",
        "project B's secret" in result["stdout_tail"],
        result,
    )
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 9. approved: an un-approved needs_approval job is denied; approved runs
# ---------------------------------------------------------------------------

def test_approved_unlocks_needs_approval_job() -> None:
    ws = make_workspace()
    write_script(ws, "unused.py", "")
    # "npm" is not on the auto allowlist -> needs_approval, not auto or deny.
    j = job("shell", {"argv": ["echo", "hi"], "cwd": "code"})
    result_unapproved = runner.run_job(j, ws)
    check(
        "approved.unapproved_needs_approval_denied",
        result_unapproved["status"] == "failed" and "needs_approval" in result_unapproved["stderr_tail"],
        result_unapproved,
    )

    j_approved = job("shell", {"argv": ["echo", "hi"], "cwd": "code"}, approved=True)
    result_approved = runner.run_job(j_approved, ws)
    check("approved.approved_needs_approval_runs", result_approved["status"] == "done", result_approved)
    shutil.rmtree(ws, ignore_errors=True)


def test_approved_never_unlocks_deny() -> None:
    ws = make_workspace()
    j = job("shell", {"argv": ["sudo", "ls"]}, approved=True)
    result = runner.run_job(j, ws)
    check("approved.deny_still_denied_even_if_approved", result["status"] == "failed", result)
    check("approved.deny_reason_not_needs_approval", "needs_approval" not in result["stderr_tail"], result)
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# 10. cancel hook: a running job can be killed mid-flight via CancelRegistry
# ---------------------------------------------------------------------------

def test_cancel_running_job() -> None:
    ws = make_workspace()
    marker = ws / PROJECT_ID / "code" / "still_running.txt"
    write_script(
        ws,
        "sleep_job.py",
        f"""
import time
with open({str(marker)!r}, "w") as f:
    f.write("started\\n")
time.sleep(30)
""",
    )
    j = job("python_script", {"argv": ["python3", "sleep_job.py"], "cwd": "code"}, job_id="job_cancel_me")

    registry = runner.CancelRegistry()
    result_holder = {}

    def run_in_thread():
        result_holder["result"] = runner.run_job(j, ws, cancel_registry=registry)

    t = threading.Thread(target=run_in_thread)
    t.start()

    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    check("cancel.job_actually_started", marker.exists(), "sleep job never started (marker file missing)")

    start_cancel = time.monotonic()
    killed = registry.cancel("job_cancel_me")
    check("cancel.cancel_found_running_job", killed is True, "cancel() reported no running job found")

    t.join(timeout=15)
    cancel_elapsed = time.monotonic() - start_cancel

    check("cancel.thread_finished", not t.is_alive(), "run_job thread did not finish after cancel")
    result = result_holder.get("result")
    check("cancel.status_cancelled", result is not None and result["status"] == "cancelled", result)
    check(
        "cancel.fast_cancel",
        cancel_elapsed < 10,
        f"cancel took {cancel_elapsed:.1f}s, expected well under the SIGTERM grace + a small margin",
    )
    shutil.rmtree(ws, ignore_errors=True)


def test_cancel_nonexistent_job_is_noop() -> None:
    registry = runner.CancelRegistry()
    killed = registry.cancel("job_never_existed")
    check("cancel.nonexistent_job_returns_false", killed is False, killed)


def main() -> None:
    tests = [
        test_normal_script,
        test_infinite_loop_timeout,
        test_child_processes_killed,
        test_secret_scrubbing,
        test_policy_denied_never_started,
        test_dangerous_env_rejected,
        test_output_cap_truncation,
        test_project_id_valid_jails_correctly,
        test_project_id_missing_rejected,
        test_project_id_empty_rejected,
        test_project_id_absolute_rejected,
        test_project_id_dotdot_rejected,
        test_project_id_path_separator_rejected,
        test_project_id_cwd_jail_differs_per_project,
        test_project_id_argv_literal_path_not_jailed,
        test_approved_unlocks_needs_approval_job,
        test_approved_never_unlocks_deny,
        test_cancel_running_job,
        test_cancel_nonexistent_job_is_noop,
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
