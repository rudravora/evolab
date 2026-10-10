"""Owner sign-in, session tokens and security headers (ARCHITECTURE section 6, D-044).

- One owner account. `OWNER_PASSWORD_HASH` (scrypt) lives in `.env`; generate it
  with `backend/scripts/hash_password.py`. The password itself is never stored.
- Session token: base64url(JSON {sub, iat, exp}) + "." + HMAC-SHA256 with
  APP_SECRET. Sent as an HttpOnly cookie, or as `Authorization: Bearer <token>`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings
from .errors import ApiError

OWNER_ID = "usr_owner"
SESSION_COOKIE = "evolab_session"

# scrypt parameters (about 16 MB, well under a second on a laptop)
_N, _R, _P = 2**14, 8, 1


# --- passwords ---------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64),
                            n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# --- session tokens ------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str, secret: str) -> str:
    return _b64url(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def issue_token(settings: Settings, sub: str = OWNER_ID) -> tuple[str, int]:
    now = int(time.time())
    exp = now + settings.session_ttl_s
    body = _b64url(json.dumps({"sub": sub, "iat": now, "exp": exp}, separators=(",", ":")).encode())
    return f"{body}.{_sign(body, settings.app_secret)}", exp


def read_token(token: str, settings: Settings) -> str | None:
    """Return the subject of a valid, unexpired token, else None."""
    try:
        body, sig = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(body, settings.app_secret)):
        return None
    try:
        claims = json.loads(_unb64url(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(claims.get("exp", 0)) <= int(time.time()):
        return None
    return claims.get("sub")


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Dependency for dashboard routes: session cookie or Bearer token."""
    token = request.cookies.get(SESSION_COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    sub = read_token(token, settings) if token else None
    if sub is None:
        raise ApiError(401, "unauthorized", "Sign in required")
    return sub


# --- login rate limit ------------------------------------------------------------

class RateLimiter:
    """At most `limit` hits per `window_s` per key (in memory, single process)."""

    def __init__(self, limit: int, window_s: float, message: str = "Too many requests"):
        self.limit, self.window_s, self.message = limit, window_s, message
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            raise ApiError(429, "rate_limited", self.message)
        hits.append(now)


def LoginLimiter() -> RateLimiter:
    return RateLimiter(5, 60.0, "Too many sign-in attempts; try again in a minute")


# --- security headers ------------------------------------------------------------

class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Cache-Control", "no-store")
        if request.url.path.startswith(("/docs", "/redoc")):
            h.setdefault("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                         "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
                         "frame-ancestors 'none'")
        else:
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if self.hsts:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
