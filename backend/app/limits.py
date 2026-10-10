"""Request limits (API.md section 12, ARCHITECTURE 6.8): per-user rate limit on dashboard
routes and a body-size cap. Route-specific limits (chat per run, n8n hooks per IP, worker
log uploads per worker) live next to those routes."""

from __future__ import annotations

import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .errors import ApiError, error_body
from .security import SESSION_COOKIE, RateLimiter

DASHBOARD_LIMIT = (300, 60.0)              # 300 requests per minute per user (a live dashboard polls several routes)
JSON_BODY_MAX = 1 * 1024 * 1024            # 1 MB for JSON bodies
UPLOAD_PATHS = ("/inputs", "/worker/artifacts")
EXEMPT = ("/api/v1/health", "/api/v1/worker/", "/api/v1/hooks/", "/api/v1/uploads/")


class Limits(BaseHTTPMiddleware):
    def __init__(self, app, dashboard_limit: tuple[int, float] = DASHBOARD_LIMIT):
        super().__init__(app)
        self.limiter = RateLimiter(*dashboard_limit, message="Too many requests; slow down")

    async def dispatch(self, request, call_next):
        path = request.url.path
        size = request.headers.get("content-length")
        if size and size.isdigit() and int(size) > JSON_BODY_MAX and not path.endswith(UPLOAD_PATHS):
            return JSONResponse(error_body("validation_error", "Request body too large"), status_code=413)
        if path.startswith("/api/v1/") and not path.startswith(EXEMPT):
            auth = request.headers.get("authorization", "")
            token = request.cookies.get(SESSION_COOKIE) or (auth[7:] if auth.lower().startswith("bearer ") else "")
            key = hashlib.sha256(token.encode()).hexdigest()[:16] if token else f"ip:{request.client.host if request.client else '?'}"
            try:
                self.limiter.check(key)
            except ApiError as exc:
                return JSONResponse(error_body(exc.code, exc.message), status_code=429, headers={"Retry-After": "60"})
        return await call_next(request)
