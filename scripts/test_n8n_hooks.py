"""Simulates both directions of the n8n integration (API.md section 11)
against a local mock backend: standard library plus `requests` only.

Outbound (backend -> n8n): posts a correctly-signed approval_requested
payload and a bad-signature one to a local receiver, checking the receiver
can tell them apart (mirrors what the n8n Webhook + signature-check node
pair should do).

Inbound (n8n -> backend): calls a local mock /hooks/n8n/decide with a good
token, a reused token, and an expired token, checking the responses match
API.md: 200 on success, 403 on invalid/used/expired (standard error
envelope, API.md section 1).

This does not require n8n or a real backend running -- it is a contract
test against a minimal mock implementing exactly what the docs specify, so
it can run in CI. Run: python scripts/test_n8n_hooks.py
"""
import hashlib
import hmac
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

FAILURES: list[str] = []
SIGNING_SECRET = "test-n8n-signing-secret"


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def compute_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# A minimal mock of the two endpoints under test:
# - POST /n8n-receiver  (stands in for n8n's inbound Webhook node, i.e. the
#   backend's outbound call target)
# - POST /hooks/n8n/decide  (stands in for the backend's real inbound hook)
# ---------------------------------------------------------------------------

class MockState:
    def __init__(self):
        self.lock = threading.Lock()
        self.received_webhooks: list[dict] = []
        # token -> {"approval_id", "decision", "used": bool, "expires_at": float}
        self.tokens: dict[str, dict] = {}


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": {}}}


class MockHandler(BaseHTTPRequestHandler):
    state: MockState = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length else b""

        if self.path == "/n8n-receiver":
            self._handle_receiver(raw_body)
            return
        if self.path == "/hooks/n8n/decide":
            self._handle_decide(raw_body)
            return
        self._send_json(404, error_body("not_found", "unknown path"))

    def _handle_receiver(self, raw_body: bytes) -> None:
        # Stands in for n8n's Webhook node + a signature-check Code node:
        # verify X-Signature over the raw body, record the outcome.
        signature_header = self.headers.get("X-Signature", "")
        expected = compute_signature(SIGNING_SECRET, raw_body)
        valid = hmac.compare_digest(signature_header, expected)
        try:
            body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            body = {}
        with self.state.lock:
            self.state.received_webhooks.append({"valid_signature": valid, "body": body})
        if not valid:
            self._send_json(401, {"ok": False, "reason": "bad signature"})
            return
        self._send_json(200, {"ok": True})

    def _handle_decide(self, raw_body: bytes) -> None:
        try:
            body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            self._send_json(400, error_body("validation_error", "invalid JSON"))
            return

        approval_id = body.get("approval_id")
        decision = body.get("decision")
        token = body.get("token")

        with self.state.lock:
            entry = self.state.tokens.get(token)

            if entry is None:
                self._send_json(403, error_body("forbidden", "invalid token"))
                return
            if entry["approval_id"] != approval_id or entry["decision"] != decision:
                self._send_json(403, error_body("forbidden", "token does not match approval/decision"))
                return
            if entry["used"]:
                self._send_json(403, error_body("forbidden", "token already used"))
                return
            if time.time() > entry["expires_at"]:
                self._send_json(403, error_body("forbidden", "token expired"))
                return

            entry["used"] = True
            # D-051: using either token invalidates both (approve and reject
            # for the same approval_id share a fate).
            for other_token, other_entry in self.state.tokens.items():
                if other_entry["approval_id"] == approval_id:
                    other_entry["used"] = True

        self._send_json(200, {"ok": True, "approval_id": approval_id, "status": decision})


def start_server(state: MockState):
    handler_cls = type("BoundMockHandler", (MockHandler,), {"state": state})
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


# ---------------------------------------------------------------------------
# Outbound direction tests
# ---------------------------------------------------------------------------

def test_outbound_correctly_signed_payload_accepted(base_url: str, state: MockState) -> None:
    payload = {
        "event": "approval_requested",
        "run_id": "run_test1",
        "approval_id": "apr_test1",
        "type": "plan",
        "summary": "13 tasks, 8 agents, ~45 min",
        "decisions": {
            "approve": {"token": "tok_approve_1", "decision_url": f"{base_url}/hooks/n8n/decide"},
            "reject": {"token": "tok_reject_1", "decision_url": f"{base_url}/hooks/n8n/decide"},
        },
        "expires_at": "2026-10-10T19:00:00Z",
    }
    body = json.dumps(payload).encode()
    signature = compute_signature(SIGNING_SECRET, body)

    resp = requests.post(
        f"{base_url}/n8n-receiver",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
        timeout=10,
    )
    check("outbound.correct_signature_200", resp.status_code == 200, resp.text)
    with state.lock:
        last = state.received_webhooks[-1]
    check("outbound.recorded_as_valid", last["valid_signature"] is True, last)


def test_outbound_bad_signature_rejected(base_url: str, state: MockState) -> None:
    payload = {"event": "approval_requested", "run_id": "run_test2", "approval_id": "apr_test2"}
    body = json.dumps(payload).encode()
    bad_signature = compute_signature("wrong-secret", body)

    resp = requests.post(
        f"{base_url}/n8n-receiver",
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": bad_signature},
        timeout=10,
    )
    check("outbound.bad_signature_401", resp.status_code == 401, resp.text)
    with state.lock:
        last = state.received_webhooks[-1]
    check("outbound.recorded_as_invalid", last["valid_signature"] is False, last)


