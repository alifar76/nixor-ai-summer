"""Database models (SQLModel) and a few API request/response schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str = ""
    password_hash: str
    is_instructor: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class Progress(SQLModel, table=True):
    """One row per (user, completed step)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    step_id: str = Field(index=True)       # e.g. "session-1/step-3"
    completed_at: datetime = Field(default_factory=_utcnow)


class Workspace(SQLModel, table=True):
    """Tracks the Docker container that backs one student's sandbox."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True, foreign_key="user.id")
    container_id: str = ""
    container_name: str = ""
    volume_name: str = ""
    status: str = "none"                   # none | starting | running | stopped | error
    last_active_at: datetime = Field(default_factory=_utcnow)
    created_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# API schemas
# --------------------------------------------------------------------------- #
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    access_code: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserPublic"


class UserPublic(BaseModel):
    id: int
    email: str
    name: str
    is_instructor: bool


class ProgressUpdate(BaseModel):
    step_id: str
    completed: bool = True


class ChatMessage(BaseModel):
    role: str                              # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    # Optional context the frontend can attach (e.g. the file the student is editing).
    context: str = ""


TokenResponse.model_rebuild()
