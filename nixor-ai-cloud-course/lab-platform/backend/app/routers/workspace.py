"""Workspace lifecycle + per-student Azure sandbox endpoints."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..auth import get_current_instructor, get_current_user
from ..config import settings
from ..db import get_session
from ..models import SandboxInfo, SandboxUpdate, StudentSandbox, User, Workspace
from ..models import _utcnow
from ..workspaces import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["workspace"])


# --------------------------------------------------------------------------- #
# Container lifecycle
# --------------------------------------------------------------------------- #

def _record(session: Session, user_id: int, info) -> None:
    ws = session.exec(select(Workspace).where(Workspace.user_id == user_id)).first()
    if ws is None:
        ws = Workspace(user_id=user_id)
        session.add(ws)
    ws.container_id = info.container_id
    ws.container_name = info.container_name
    ws.volume_name = info.volume_name
    ws.status = info.status
    ws.last_active_at = _utcnow()
    session.commit()


@router.post("/start")
def start(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Idempotently create + start the student's sandbox. Safe to call on every login."""
    info = manager.ensure_workspace(user.id)
    _record(session, user.id, info)
    return {"status": info.status, "container": info.container_name}


@router.get("/status")
def workspace_status(user: User = Depends(get_current_user)):
    return {"status": manager.status(user.id)}


@router.post("/stop")
def stop(user: User = Depends(get_current_user)):
    manager.stop_workspace(user.id)
    return {"status": "stopped"}


# --------------------------------------------------------------------------- #
# Per-student Azure sandbox info (Sessions 1 & 3: deploy target)
# --------------------------------------------------------------------------- #

def _get_sandbox(session: Session, user_id: int) -> StudentSandbox | None:
    return session.exec(select(StudentSandbox).where(StudentSandbox.user_id == user_id)).first()


def _email_to_slug(email: str) -> str:
    """ali.faruqi@datadam.io → ali-faruqi (max 20 chars, safe for Azure resource names)."""
    local = email.split("@")[0]
    slug = re.sub(r"[^a-z0-9]+", "-", local.lower()).strip("-")
    return slug[:20]