# ---------------------------------------------------------------------------
# Inbound direction tests
# ---------------------------------------------------------------------------

def test_inbound_good_token_approved(base_url: str, state: MockState) -> None:
    with state.lock:
        state.tokens["tok_good"] = {
            "approval_id": "apr_good",
            "decision": "approve",
            "used": False,
            "expires_at": time.time() + 1800,
        }
    resp = requests.post(
        f"{base_url}/hooks/n8n/decide",
        json={"approval_id": "apr_good", "decision": "approve", "token": "tok_good"},
        timeout=10,
    )
    check("inbound.good_token_200", resp.status_code == 200, resp.text)


def test_inbound_reused_token_rejected(base_url: str, state: MockState) -> None:
    with state.lock:
        state.tokens["tok_reuse"] = {
            "approval_id": "apr_reuse",
            "decision": "approve",
            "used": False,
            "expires_at": time.time() + 1800,
        }
    body = {"approval_id": "apr_reuse", "decision": "approve", "token": "tok_reuse"}
    first = requests.post(f"{base_url}/hooks/n8n/decide", json=body, timeout=10)
    second = requests.post(f"{base_url}/hooks/n8n/decide", json=body, timeout=10)
    check("inbound.first_use_200", first.status_code == 200, first.text)
    check("inbound.reuse_403", second.status_code == 403, second.text)
    check("inbound.reuse_error_code_forbidden", second.json().get("error", {}).get("code") == "forbidden", second.text)


def test_inbound_either_token_invalidates_both(base_url: str, state: MockState) -> None:
    """D-051: using either the approve or reject token invalidates both."""
    with state.lock:
        state.tokens["tok_pair_approve"] = {
            "approval_id": "apr_pair",
            "decision": "approve",
            "used": False,
            "expires_at": time.time() + 1800,
        }
        state.tokens["tok_pair_reject"] = {
            "approval_id": "apr_pair",
            "decision": "reject",
            "used": False,
            "expires_at": time.time() + 1800,
        }
    approve_resp = requests.post(
        f"{base_url}/hooks/n8n/decide",
        json={"approval_id": "apr_pair", "decision": "approve", "token": "tok_pair_approve"},
        timeout=10,
    )
    reject_resp = requests.post(
        f"{base_url}/hooks/n8n/decide",
        json={"approval_id": "apr_pair", "decision": "reject", "token": "tok_pair_reject"},
        timeout=10,
    )
    check("inbound.pair_approve_200", approve_resp.status_code == 200, approve_resp.text)
    check("inbound.pair_reject_403_after_approve_used", reject_resp.status_code == 403, reject_resp.text)


def test_inbound_expired_token_rejected(base_url: str, state: MockState) -> None:
    with state.lock:
        state.tokens["tok_expired"] = {
            "approval_id": "apr_expired",
            "decision": "approve",
            "used": False,
            "expires_at": time.time() - 1,  # already expired
        }
    resp = requests.post(
        f"{base_url}/hooks/n8n/decide",
        json={"approval_id": "apr_expired", "decision": "approve", "token": "tok_expired"},
        timeout=10,
    )
    check("inbound.expired_403", resp.status_code == 403, resp.text)
    check("inbound.expired_error_code_forbidden", resp.json().get("error", {}).get("code") == "forbidden", resp.text)


def test_inbound_unknown_token_rejected(base_url: str, state: MockState) -> None:
    resp = requests.post(
        f"{base_url}/hooks/n8n/decide",
        json={"approval_id": "apr_unknown", "decision": "approve", "token": "tok_never_issued"},
        timeout=10,
    )
    check("inbound.unknown_token_403", resp.status_code == 403, resp.text)


def test_inbound_mismatched_decision_rejected(base_url: str, state: MockState) -> None:
    """A token bound to 'approve' must not work for 'reject', and vice versa."""
    with state.lock:
        state.tokens["tok_mismatch"] = {
            "approval_id": "apr_mismatch",
            "decision": "approve",
            "used": False,
            "expires_at": time.time() + 1800,
        }
    resp = requests.post(
        f"{base_url}/hooks/n8n/decide",
        json={"approval_id": "apr_mismatch", "decision": "reject", "token": "tok_mismatch"},
        timeout=10,
    )
    check("inbound.mismatched_decision_403", resp.status_code == 403, resp.text)


def main() -> None:
    state = MockState()
    server, port = start_server(state)
    base_url = f"http://127.0.0.1:{port}"

    try:
        tests = [
            test_outbound_correctly_signed_payload_accepted,
            test_outbound_bad_signature_rejected,
            test_inbound_good_token_approved,
            test_inbound_reused_token_rejected,
            test_inbound_either_token_invalidates_both,
            test_inbound_expired_token_rejected,
            test_inbound_unknown_token_rejected,
            test_inbound_mismatched_decision_rejected,
        ]
        for t in tests:
            t(base_url, state)

        if FAILURES:
            print(f"FAILED {len(FAILURES)} of {len(tests)} checks:")
            for f in FAILURES:
                print(f"  - {f}")
            sys.exit(1)
        print(f"ALL CHECKS PASSED ({len(tests)} scenarios)")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
