from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.database import get_db
from src.core.security import decode_access_token
from src.schemas.auth import (
    GoogleRequest,
    LoginRequest,
    RegisterRequest,
    SetPasswordRequest,
    UserResponse,
)
from src.services.auth import (
    AuthError,
    IssuedSession,
    get_active_user,
    login_user,
    login_with_google,
    logout_user,
    refresh_session,
    register_user,
    set_password,
    to_user_response,
)

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"

router = APIRouter()


def current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AuthError(401, "Not authenticated.")
    try:
        user_id: UUID = decode_access_token(token)
    except ValueError as exc:
        raise AuthError(401, "Not authenticated.") from exc
    return get_active_user(db, user_id)


@router.post("/api/auth/register", response_model=UserResponse)
def register(
    body: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    session = register_user(db, body.email, body.password)
    _set_session_cookies(response, session)
    return to_user_response(session.user)


@router.post("/api/auth/login", response_model=UserResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    session = login_user(db, body.email, body.password)
    _set_session_cookies(response, session)
    return to_user_response(session.user)


@router.post("/api/auth/google", response_model=UserResponse)
def google(
    body: GoogleRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> UserResponse:
    session = login_with_google(db, body.id_token)
    _set_session_cookies(response, session)
    return to_user_response(session.user)


@router.post("/api/auth/password", status_code=204)
def password(
    body: SetPasswordRequest,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> None:
    set_password(db, user, body.password)


@router.post("/api/auth/refresh", response_model=UserResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> UserResponse:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AuthError(401, "Refresh token is not valid.")
    session = refresh_session(db, raw)
    _set_session_cookies(response, session)
    return to_user_response(session.user)


@router.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        logout_user(db, raw)
    _clear_session_cookies(response)


@router.get("/api/me", response_model=UserResponse)
def me(user=Depends(current_user)) -> UserResponse:
    return to_user_response(user)


def _cookie_flags() -> dict:
    return {
        "httponly": True,
        "secure": get_settings().cookie_secure,
        "samesite": "lax",
    }


def _set_session_cookies(response: Response, session: IssuedSession) -> None:
    settings = get_settings()
    flags = _cookie_flags()
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=settings.access_token_minutes * 60,
        path="/",
        **flags,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=settings.refresh_token_days * 86400,
        path=REFRESH_COOKIE_PATH,
        **flags,
    )


def _clear_session_cookies(response: Response) -> None:
    flags = _cookie_flags()
    response.delete_cookie(ACCESS_COOKIE, path="/", **flags)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, **flags)
