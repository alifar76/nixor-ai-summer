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


class StudentSandbox(SQLModel, table=True):
    """Per-student Azure resources provisioned for the course (Sessions 1 & 3 deploy target).

    The instructor (or provision_student.py) populates these after provisioning.
    Students read them via GET /api/workspace/sandbox to get their pre-filled deploy command.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True, foreign_key="user.id")
    # Azure resource group and App Service Web App created for this student.
    resource_group: str = ""               # e.g. rg-nixor-team01
    webapp_name: str = ""                  # e.g. nixor-team01-app
    location: str = "eastus"
    # The deployed app's public URL (set once the first deploy succeeds).
    deploy_url: str = ""
    # The student's Azure OpenAI endpoint/key (scoped to their RG, if provisioned).
    # If blank, the platform's shared credentials are used for local streamlit runs.
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    status: str = "pending"               # pending | ready | deployed | error
    # Cluster node assignment (Session 3 VM-cluster deploy path).
    # node_index is the 0-based index into CLUSTER_NODE_URLS; -1 = not yet assigned.
    # cluster_port is the host port on that node where the student's container listens.
    cluster_node_index: int = Field(default=-1)
    cluster_port: int = Field(default=0)
    updated_at: datetime = Field(default_factory=_utcnow)
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
    # Optional UI-selected model id from /api/ai/models.
    model_id: str = ""


class AIModelInfo(BaseModel):
    id: str
    provider: str
    label: str
    model: str
    input: list[str] = []
    output: list[str] = []
    chat_eligible: bool = False


class SandboxInfo(BaseModel):
    """Public view of a student's sandbox — safe to return to the student."""
    resource_group: str
    webapp_name: str
    location: str
    deploy_url: str
    status: str
    has_own_ai_credentials: bool
    # Cluster deploy info (populated once assigned)
    cluster_node_index: int = -1
    cluster_port: int = 0


class SandboxUpdate(BaseModel):
    """Instructor-only: set or update per-student sandbox info."""
    resource_group: str = ""
    webapp_name: str = ""
    location: str = "eastus"
    deploy_url: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    status: str = "ready"


TokenResponse.model_rebuild()
