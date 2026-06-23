"""Abstract workspace manager interface.

A workspace is one isolated Linux sandbox per student. The current implementation
is Docker-backed (docker_driver.py); the interface is kept driver-agnostic so a
Kubernetes-backed driver can replace it for larger cohorts without API changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WorkspaceInfo:
    user_id: int
    container_id: str
    container_name: str
    volume_name: str
    status: str  # starting | running | stopped | error


@dataclass
class FileNode:
    path: str            # relative to the workspace home
    is_dir: bool


class WorkspaceManager(ABC):
    @abstractmethod
    def ensure_workspace(self, user_id: int) -> WorkspaceInfo:
        """Create (if needed) and start the student's sandbox. Idempotent."""

    @abstractmethod
    def stop_workspace(self, user_id: int) -> None:
        ...

    @abstractmethod
    def delete_workspace(self, user_id: int, *, delete_data: bool = False) -> None:
        ...

    @abstractmethod
    def status(self, user_id: int) -> str:
        ...

    @abstractmethod
    def open_terminal(self, user_id: int, cols: int, rows: int):
        """Return an object exposing a raw socket to a PTY running a shell in
        the student's container. Caller bridges it to a websocket."""

    @abstractmethod
    def list_files(self, user_id: int) -> list[FileNode]:
        ...

    @abstractmethod
    def read_file(self, user_id: int, rel_path: str) -> str:
        ...

    @abstractmethod
    def write_file(self, user_id: int, rel_path: str, content: str) -> None:
        ...

    @abstractmethod
    def touch_active(self, user_id: int) -> None:
        """Mark the workspace as recently used (for idle reaping)."""
