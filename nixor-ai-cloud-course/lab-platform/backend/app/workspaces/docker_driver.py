"""Docker-backed workspace manager: one container per student.

Each student gets:
  - a named volume  vol-user-<id>   mounted at the workspace home (persistent files)
  - a container     ws-user-<id>    from the workspace image, CPU/memory capped

The container runs as the non-root `student` user and stays alive with `sleep
infinity`; interactive shells are launched on demand via `docker exec` with a PTY.
All operations are idempotent (check-then-create) per the project's constraints.
"""

from __future__ import annotations

import io
import logging
import os
import posixpath
import tarfile
import threading
from dataclasses import dataclass
from typing import Optional

import docker
from docker.errors import NotFound

from ..config import settings
from .base import FileNode, WorkspaceInfo, WorkspaceManager

logger = logging.getLogger(__name__)

# Directories we never surface in the file tree (noise / huge).
_IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".cache", ".venv", "venv", ".azure"}
_MAX_FILE_BYTES = 1_000_000  # editor guard: don't load files larger than ~1 MB


@dataclass
class TerminalSession:
    """A live PTY attached to a shell inside a student's container."""

    exec_id: str
    socket: object  # raw socket with recv/sendall/fileno
    _api: docker.APIClient

    def resize(self, cols: int, rows: int) -> None:
        try:
            self._api.exec_resize(self.exec_id, height=rows, width=cols)
        except Exception as exc:  # resize is best-effort
            logger.debug("exec_resize failed: %s", exc)

    def close(self) -> None:
        try:
            self.socket.close()
        except Exception:
            pass


def _raw_socket(sock_obj):
    """docker-py returns a wrapped socket from exec_start(socket=True).
    Return the underlying object that supports recv/sendall/fileno."""
    return getattr(sock_obj, "_sock", sock_obj)