def _ensure_sandbox(session: Session, user: User) -> StudentSandbox:
    """Return the sandbox row, auto-creating it if missing.

    Names are derived deterministically from user.id so re-running is idempotent.
    Cluster node + port are assigned here so every student always lands on the same
    node regardless of when they first log in.
    """
    sb = _get_sandbox(session, user.id)
    if sb is not None:
        return sb

    slug = _email_to_slug(user.email)
    nodes = settings.cluster_nodes
    node_idx = (user.id - 1) % len(nodes) if nodes else -1
    port = settings.cluster_port_base + ((user.id - 1) % 100) if nodes else 0

    sb = StudentSandbox(
        user_id=user.id,
        resource_group=f"rg-nixor-{slug}",
        webapp_name=f"nixor-{slug}-app",
        location=settings.deploy_location,
        status="ready",
        cluster_node_index=node_idx,
        cluster_port=port,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    logger.info(
        "Auto-provisioned sandbox for user %s (%s): node=%d port=%d",
        user.id, user.email, node_idx, port,
    )
    return sb


@router.get("/sandbox", response_model=SandboxInfo)
def get_sandbox(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SandboxInfo:
    """Return this student's Azure resource info, auto-creating the row if needed."""
    sb = _ensure_sandbox(session, user)
    return SandboxInfo(
        resource_group=sb.resource_group,
        webapp_name=sb.webapp_name,
        location=sb.location,
        deploy_url=sb.deploy_url,
        status=sb.status,
        has_own_ai_credentials=bool(sb.azure_openai_endpoint and sb.azure_openai_api_key),
        cluster_node_index=sb.cluster_node_index,
        cluster_port=sb.cluster_port,
    )


@router.get("/deploy-cmd")
def deploy_cmd(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Return the exact az webapp up command pre-filled with this student's resources.

    Students paste this into the terminal (Sessions 1 & 3). The command includes
    startup-command and port so the Streamlit app binds correctly on App Service.
    """
    sb = _get_sandbox(session, user.id)
    if sb is None or not sb.webapp_name or not sb.resource_group:
        return {
            "ready": False,
            "message": "Your Azure sandbox hasn't been set up yet. Ask your instructor.",
            "command": "",
        }

    # Determine which OpenAI endpoint to wire into the deployed app:
    # prefer the student's own scoped credentials, fall back to the platform shared ones.
    endpoint = sb.azure_openai_endpoint or settings.azure_openai_endpoint
    api_key = sb.azure_openai_api_key or settings.azure_openai_api_key
    # Student apps default to a deployable catalog model (gpt-5.3).
    deployment = (
        sb.azure_openai_deployment
        or settings.model_gpt53_deployment
        or settings.azure_openai_deployment
    )
    api_version = settings.azure_openai_api_version

    env_settings = (
        f"AZURE_OPENAI_ENDPOINT={endpoint} "
        f"AZURE_OPENAI_API_KEY={api_key} "
        f"AZURE_OPENAI_DEPLOYMENT={deployment} "
        f"AZURE_OPENAI_API_VERSION={api_version} "
        f"AZURE_FOUNDRY_ENDPOINT={settings.azure_foundry_endpoint} "
        f"AZURE_FOUNDRY_API_KEY={settings.azure_foundry_api_key} "
        f"MODEL_GPT53_DEPLOYMENT={settings.model_gpt53_deployment} "
        f"MODEL_GROK43_DEPLOYMENT={settings.model_grok43_deployment} "
        f"MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT={settings.model_deepseek_v4_pro_deployment} "
        f"MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT={settings.model_mistral_medium_35_deployment} "
        f"AI_MODEL_CATALOG_JSON={settings.ai_model_catalog_json} "
        f"WEBSITES_PORT=8000"
    )

    command = (
        f"az webapp up \\\n"
        f"  --name {sb.webapp_name} \\\n"
        f"  --resource-group {sb.resource_group} \\\n"
        f"  --runtime PYTHON:3.11 \\\n"
        f"  --sku F1 \\\n"
        f"  --startup-file 'python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0'"
    )
    settings_cmd = (
        f"\n\n# Also set App Settings (run once after first deploy):\n"
        f"az webapp config appsettings set \\\n"
        f"  --name {sb.webapp_name} \\\n"
        f"  --resource-group {sb.resource_group} \\\n"
        f"  --settings {env_settings}"
    )

    return {
        "ready": True,
        "webapp_name": sb.webapp_name,
        "resource_group": sb.resource_group,
        "deploy_url": sb.deploy_url or f"https://{sb.webapp_name}.azurewebsites.net",
        "command": command + settings_cmd,
        "message": "Paste this into your terminal from the /workspace directory.",
    }


# --------------------------------------------------------------------------- #
# Instructor-only: provision / update sandbox info for a student
# --------------------------------------------------------------------------- #

@router.put("/sandbox/{user_id}", response_model=SandboxInfo)
def set_sandbox(
    user_id: int,
    body: SandboxUpdate,
    _: User = Depends(get_current_instructor),
    session: Session = Depends(get_session),
) -> SandboxInfo:
    """Set or update the Azure sandbox info for a student (instructor only).

    Call this after running provision_student.py for each student. Idempotent.
    """
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    sb = _get_sandbox(session, user_id)
    if sb is None:
        sb = StudentSandbox(user_id=user_id)
        session.add(sb)

    sb.resource_group = body.resource_group
    sb.webapp_name = body.webapp_name
    sb.location = body.location
    sb.deploy_url = body.deploy_url
    sb.azure_openai_endpoint = body.azure_openai_endpoint
    sb.azure_openai_api_key = body.azure_openai_api_key
    sb.azure_openai_deployment = body.azure_openai_deployment
    sb.status = body.status
    sb.updated_at = _utcnow()
    session.commit()
    session.refresh(sb)

    return SandboxInfo(
        resource_group=sb.resource_group,
        webapp_name=sb.webapp_name,
        location=sb.location,
        deploy_url=sb.deploy_url,
        status=sb.status,
        has_own_ai_credentials=bool(sb.azure_openai_endpoint and sb.azure_openai_api_key),
    )


@router.get("/sandbox/all")
def all_sandboxes(
    _: User = Depends(get_current_instructor),
    session: Session = Depends(get_session),
) -> dict:
    """List every student's sandbox status (instructor dashboard)."""
    rows = session.exec(select(StudentSandbox)).all()
    return {
        "sandboxes": [
            {
                "user_id": r.user_id,
                "resource_group": r.resource_group,
                "webapp_name": r.webapp_name,
                "deploy_url": r.deploy_url,
                "status": r.status,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }
