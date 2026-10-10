"""Owner sign-in (API.md section 2a, D-044)."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..errors import ApiError
from ..security import OWNER_ID, SESSION_COOKIE, LoginLimiter, current_user, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = LoginLimiter()


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class User(BaseModel):
    id: str


class LoginResponse(BaseModel):
    user: User
    token: str
    expires_at: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response,
          settings: Settings = Depends(get_settings)) -> LoginResponse:
    """Sets an HttpOnly session cookie and also returns the token for `Authorization: Bearer`."""
    limiter.check(request.client.host if request.client else "unknown")
    if not settings.owner_password_hash:
        raise ApiError(403, "forbidden", "Sign-in is not configured (OWNER_PASSWORD_HASH is empty)")
    if not verify_password(body.password, settings.owner_password_hash):
        raise ApiError(401, "unauthorized", "Wrong password")
    token, exp = issue_token(settings)
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_s, httponly=True,
                        secure=settings.https, samesite="lax", path="/")
    return LoginResponse(user=User(id=OWNER_ID), token=token, expires_at=exp)


@router.post("/logout", status_code=204)
def logout(response: Response, settings: Settings = Depends(get_settings)) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.https, httponly=True, samesite="lax")
    response.status_code = 204
    return response


@router.get("/me", response_model=User)
def me(user_id: str = Depends(current_user)) -> User:
    return User(id=user_id)
