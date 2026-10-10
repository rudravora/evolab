"""Browser uploads and worker artifacts (API.md sections 3 and 9, D-034, Q-18).

- Paper PDFs and datasets uploaded in the browser are stored under ARTIFACTS_DIR/uploads.
- Dataset uploads are relayed to the worker: a `download` job pointing at a short-lived
  signed backend URL (GET /api/v1/uploads/{input_id}?exp=&sig=). Once the worker has it,
  the backend copy is deleted (Q-18 suggestion). No size cap for datasets for now (D-034);
  the type allowlist still applies.
- Worker result files arrive through POST /worker/artifacts (size-capped, type-allowlisted).
"""

from __future__ import annotations

import hashlib
import hmac

import time
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import policy
from .errors import ApiError
from .ids import new_id
from .models import Input, Job, Project, Run

UPLOAD_TYPES = {".pdf", ".csv", ".tsv", ".json", ".parquet", ".txt", ".md", ".zip"}
ARTIFACT_TYPES = {".json", ".csv", ".tsv", ".txt", ".md", ".log", ".png", ".svg", ".pdf"}
ARTIFACT_MAX_BYTES = 50 * 1024 * 1024
RELAY_TTL_S = 3600


def _safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(name or "file").name)
    return keep[:120] or "file"


def _save(file: UploadFile, dest: Path, max_bytes: int | None) -> tuple[int, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    h, size = hashlib.sha256(), 0
    with open(dest, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise ApiError(413, "validation_error", f"file larger than {max_bytes} bytes")
            h.update(chunk)
            out.write(chunk)
    return size, h.hexdigest()


def relay_signature(secret: str, input_id: str, exp: int) -> str:
    return hmac.new(secret.encode(), f"relay|{input_id}|{exp}".encode(), hashlib.sha256).hexdigest()


def relay_url(settings, input_id: str) -> str:
    exp = int(time.time()) + RELAY_TTL_S
    return f"{settings.public_base_url}/api/v1/uploads/{input_id}?exp={exp}&sig={relay_signature(settings.app_secret, input_id, exp)}"


def store_upload(db: Session, services, project: Project, kind: str, file: UploadFile) -> Input:
    name = _safe_name(file.filename or "upload")
    ext = Path(name).suffix.lower()
    if ext not in UPLOAD_TYPES or (kind == "paper" and ext != ".pdf"):
        raise ApiError(422, "validation_error", f"file type {ext or '(none)'} is not allowed for {kind}")
    inp = Input(id=new_id("inp"), project_id=project.id, kind=kind, ref=name, source="upload", meta_json={})
    path = Path(services.settings.artifacts_dir) / "uploads" / project.id / f"{inp.id}{ext}"
    size, digest = _save(file, path, None)
    inp.meta_json = {"untrusted": True, "path": str(path), "size_bytes": size, "sha256": digest, "filename": name}
    db.add(inp)
    db.flush()
    if kind == "dataset":
        run = db.scalar(select(Run).where(Run.project_id == project.id, Run.status.in_(("planning", "awaiting_approval", "running")))
                        .order_by(Run.started_at.desc()).limit(1))
        if run is not None:
            relay(db, services, run, inp)
    return inp


def relay(db: Session, services, run: Run, inp: Input) -> Job:
    from .jobs import create_job

    payload = {"url": relay_url(services.settings, inp.id), "dest": f"data/{inp.meta_json['filename']}",
               "sha256": inp.meta_json["sha256"], "relay_input_id": inp.id}
    job = create_job(db, run, "download", payload, timeout_s=600, actor="uploads")
    job.approved = True              # the researcher uploaded it; the worker may fetch from the backend host
    if job.status == "awaiting_approval":
        job.status = "pending"
    inp.meta_json = {**inp.meta_json, "relay_job_id": job.id, "worker_path": payload["dest"]}
    return job


def on_job_finished(db: Session, job: Job) -> bool:
    """Delete the backend copy once the worker has the dataset."""
    input_id = (job.payload_json or {}).get("relay_input_id")
    if not input_id:
        return False
    inp = db.get(Input, input_id)
    if inp is not None and job.status == "done":
        Path(inp.meta_json.get("path", "")).unlink(missing_ok=True)
        inp.meta_json = {**inp.meta_json, "relayed": True, "path": None}
    return True


def trust_backend_host(settings) -> None:
    """Relay downloads from our own backend are allowed (http only in local dev)."""
    policy.TRUSTED_URL_PREFIXES[:] = [f"{settings.public_base_url}/api/v1/uploads/"]


def save_artifact(services, run_id: str, job_id: str, rel_path: str, file: UploadFile) -> tuple[Path, int, str]:
    if problem := policy.check_path(rel_path, "path"):
        raise ApiError(422, "validation_error", problem)
    name = _safe_name(rel_path)
    if Path(name).suffix.lower() not in ARTIFACT_TYPES:
        raise ApiError(422, "validation_error", "artifact type not allowed")
    dest = Path(services.settings.artifacts_dir) / run_id / "files" / job_id / name
    size, digest = _save(file, dest, ARTIFACT_MAX_BYTES)
    return dest, size, digest


