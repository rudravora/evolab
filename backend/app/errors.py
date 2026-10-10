"""Standard error shape (API.md section 1): { "error": { "code", "message", "details" } }.

Never returns stack traces; unexpected errors are logged server-side and
reported as `internal_error`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("evolab")

STATUS_CODES = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "invalid_state",
    409: "conflict",
    413: "validation_error",
    422: "validation_error",
    429: "rate_limited",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, exc: ApiError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError):
        fields = [
            {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(error_body("validation_error", "Invalid request", {"fields": fields}), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException):
        code = STATUS_CODES.get(exc.status_code, "internal_error")
        message = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def _unexpected(req: Request, exc: Exception):
        log.exception("unhandled error on %s %s", req.method, req.url.path)
        return JSONResponse(error_body("internal_error", "Internal error"), status_code=500)