class DockerWorkspaceManager(WorkspaceManager):
    def __init__(self) -> None:
        self._client: Optional[docker.DockerClient] = None
        self._lock = threading.Lock()  # serialise create-or-start per process

    # ----- client -----
    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            if settings.docker_host:
                self._client = docker.DockerClient(base_url=settings.docker_host)
            else:
                self._client = docker.from_env()
        return self._client

    # ----- naming -----
    @staticmethod
    def _container_name(user_id: int) -> str:
        return f"ws-user-{user_id}"

    @staticmethod
    def _volume_name(user_id: int) -> str:
        return f"vol-user-{user_id}"

    # ----- lifecycle -----
    def ensure_workspace(self, user_id: int) -> WorkspaceInfo:
        name = self._container_name(user_id)
        volume = self._volume_name(user_id)

        with self._lock:
            # 1. Volume (persistent home). Idempotent.
            try:
                self.client.volumes.get(volume)
            except NotFound:
                self.client.volumes.create(
                    name=volume, labels={"course": "nixor-ai-cloud", "user_id": str(user_id)}
                )

            # 2. Container. Reuse if present.
            try:
                container = self.client.containers.get(name)
                if container.status != "running":
                    container.start()
                container.reload()
                return WorkspaceInfo(user_id, container.id, name, volume, "running")
            except NotFound:
                pass

            # 3. Create fresh.
            container = self.client.containers.run(
                image=settings.workspace_image,
                name=name,
                command=["sleep", "infinity"],
                detach=True,
                tty=True,
                working_dir=settings.workspace_home,
                volumes={volume: {"bind": settings.workspace_home, "mode": "rw"}},
                nano_cpus=int(settings.workspace_cpus * 1e9),
                mem_limit=f"{settings.workspace_memory_mb}m",
                network=settings.workspace_network,
                restart_policy={"Name": "unless-stopped"},
                labels={"course": "nixor-ai-cloud", "user_id": str(user_id)},
                # Drop privileges hardening; students still have full userland.
                cap_drop=["NET_RAW"],
                security_opt=["no-new-privileges"],
            )
            container.reload()
            logger.info("Created workspace container %s for user %s", name, user_id)
            return WorkspaceInfo(user_id, container.id, name, volume, "running")

    def _get_container(self, user_id: int):
        return self.client.containers.get(self._container_name(user_id))

    def stop_workspace(self, user_id: int) -> None:
        try:
            self._get_container(user_id).stop(timeout=5)
        except NotFound:
            pass

    def delete_workspace(self, user_id: int, *, delete_data: bool = False) -> None:
        try:
            self._get_container(user_id).remove(force=True)
        except NotFound:
            pass
        if delete_data:
            try:
                self.client.volumes.get(self._volume_name(user_id)).remove(force=True)
            except NotFound:
                pass

    def status(self, user_id: int) -> str:
        try:
            c = self._get_container(user_id)
            c.reload()
            return c.status  # running | exited | created | ...
        except NotFound:
            return "none"

    def touch_active(self, user_id: int) -> None:
        # The DB row carries last_active_at; nothing to do at the Docker layer.
        return None

    # ----- terminal -----
    def open_terminal(self, user_id: int, cols: int = 80, rows: int = 24) -> TerminalSession:
        self.ensure_workspace(user_id)
        api = self.client.api
        exec_id = api.exec_create(
            self._container_name(user_id),
            cmd=["/bin/bash", "-l"],
            stdin=True,
            tty=True,
            workdir=settings.workspace_home,
            user="student",
            environment={"TERM": "xterm-256color"},
        )["Id"]
        sock_obj = api.exec_start(exec_id, tty=True, stream=False, socket=True, demux=False)
        sock = _raw_socket(sock_obj)
        try:
            sock.setblocking(True)
        except Exception:
            pass
        api.exec_resize(exec_id, height=rows, width=cols)
        return TerminalSession(exec_id=exec_id, socket=sock, _api=api)

    # ----- files -----
    def _exec(self, user_id: int, cmd: list[str], user: str = "student") -> tuple[int, bytes]:
        container = self._get_container(user_id)
        code, output = container.exec_run(cmd, user=user, demux=False)
        return code, output or b""

    @staticmethod
    def _safe_abspath(rel_path: str) -> str:
        home = settings.workspace_home
        rel = rel_path.lstrip("/")
        abspath = posixpath.normpath(posixpath.join(home, rel))
        if abspath != home and not abspath.startswith(home + "/"):
            raise ValueError("Path escapes workspace home")
        return abspath

    def list_files(self, user_id: int) -> list[FileNode]:
        self.ensure_workspace(user_id)
        prune = " -o ".join(f"-name {d}" for d in _IGNORE_DIRS)
        # Print "d <relpath>" for dirs and "f <relpath>" for files, relative to home.
        script = (
            f"cd {settings.workspace_home} && "
            f"find . \\( {prune} \\) -prune -o -printf '%y %P\\n' 2>/dev/null"
        )
        code, out = self._exec(user_id, ["bash", "-lc", script])
        nodes: list[FileNode] = []
        for line in out.decode("utf-8", "replace").splitlines():
            if len(line) < 3 or line[1] != " ":
                continue
            kind, path = line[0], line[2:]
            if not path:
                continue
            nodes.append(FileNode(path=path, is_dir=(kind == "d")))
        nodes.sort(key=lambda n: (not n.is_dir, n.path))
        return nodes

    def read_file(self, user_id: int, rel_path: str) -> str:
        self.ensure_workspace(user_id)
        abspath = self._safe_abspath(rel_path)
        # Guard size before catting.
        code, out = self._exec(user_id, ["bash", "-lc", f"wc -c < '{abspath}' 2>/dev/null"])
        if code == 0:
            try:
                if int(out.decode().strip() or "0") > _MAX_FILE_BYTES:
                    raise ValueError("File too large to open in the editor")
            except ValueError:
                raise
            except Exception:
                pass
        code, out = self._exec(user_id, ["cat", abspath])
        if code != 0:
            raise FileNotFoundError(rel_path)
        return out.decode("utf-8", "replace")

    def write_file(self, user_id: int, rel_path: str, content: str) -> None:
        self.ensure_workspace(user_id)
        abspath = self._safe_abspath(rel_path)
        parent = posixpath.dirname(abspath)
        base = posixpath.basename(abspath)

        # Ensure parent dir exists and is owned by student.
        self._exec(user_id, ["bash", "-lc", f"mkdir -p '{parent}'"])

        # Build a tar with a single file and copy it into the parent dir.
        data = content.encode("utf-8")
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            info = tarfile.TarInfo(name=base)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
        stream.seek(0)

        container = self._get_container(user_id)
        container.put_archive(parent, stream.getvalue())
        # put_archive writes as root; hand ownership back to student.
        self._exec(user_id, ["chown", "student:student", abspath], user="root")
