"""Supermemory REST client (D-038). Add: POST /v3/documents. Search: POST /v4/search.
Shapes verified against the API reference on 2026-10-10. Backend only; the key never leaves it."""

from __future__ import annotations

import logging
import re

import httpx

log = logging.getLogger("evolab.supermemory")
_TAG_OK = re.compile(r"[^A-Za-z0-9_\-]")


def tag(text: str) -> str:
    """Container tags: letters, digits, '_' and '-' only, at most 100 characters."""
    return _TAG_OK.sub("-", text)[:100]


class SupermemoryError(RuntimeError):
    pass


class Supermemory:
    def __init__(self, api_key: str, base_url: str = "https://api.supermemory.ai", timeout_s: float = 20.0):
        self.api_key, self.base_url, self.timeout_s = api_key, base_url.rstrip("/"), timeout_s

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = httpx.post(self.base_url + path, json=body, timeout=self.timeout_s,
                           headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        except httpx.HTTPError as exc:
            raise SupermemoryError(f"{path}: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise SupermemoryError(f"{path}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def add(self, content: str, container_tag: str, custom_id: str, metadata: dict) -> str | None:
        clean_meta = {k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))}
        data = self._post("/v3/documents", {"content": content[:20_000], "containerTag": tag(container_tag),
                                            "customId": tag(custom_id), "metadata": clean_meta, "dreaming": "instant"})
        return data.get("id")

    def search(self, q: str, container_tags: list[str], limit: int = 5, kind: str | None = None) -> list[dict]:
        body: dict = {"q": q[:1000], "containerTags": [tag(t) for t in container_tags], "limit": limit,
                      "searchMode": "hybrid", "threshold": 0.4}
        if kind:
            body["filters"] = {"AND": [{"key": "kind", "value": kind}]}
        data = self._post("/v4/search", body)
        return [{"id": r.get("id"), "text": r.get("memory") or r.get("chunk") or "",
                 "similarity": float(r.get("similarity") or 0.0), "metadata": r.get("metadata") or {}}
                for r in data.get("results", [])]
