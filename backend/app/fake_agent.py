"""M1 fake agent: proves the job pipe end to end without an LLM (COORDINATION gate M1).

On a new run it writes a small script into the project jail, then runs it, so
the worker streams real log lines back. It uses the same suspend/resume shape
as the real agent loop (M2): the task waits for each job and continues when
the job's result arrives. It is replaced by the orchestrator in M2.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import runs
from .events import emit
from .ids import new_id, now_iso
from .models import AgentTask, Job, Run

TASK_TYPE = "m1_pipe_check"
ACTOR = "fake_agent"
SCRIPT_PATH = "m1/hello.py"
SCRIPT = '''import time

for i in range(1, 6):
    print(f"evolab pipe check: step {i}/5", flush=True)
    time.sleep(0.5)
print("evolab pipe check: done", flush=True)
'''


def _task_event(db: Session, task: AgentTask, summary: str) -> None:
    emit(db, task.run_id, ACTOR, "agent.task",
         {"task_id": task.id, "agent_id": None, "agent_name": "M1 fake agent", "status": task.status, "summary": summary})


def start(db: Session, run: Run) -> AgentTask:
    from .jobs import create_job

    runs.set_status(db, run, "running", ACTOR)
    task = AgentTask(id=new_id("tsk"), run_id=run.id, task_type=TASK_TYPE, required_tags_json=[],
                     input_json={"step": "write"}, status="waiting_for_job")
    db.add(task)
    db.flush()
    _task_event(db, task, "Writing the pipe-check script")
    create_job(db, run, "write_file", {"path": SCRIPT_PATH, "content": SCRIPT}, task_id=task.id, timeout_s=60,
               actor=ACTOR)
    return task


def _continue(db: Session, task: AgentTask, job: Job) -> None:
    from .jobs import create_job

    run = db.get(Run, task.run_id)
    if job.status != "done":
        task.status, task.ended_at = "failed", now_iso()
        task.output_json = {"failed_job_id": job.id, "status": job.status}
        _task_event(db, task, f"Job {job.type} ended {job.status}")
        if run.status not in runs.TERMINAL:
            runs.set_status(db, run, "cancelled" if job.status == "cancelled" else "failed", ACTOR)
        return
    if task.input_json.get("step") == "write":
        task.input_json = {"step": "run"}
        task.status = "waiting_for_job"
        _task_event(db, task, "Running the pipe-check script")
        create_job(db, run, "python_script", {"argv": ["python", SCRIPT_PATH], "cwd": ".", "env": {}},
                   task_id=task.id, timeout_s=120, actor=ACTOR)
    else:
        task.status, task.ended_at = "done", now_iso()
        task.output_json = {"job_id": job.id, "exit_code": job.exit_code}
        _task_event(db, task, "Pipe check passed")
        runs.set_status(db, run, "done", ACTOR)


def on_job_finished(db: Session, job: Job) -> None:
    if job.task_id is None:
        return
    task = db.get(AgentTask, job.task_id)
    if task is None or task.task_type != TASK_TYPE or task.status != "waiting_for_job":
        return
    run = db.get(Run, task.run_id)
    if run.status == "paused" and job.status == "done":
        task.status = "queued"                      # resume() continues it
        task.input_json = {**task.input_json, "pending_job_id": job.id}
        _task_event(db, task, "Paused; will continue on resume")
        return
    _continue(db, task, job)


def resume(db: Session, run: Run) -> None:
    for task in db.scalars(select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.task_type == TASK_TYPE,
                                                   AgentTask.status == "queued")):
        job = db.get(Job, task.input_json.get("pending_job_id"))
        task.status = "waiting_for_job"
        if job is not None:
            _continue(db, task, job)
