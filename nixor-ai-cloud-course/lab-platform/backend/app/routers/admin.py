"""Instructor dashboard: roster, progress, and sandbox teardown."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import get_current_instructor
from ..course import all_step_ids
from ..db import get_session
from ..models import Progress, User, Workspace
from ..workspaces import manager

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/students")
def students(
    _: User = Depends(get_current_instructor), session: Session = Depends(get_session)
):
    total_steps = len(all_step_ids())
    users = session.exec(select(User)).all()
    out = []
    for u in users:
        done = len(session.exec(select(Progress).where(Progress.user_id == u.id)).all())
        ws = session.exec(select(Workspace).where(Workspace.user_id == u.id)).first()
        out.append(
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "is_instructor": u.is_instructor,
                "completed_steps": done,
                "total_steps": total_steps,
                "workspace_status": manager.status(u.id),
                "created_at": u.created_at.isoformat(),
            }
        )
    return {"students": out}


@router.post("/students/{user_id}/stop")
def stop_student(user_id: int, _: User = Depends(get_current_instructor)):
    manager.stop_workspace(user_id)
    return {"ok": True}


@router.post("/teardown")
def teardown_all(
    delete_data: bool = False,
    _: User = Depends(get_current_instructor),
    session: Session = Depends(get_session),
):
    """Stop (and optionally delete) every student's sandbox. Frees host resources
    between cohorts."""
    users = session.exec(select(User)).all()
    count = 0
    for u in users:
        manager.delete_workspace(u.id, delete_data=delete_data)
        count += 1
    return {"torn_down": count, "data_deleted": delete_data}
