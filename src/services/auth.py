from dataclasses import dataclass
from datetime import timedelta

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    utcnow,
    verify_password,
)
from src.models.refresh_token import RefreshToken
from src.models.subscription import Plan, Subscription
from src.models.user import Role, User
from src.schemas.auth import UserResponse


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    user: User


def verify_google_id_token(token: str) -> GoogleProfile:
    client_id = get_settings().google_client_id
    if not client_id:
        raise AuthError(500, "Google sign-in is not configured.")
    try:
        info = id_token.verify_oauth2_token(token, requests.Request(), client_id)
    except (ValueError, GoogleAuthError) as exc:
        raise AuthError(401, "Google sign-in could not be verified.") from exc
    email = info.get("email")
    if not email or not info.get("email_verified") or not info.get("sub"):
        raise AuthError(401, "Google account email is not verified.")
    return GoogleProfile(sub=str(info["sub"]), email=str(email).strip().lower())


def register_user(db: Session, email: str, password: str) -> IssuedSession:
    if _find_by_email(db, email) is not None:
        raise AuthError(409, "An account with this email already exists.")
    user = _create_user(db, email=email, password_hash=hash_password(password))
    return _issue_tokens(db, user)


def login_user(db: Session, email: str, password: str) -> IssuedSession:
    user = _find_by_email(db, email)
    if user is None or user.password_hash is None:
        raise AuthError(401, "Email or password is incorrect.")
    _reject_if_closed(user)
    if not verify_password(password, user.password_hash):
        raise AuthError(401, "Email or password is incorrect.")
    user.last_connection = utcnow()
    return _issue_tokens(db, user)


def login_with_google(db: Session, token: str) -> IssuedSession:
    profile = verify_google_id_token(token)
    user = db.scalar(select(User).where(User.google_sub == profile.sub))
    if user is not None:
        _reject_if_closed(user)
        user.last_connection = utcnow()
        return _issue_tokens(db, user)

    user = _find_by_email(db, profile.email)
    if user is not None:
        _reject_if_closed(user)
        if user.google_sub is not None and user.google_sub != profile.sub:
            raise AuthError(409, "This email is already linked to another Google account.")
        user.google_sub = profile.sub
        user.last_connection = utcnow()
        return _issue_tokens(db, user)

    user = _create_user(db, email=profile.email, google_sub=profile.sub)
    return _issue_tokens(db, user)


def set_password(db: Session, user: User, password: str) -> None:
    _reject_if_closed(user)
    if user.password_hash is not None:
        raise AuthError(409, "This account already has a password.")
    user.password_hash = hash_password(password)
    db.commit()


def refresh_session(db: Session, refresh_token: str) -> IssuedSession:
    stored = _get_valid_refresh_token(db, refresh_token)
    user = _load_user(db, stored.user_id)
    _reject_if_closed(user)
    stored.revoked = True
    return _issue_tokens(db, user)


def logout_user(db: Session, refresh_token: str) -> None:
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
    )
    if stored is None or stored.revoked or _as_utc(stored.expires_at) <= utcnow():
        return
    stored.revoked = True
    db.commit()


def get_active_user(db: Session, user_id) -> User:
    user = _load_user(db, user_id)
    _reject_if_closed(user)
    return user


def to_user_response(user: User) -> UserResponse:
    subscription = user.subscription
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        last_connection=user.last_connection,
        subscription={
            "id": subscription.id,
            "plan": subscription.plan,
            "subscription_status": subscription.subscription_status,
            "current_period_end": subscription.current_period_end,
            "deleted_at": subscription.deleted_at,
            "deleted_reason": subscription.deleted_reason,
        },
    )


def _create_user(
    db: Session,
    email: str,
    password_hash: str | None = None,
    google_sub: str | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        google_sub=google_sub,
        role=Role.user,
        last_connection=utcnow(),
    )
    db.add(user)
    db.flush()
    db.add(Subscription(user_id=user.id, plan=Plan.free))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AuthError(409, "An account with this email already exists.") from exc
    return _load_user(db, user.id)


def _issue_tokens(db: Session, user: User) -> IssuedSession:
    settings = get_settings()
    raw_refresh = new_refresh_token()
    stored = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
    )
    db.add(stored)
    db.commit()
    return IssuedSession(
        access_token=create_access_token(user.id),
        refresh_token=raw_refresh,
        user=_load_user(db, user.id),
    )


def _get_valid_refresh_token(db: Session, raw_token: str) -> RefreshToken:
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if stored is None or stored.revoked or _as_utc(stored.expires_at) <= utcnow():
        raise AuthError(401, "Refresh token is not valid.")
    return stored


def _find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def _load_user(db: Session, user_id) -> User:
    user = db.scalar(
        select(User).options(joinedload(User.subscription)).where(User.id == user_id)
    )
    if user is None:
        raise AuthError(401, "Not authenticated.")
    return user


def _reject_if_closed(user: User) -> None:
    if user.deleted_at is not None:
        raise AuthError(403, "This account is closed.")


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=utcnow().tzinfo)
    return value
