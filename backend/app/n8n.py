"""n8n plumbing (API.md section 11, FR-26, FR-27, D-016): phone approvals and alerts only.

Outbound: POST {N8N_WEBHOOK_URL} with `X-Signature: sha256=<HMAC of the body>` for
approval_requested, job_failed and run_finished. Approval messages carry one decision
link per option; each link holds a single-use token bound to the approval id and the
decision, expiring with the approval. Only the token's hash is stored.

Inbound: POST /hooks/n8n/decide {approval_id, decision, token}; see routes/hooks.py.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time

import httpx
from sqlalchemy.orm import Session

from .config import Settings

log = logging.getLogger("evolab.n8n")
DECISIONS = ("approve", "reject")
DEFAULT_TTL_S = 30 * 60


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sign_body(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_token(secret: str, approval_id: str, decision: str, expires_at: int) -> str:
    payload = _b64(json.dumps({"a": approval_id, "d": decision, "e": expires_at}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(secret: str, token: str) -> dict | None:
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data if int(data["e"]) > time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Notifier:
    def __init__(self, settings: Settings, post=None):
        self.settings = settings
        self._post = post or (lambda url, body, headers: httpx.post(url, content=body, headers=headers, timeout=10))
        self.sent: list[dict] = []      # last payloads, for tests and debugging (no secrets inside)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.n8n_webhook_url and self.settings.n8n_signing_secret)

    def send(self, db: Session, event: str, obj) -> None:
        if not self.enabled:
            return
        from .models import Approval, Job, Run

        if isinstance(obj, Approval):
            body = self._approval(obj)
        elif isinstance(obj, Job):
            body = {"event": event, "run_id": obj.run_id, "job_id": obj.id, "status": obj.status,
                    "summary": f"{obj.type} job {obj.status}"}
        elif isinstance(obj, Run):
            body = {"event": event, "run_id": obj.id, "status": obj.status, "summary": f"run {obj.status}"}
        else:
            return
        body["event"] = event
        self.sent.append(body)
        raw = json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "X-Signature": sign_body(raw, self.settings.n8n_signing_secret)}
        threading.Thread(target=self._deliver, args=(raw, headers), daemon=True).start()

    def _deliver(self, raw: bytes, headers: dict) -> None:
        try:
            self._post(self.settings.n8n_webhook_url, raw, headers)
        except Exception:  # noqa: BLE001 - plumbing must never break a run
            log.warning("n8n webhook delivery failed", exc_info=True)

    def _approval(self, a) -> dict:
        exp = int(time.time()) + DEFAULT_TTL_S
        links, hashes = {}, []
        for d in DECISIONS:
            tok = make_token(self.settings.n8n_signing_secret, a.id, d, exp)
            hashes.append(token_hash(tok))
            links[d] = {"token": tok, "decision_url": f"{self.settings.public_base_url}/api/v1/hooks/n8n/decide"}
        a.token_hash = ",".join(hashes)          # single use: cleared once any token is used
        return {"run_id": a.run_id, "approval_id": a.id, "type": a.type,
                "summary": (a.payload_json or {}).get("summary", ""), "decisions": links,
                "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(exp))}
