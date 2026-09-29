from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.security import decode_access_token
from src.models.user import Role, User
from src.services.auth import AuthError, get_active_user

ACCESS_COOKIE = "access_token"


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AuthError(401, "Not authenticated.")
    try:
        user_id: UUID = decode_access_token(token)
    except ValueError as exc:
        raise AuthError(401, "Not authenticated.") from exc
    return get_active_user(db, user_id)


def current_admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.admin:
        raise AuthError(404, "Not found.")
    return user
