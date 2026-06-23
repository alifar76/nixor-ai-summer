"""Per-student workspace orchestration.

`manager` is the process-wide WorkspaceManager. Today it's the Docker driver
(one container per student on the host's Docker daemon). The abstraction lets a
future Kubernetes driver drop in without touching the routers.
"""

from __future__ import annotations

from ..config import settings
from .base import WorkspaceInfo, WorkspaceManager
from .local_driver import LocalWorkspaceManager


def _build_manager() -> WorkspaceManager:
    driver = settings.workspace_driver.strip().lower()
    if driver == "docker":
        from .docker_driver import DockerWorkspaceManager

        return DockerWorkspaceManager()
    return LocalWorkspaceManager()


manager: WorkspaceManager = _build_manager()

__all__ = ["manager", "WorkspaceInfo", "WorkspaceManager"]
