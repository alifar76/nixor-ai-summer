"""File tree + read/write for the Monaco editor, backed by the student's container."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user
from ..models import User
from ..workspaces import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


class WriteFileRequest(BaseModel):
    path: str
    content: str


@router.get("/tree")
def tree(user: User = Depends(get_current_user)):
    nodes = manager.list_files(user.id)
    return {"files": [{"path": n.path, "is_dir": n.is_dir} for n in nodes]}


@router.get("")
def read(path: str, user: User = Depends(get_current_user)):
    try:
        return {"path": path, "content": manager.read_file(user.id, path)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("")
def write(body: WriteFileRequest, user: User = Depends(get_current_user)):
    try:
        manager.write_file(user.id, body.path, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}
