"""Workspace lifecycle endpoints (the per-student sandbox container)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import get_current_user
from ..db import get_session
from ..models import User, Workspace
from ..models import _utcnow
from ..workspaces import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["workspace"])


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
