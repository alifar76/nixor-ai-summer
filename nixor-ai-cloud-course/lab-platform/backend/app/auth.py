"""Email + password auth: hashing, JWT issuance, and request dependencies."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl is informational (used by docs); login is handled by our own route.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.session_signing_key, algorithm=settings.jwt_algorithm)


def _decode_user_id(token: str) -> int:
    try:
        payload = jwt.decode(
            token, settings.session_signing_key, algorithms=[settings.jwt_algorithm]
        )
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = _decode_user_id(token)
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_instructor(user: User = Depends(get_current_user)) -> User:
    if not user.is_instructor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor only")
    return user


def user_from_token_value(token: str, session: Session) -> Optional[User]:
    """Resolve a user from a raw token string (used by the websocket terminal,
    where the token arrives as a query param rather than a header)."""
    try:
        user_id = _decode_user_id(token)
    except HTTPException:
        return None
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(select(User).where(User.email == email.lower())).first()
