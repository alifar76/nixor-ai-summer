"""Pydantic models = the API contract the frontend builds against."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr


class EnrollRequest(BaseModel):
    email: EmailStr


class ProgressUpdate(BaseModel):
    email: EmailStr
    step_id: str  # e.g. "session-1-step-3"


class Sandbox(BaseModel):
    email: str
    team: str
    resource_group: str
    openAiEndpoint: str | None = None
    webAppName: str | None = None
    webAppUrl: str | None = None
    deploymentName: str | None = None


class StudentStatus(BaseModel):
    email: str
    team: str
    sandbox_status: str = "pending"  # pending | provisioning | ready | failed
    sandbox: Sandbox | None = None
    completed_steps: list[str] = []
    error: str | None = None
