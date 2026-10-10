"""LLM wrapper: `llm.call(tier, messages)` over the event gateway (AGENTS.md section 3, D-041).

Gateway facts (tested 2026-10-10, recorded in backend/agents/models.json):
- one POST endpoint for all models, OpenAI Chat Completions JSON, Bearer auth, no streaming;
- the `tools` field is ignored, so agents use a JSON-in-text tool protocol (app/toolproto.py);
- each request body is capped at 48 KB, so messages are trimmed to fit before sending;
- GPT tiers cap output with `max_completion_tokens` (and spend part of it on hidden
  reasoning), DeepSeek with `max_tokens`.

Retries with backoff on 429/5xx/timeouts, optional fallback to another tier, a small
cache for identical calls, and a tracer hook. The HTTP transport is injectable so tests
never reach the network.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Settings

MODELS = json.loads((Path(__file__).resolve().parent.parent / "agents" / "models.json").read_text(encoding="utf-8"))
GATEWAY = MODELS["gateway"]
TIERS = MODELS["tiers"]
MAX_REQUEST_BYTES = int(GATEWAY["max_request_bytes"])
MAX_OUTPUT_TOKENS = int(GATEWAY.get("max_output_tokens", 4000))   # gateway rejects larger caps with HTTP 400
SAFETY_BYTES = 1024           # headroom for headers the gateway may count
RETRY_DELAYS_S = (5.0, 15.0, 30.0)     # the gateway rate-limits per minute; back off across a window
TRIM_NOTE = "[trimmed to fit the 48 KB request limit]"

Transport = Callable[[dict, dict, float], tuple[int, dict]]   # (body, headers, timeout) -> (status, json)


class LLMError(RuntimeError):
    pass


class LLMRateLimited(LLMError):
    """The orchestrator turns this into a short pause, not a task failure (AGENTS.md section 3)."""


@dataclass
class LLMReply:
    text: str
    tier: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    trimmed: bool = False
    cached: bool = False


def httpx_transport(url: str) -> Transport:
    def send(body: dict, headers: dict, timeout: float) -> tuple[int, dict]:
        r = httpx.post(url, json=body, headers=headers, timeout=timeout)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"error": r.text[:500]}
    return send


def body_size(body: dict) -> int:
    return len(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def fit_messages(messages: list[dict], build_body: Callable[[list[dict]], dict],
                 limit: int = MAX_REQUEST_BYTES - SAFETY_BYTES) -> tuple[list[dict], bool]:
    """Trim messages until the request body fits `limit` bytes.

    Order (AGENTS.md section 3): keep the system prompt and the first user message
    (task input); blank the oldest middle messages first; drop blanked pairs; then cut
    the longest remaining message from its middle. Never sends an over-size body.
    """
    msgs = [dict(m) for m in messages]
    if body_size(build_body(msgs)) <= limit:
        return msgs, False
    # 1. blank oldest middle messages (tool results, earlier replies)
    for i in range(2, len(msgs) - 1):
        if body_size(build_body(msgs)) <= limit:
            return msgs, True
        if msgs[i]["content"] != TRIM_NOTE:
            msgs[i]["content"] = TRIM_NOTE
    # 2. drop blanked messages entirely, oldest first
    while len(msgs) > 3 and body_size(build_body(msgs)) > limit:
        idx = next((i for i in range(2, len(msgs) - 1) if msgs[i]["content"] == TRIM_NOTE), None)
        if idx is None:
            break
        msgs.pop(idx)
    # 3. cut the longest message from the middle until it fits
    while body_size(build_body(msgs)) > limit:
        longest = max(range(len(msgs)), key=lambda i: len(msgs[i]["content"]))
        text = msgs[longest]["content"]
        over = body_size(build_body(msgs)) - limit
        keep = max(len(text) - over - len(TRIM_NOTE) - 64, 0)
        if keep == 0 and len(text) <= len(TRIM_NOTE):
            raise LLMError("request cannot be trimmed under the gateway limit")
        msgs[longest]["content"] = text[: keep // 2] + "\n" + TRIM_NOTE + "\n" + text[len(text) - keep // 2:]
    return msgs, True


class LLMClient:
    def __init__(self, settings: Settings, transport: Transport | None = None, tracer=None, cache_size: int = 256):
        self.settings = settings
        self.models = settings.llm_models
        self.transport = transport or httpx_transport(settings.llm_base_url)
        self.tracer = tracer
        self._cache: OrderedDict[str, LLMReply] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def configured(self) -> bool:
        return bool(self.settings.llm_base_url and self.settings.llm_api_key and all(self.models.values()))

    def _body(self, tier: str, messages: list[dict], max_output_tokens: int) -> dict:
        return {"model": self.models[tier], "messages": messages, "stream": False,
                TIERS[tier]["output_param"]: max(1, min(max_output_tokens, MAX_OUTPUT_TOKENS))}

    def call(self, tier: str, messages: list[dict], *, max_output_tokens: int = 4000, allow_fallback: bool = True,
             trace=None, name: str = "llm") -> LLMReply:
        if tier not in TIERS:
            raise LLMError(f"unknown tier {tier}")
        if not self.configured():
            raise LLMError("LLM gateway is not configured (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_*)")
        tiers = [tier] + (list(TIERS[tier]["fallback"]) if allow_fallback else [])
        last: Exception | None = None
        for t in tiers:
            try:
                reply = self._call_tier(t, messages, max_output_tokens)
                if self.tracer and trace is not None:
                    self.tracer.log_llm(trace, name, t, messages, reply)
                return reply
            except LLMRateLimited as exc:
                last = exc            # try the next tier
        raise LLMRateLimited(str(last) if last else "rate limited")

    def _call_tier(self, tier: str, messages: list[dict], max_output_tokens: int) -> LLMReply:
        fitted, trimmed = fit_messages(messages, lambda m: self._body(tier, m, max_output_tokens))
        body = self._body(tier, fitted, max_output_tokens)
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                hit = self._cache[key]
                return LLMReply(**{**hit.__dict__, "cached": True})
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}", "Content-Type": "application/json"}
        for attempt, delay in enumerate((*RETRY_DELAYS_S, None)):
            started = time.monotonic()
            try:
                status, data = self.transport(body, headers, self.settings.llm_timeout_s)
            except httpx.HTTPError as exc:
                # Timeouts, dropped connections and undecodable error pages (seen live from the
                # gateway on long requests) are all retried, then reported as a gateway error.
                status, data = 0, {"error": f"{type(exc).__name__}"}
            latency = time.monotonic() - started
            if status == 200:
                reply = self._parse(tier, data, latency, trimmed)
                with self._lock:
                    self._cache[key] = reply
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                return reply
            retryable = status in (0, 408, 409, 429) or status >= 500
            if not retryable:
                raise LLMError(f"gateway returned {status}: {str(data)[:300]}")
            if delay is None:
                if status == 429:
                    raise LLMRateLimited(f"{tier}: rate limited after {attempt + 1} attempts")
                raise LLMError(f"{tier}: gateway error {status} after {attempt + 1} attempts")
            time.sleep(delay)
        raise LLMError("unreachable")

    def _parse(self, tier: str, data: dict, latency: float, trimmed: bool) -> LLMReply:
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected gateway response: {str(data)[:300]}") from exc
        usage = data.get("usage") or {}
        if not text.strip() and choice.get("finish_reason") == "length":
            raise LLMError("empty reply: output cap spent on reasoning; raise max_output_tokens")
        return LLMReply(text=text, tier=tier, model=self.models[tier], tokens_in=int(usage.get("prompt_tokens") or 0),
                        tokens_out=int(usage.get("completion_tokens") or 0), latency_s=round(latency, 3), trimmed=trimmed)
