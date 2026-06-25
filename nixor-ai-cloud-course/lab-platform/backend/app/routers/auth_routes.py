"""Signup / login / current-user endpoints."""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from ..auth import (
    create_access_token,
    get_current_user,
    get_user_by_email,
    hash_password,
    verify_password,
)
from ..config import settings
from ..db import get_session
from ..models import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    User,
    UserPublic,
)
from .workspace import _ensure_sandbox

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# bcrypt only uses the first 72 bytes; reject longer so behaviour is predictable and a
# multi-megabyte password can't be used as a cheap hashing DoS.
_MAX_PASSWORD_LEN = 72

# Precomputed once: used to spend equivalent bcrypt time on logins for non-existent users,
# so timing doesn't leak which emails are registered.
_DUMMY_HASH = hash_password("dummy-password-for-constant-time-login")

# Lightweight in-memory rate limiter to blunt credential brute-forcing. Keyed by client IP
# + endpoint; sliding window. In-process only (fine for the single-VM deployment); resets
# on restart. Generous enough that a student fat-fingering their password is never blocked.
_RL_WINDOW_SEC = 300
_RL_MAX_HITS = 10
_rl_lock = threading.Lock()
_rl_hits: dict[str, list[float]] = {}


def _rate_limit(request: Request, bucket: str) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{ip}"
    now = time.monotonic()
    with _rl_lock:
        hits = [t for t in _rl_hits.get(key, []) if now - t < _RL_WINDOW_SEC]
        if len(hits) >= _RL_MAX_HITS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please wait a few minutes and try again.",
            )
        hits.append(now)
        _rl_hits[key] = hits


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id, email=user.email, name=user.name, is_instructor=user.is_instructor
    )


@router.post("/signup", response_model=TokenResponse)
def signup(
    body: SignupRequest, request: Request, session: Session = Depends(get_session)
) -> TokenResponse:
    _rate_limit(request, "signup")
    if settings.signup_access_code and body.access_code != settings.signup_access_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access code")

    email = body.email.lower()
    if get_user_by_email(session, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if len(body.password) > _MAX_PASSWORD_LEN:
        raise HTTPException(
            status_code=400, detail=f"Password must be at most {_MAX_PASSWORD_LEN} characters"
        )

    user = User(email=email, name=body.name, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    _ensure_sandbox(session, user)
    logger.info("New signup: %s", email)
    return TokenResponse(access_token=create_access_token(user), user=_public(user))


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest, request: Request, session: Session = Depends(get_session)
) -> TokenResponse:
    _rate_limit(request, "login")
    user = get_user_by_email(session, body.email.lower())
    if not user or not verify_password(body.password, user.password_hash):
        # Verify against a dummy hash when the user doesn't exist so the response time
        # doesn't reveal whether an email is registered (timing-based user enumeration).
        if not user:
            verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong email or password"
        )
    return TokenResponse(access_token=create_access_token(user), user=_public(user))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return _public(user)
