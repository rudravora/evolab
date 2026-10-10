"""Public, token-authenticated routes: the n8n decision hook (API.md 11) and the signed
upload-relay download the worker uses (Q-18). Neither uses the dashboard session."""

from __future__ import annotations

import hmac
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..models import Approval, Input
from ..n8n import read_token, token_hash
from ..uploads import relay_signature

router = APIRouter(tags=["hooks"])


class DecideIn(BaseModel):
    approval_id: str = Field(min_length=1, max_length=64)
    decision: Literal["approve", "reject"]
    token: str = Field(min_length=10, max_length=2000)


@router.post("/hooks/n8n/decide")
def n8n_decide(body: DecideIn, request: Request, db: Session = Depends(get_db)) -> dict:
    from .approvals import apply_decision

    settings = request.app.state.settings
    request.app.state.hook_limiter.check(request.client.host if request.client else "unknown")
    forbidden = ApiError(403, "forbidden", "Invalid, used or expired token")
    if not settings.n8n_signing_secret:
        raise forbidden
    data = read_token(settings.n8n_signing_secret, body.token)
    a = db.get(Approval, body.approval_id)
    if not data or data.get("a") != body.approval_id or data.get("d") != body.decision or a is None:
        raise forbidden
    if a.status != "pending" or not a.token_hash or token_hash(body.token) not in a.token_hash.split(","):
        raise forbidden
    apply_decision(db, a, "approved" if body.decision == "approve" else "rejected", "n8n", "decided from phone",
                   request.app.state.services)
    db.commit()
    return {"approval_id": a.id, "status": a.status}


@router.get("/uploads/{input_id}", response_class=FileResponse)
def relay_download(input_id: str, request: Request, exp: int = Query(...), sig: str = Query(..., max_length=128),
                   db: Session = Depends(get_db)):
    settings = request.app.state.settings
    if exp < time.time() or not hmac.compare_digest(sig, relay_signature(settings.app_secret, input_id, exp)):
        raise ApiError(403, "forbidden", "Invalid or expired link")
    inp = db.get(Input, input_id)
    path = (inp.meta_json or {}).get("path") if inp else None
    if not path or not Path(path).exists():
        raise ApiError(404, "not_found", "Upload not available")
    return FileResponse(path, filename=(inp.meta_json or {}).get("filename", "upload"), media_type="application/octet-stream")
