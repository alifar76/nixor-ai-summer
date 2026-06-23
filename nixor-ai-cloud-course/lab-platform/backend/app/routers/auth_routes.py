"""Signup / login / current-user endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id, email=user.email, name=user.name, is_instructor=user.is_instructor
    )


@router.post("/signup", response_model=TokenResponse)
def signup(body: SignupRequest, session: Session = Depends(get_session)) -> TokenResponse:
    if settings.signup_access_code and body.access_code != settings.signup_access_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access code")

    email = body.email.lower()
    if get_user_by_email(session, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(email=email, name=body.name, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("New signup: %s", email)
    return TokenResponse(access_token=create_access_token(user), user=_public(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = get_user_by_email(session, body.email.lower())
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong email or password"
        )
    return TokenResponse(access_token=create_access_token(user), user=_public(user))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return _public(user)
