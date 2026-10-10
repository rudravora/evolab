"""Outbound fetches from the backend: arXiv, GitHub, paper PDFs, dataset HEAD (ARCHITECTURE 2.4).

Every URL comes from untrusted input, so `safe_get` blocks SSRF: https/http only, the host
must resolve to public addresses (no loopback, private, link-local or metadata ranges),
redirects are followed manually and re-checked, and bodies are size-capped. Everything
returned is untrusted text.
"""

from __future__ import annotations

import io
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse

import httpx

TIMEOUT_S = 30.0
MAX_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5
UA = {"User-Agent": "EvoLab/0.1 (research reproduction; hackathon)"}
ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


class FetchError(RuntimeError):
    pass


def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError(f"cannot resolve {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError(f"blocked non-public address for {host}")


def safe_get(url: str, *, headers: dict | None = None, max_bytes: int = MAX_BYTES, method: str = "GET") -> httpx.Response:
    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise FetchError(f"unsupported URL: {url[:200]}")
        _public_host(parsed.hostname)
        with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, headers={**UA, **(headers or {})}) as c:
            with c.stream(method, url) as r:
                if r.is_redirect and "location" in r.headers:
                    url = urljoin(url, r.headers["location"])
                    continue
                body = bytearray()
                for chunk in r.iter_bytes():          # already decompressed
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise FetchError(f"response larger than {max_bytes} bytes")
                # Drop transfer headers: the body is decoded, so keeping content-encoding would make
                # httpx try to decompress it a second time (seen live with GitHub's gzip responses).
                headers = [(k, v) for k, v in r.headers.items() if k.lower() not in ("content-encoding", "content-length",
                                                                                   "transfer-encoding")]
                return httpx.Response(r.status_code, headers=headers, content=bytes(body), request=r.request)
    raise FetchError("too many redirects")


def arxiv_id(text: str) -> str | None:
    m = ARXIV_ID.search(text or "")
    return m.group(1) if m else None


@dataclass
class Paper:
    arxiv_id: str | None
    title: str
    url: str
    abstract: str
    published: str | None = None


_ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _parse_arxiv_feed(xml: bytes) -> list[Paper]:
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", _ATOM):
        link = (e.findtext("a:id", default="", namespaces=_ATOM) or "").strip()
        out.append(Paper(arxiv_id=arxiv_id(link), title=" ".join((e.findtext("a:title", "", _ATOM) or "").split()),
                         url=link.replace("http://", "https://"),
                         abstract=" ".join((e.findtext("a:summary", "", _ATOM) or "").split())[:2000],
                         published=(e.findtext("a:published", "", _ATOM) or "")[:10] or None))
    return out


class Web:
    """Real network implementation. Tests replace it with a fake that has the same methods."""

    def arxiv_search(self, query: str, max_results: int = 5) -> list[Paper]:
        q = quote(query[:300])
        r = safe_get(f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={max_results}")
        return _parse_arxiv_feed(r.content)

    def arxiv_meta(self, aid: str) -> Paper | None:
        r = safe_get(f"https://export.arxiv.org/api/query?id_list={quote(aid)}")
        papers = _parse_arxiv_feed(r.content)
        return papers[0] if papers else None

    def pdf_text(self, url: str) -> str:
        aid = arxiv_id(url)
        if aid and "arxiv.org" in url:
            url = f"https://arxiv.org/pdf/{aid}"
        r = safe_get(url)
        if r.status_code != 200:
            raise FetchError(f"PDF fetch returned {r.status_code}")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(r.content))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:60])

    def github_readme(self, repo_url: str) -> str | None:
        m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", repo_url or "")
        if not m:
            return None
        owner, repo = m.group(1), m.group(2).removesuffix(".git")
        r = safe_get(f"https://api.github.com/repos/{owner}/{repo}/readme",
                     headers={"Accept": "application/vnd.github.raw+json"}, max_bytes=2 * 1024 * 1024)
        return r.text if r.status_code == 200 else None

    def github_search(self, query: str, limit: int = 5) -> list[dict]:
        r = safe_get(f"https://api.github.com/search/repositories?q={quote(query[:200])}&per_page={limit}",
                     headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return []
        return [{"name": i["full_name"], "url": i["html_url"], "stars": i.get("stargazers_count"),
                 "description": (i.get("description") or "")[:300]} for i in r.json().get("items", [])[:limit]]

    def head(self, url: str) -> dict:
        r = safe_get(url, method="HEAD", max_bytes=1024)
        return {"status": r.status_code, "content_type": r.headers.get("content-type"),
                "size_bytes": int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None}
