"""Course content + per-student progress endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, delete, select

from ..auth import get_current_user
from ..course import all_step_ids, sessions_as_dicts
from ..db import get_session
from ..models import Progress, ProgressUpdate, User

router = APIRouter(prefix="/api", tags=["course"])


@router.get("/course")
def get_course():
    return {"sessions": sessions_as_dicts()}


@router.get("/progress")
def get_progress(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Progress).where(Progress.user_id == user.id)).all()
    return {"completed": sorted(r.step_id for r in rows)}


@router.post("/progress")
def set_progress(
    body: ProgressUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if body.step_id not in all_step_ids():
        raise HTTPException(status_code=404, detail="Unknown step")

    existing = session.exec(
        select(Progress).where(
            Progress.user_id == user.id, Progress.step_id == body.step_id
        )
    ).first()

    if body.completed and existing is None:
        session.add(Progress(user_id=user.id, step_id=body.step_id))
        session.commit()
    elif not body.completed and existing is not None:
        session.exec(
            delete(Progress).where(
                Progress.user_id == user.id, Progress.step_id == body.step_id
            )
        )
        session.commit()

    rows = session.exec(select(Progress).where(Progress.user_id == user.id)).all()
    return {"completed": sorted(r.step_id for r in rows)}
