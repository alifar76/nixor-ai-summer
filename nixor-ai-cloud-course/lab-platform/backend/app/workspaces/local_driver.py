"""Local filesystem + PTY workspace manager.

This driver is designed for environments like Azure App Service where running a
Docker daemon inside the API process is not practical. Each student gets a
private folder on disk and interactive shell sessions run as child processes.
"""

from __future__ import annotations

import fcntl
import logging
import os
import pathlib
import pty
import shutil
import struct
import termios
import threading
from dataclasses import dataclass
from subprocess import Popen
from typing import Optional

from ..config import settings
from .base import FileNode, WorkspaceInfo, WorkspaceManager

logger = logging.getLogger(__name__)

_IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".cache", ".venv", "venv", ".azure"}
_MAX_FILE_BYTES = 1_000_000


class PtySocket:
    """Socket-like wrapper over a PTY master fd for websocket bridging."""

    def __init__(self, fd: int):
        self._fd = fd

    def recv(self, size: int) -> bytes:
        try:
            return os.read(self._fd, size)
        except OSError:
            return b""

    def sendall(self, data: bytes) -> None:
        if not data:
            return
        os.write(self._fd, data)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


@dataclass
class TerminalSession:
    process: Popen
    socket: PtySocket
    _fd: int

    def resize(self, cols: int, rows: int) -> None:
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            logger.debug("pty resize failed", exc_info=True)

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=1)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        self.socket.close()


class LocalWorkspaceManager(WorkspaceManager):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stopped: set[int] = set()

    @staticmethod
    def _set_tree_owner(root: pathlib.Path, uid: int, gid: int) -> None:
        for dirpath, dirnames, filenames in os.walk(root):
            current = pathlib.Path(dirpath)
            try:
                os.chown(current, uid, gid)
            except OSError:
                logger.debug("chown failed for %s", current, exc_info=True)
            for name in filenames:
                path = current / name
                try:
                    os.chown(path, uid, gid)
                except OSError:
                    logger.debug("chown failed for %s", path, exc_info=True)

    def _sandbox_credentials(self) -> tuple[int, int] | None:
        if not settings.terminal_require_non_root or os.geteuid() != 0:
            return None
        uid = settings.local_sandbox_uid
        gid = settings.local_sandbox_gid
        if uid <= 0 or gid <= 0:
            raise RuntimeError("Invalid sandbox UID/GID. Must be non-zero values.")
        return uid, gid

    @staticmethod
    def _read_process_uid(pid: int) -> Optional[int]:
        status_path = pathlib.Path(f"/proc/{pid}/status")
        if not status_path.exists():
            return None
        try:
            for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.startswith("Uid:"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1])
        except Exception:
            return None
        return None

    @staticmethod
    def _workspace_name(user_id: int) -> str:
        return f"ws-user-{user_id}"

    @staticmethod
    def _volume_name(user_id: int) -> str:
        return f"local-user-{user_id}"

    def _root(self) -> pathlib.Path:
        root = pathlib.Path(settings.local_workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _workspace_dir(self, user_id: int) -> pathlib.Path:
        return self._root() / f"user-{user_id}"

    def _seed_workspace(self, target: pathlib.Path) -> None:
        template = pathlib.Path(settings.local_workspace_template_dir)
        if not template.exists() or not template.is_dir():
            return
        if any(target.iterdir()):
            return
        for item in template.iterdir():
            if item.name.startswith(".") and item.name not in {".env.example", ".gitignore"}:
                continue
            dst = target / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)

    def ensure_workspace(self, user_id: int) -> WorkspaceInfo:
        ws_dir = self._workspace_dir(user_id)
        with self._lock:
            ws_dir.mkdir(parents=True, exist_ok=True)
            self._seed_workspace(ws_dir)
            creds = self._sandbox_credentials()
            if creds is not None:
                uid, gid = creds
                self._set_tree_owner(ws_dir, uid, gid)
            self._stopped.discard(user_id)
        return WorkspaceInfo(
            user_id=user_id,
            container_id=str(ws_dir),
            container_name=self._workspace_name(user_id),
            volume_name=self._volume_name(user_id),
            status="running",
        )

    def stop_workspace(self, user_id: int) -> None:
        self._stopped.add(user_id)

    def delete_workspace(self, user_id: int, *, delete_data: bool = False) -> None:
        self._stopped.add(user_id)
        if delete_data:
            shutil.rmtree(self._workspace_dir(user_id), ignore_errors=True)

    def status(self, user_id: int) -> str:
        if user_id in self._stopped:
            return "stopped"
        if self._workspace_dir(user_id).exists():
            return "running"
        return "none"

    def touch_active(self, user_id: int) -> None:
        return None

    def open_terminal(self, user_id: int, cols: int, rows: int) -> TerminalSession:
        ws = self.ensure_workspace(user_id)
        cwd = pathlib.Path(ws.container_id)
        env = {
            "HOME": str(cwd),
            "PWD": str(cwd),
            "TERM": "xterm-256color",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
        }
        creds = self._sandbox_credentials()

        def _drop_privs() -> None:
            os.setsid()
            if creds is None:
                return
            uid, gid = creds
            os.setgid(gid)
            os.setuid(uid)

        master_fd, slave_fd = pty.openpty()
        process = Popen(
            ["/bin/bash", "--noprofile", "--norc", "-i"],
            cwd=str(cwd),
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=_drop_privs,
        )
        os.close(slave_fd)
        if settings.terminal_require_non_root:
            runtime_uid = self._read_process_uid(process.pid)
            if runtime_uid in {None, 0}:
                process.terminate()
                raise RuntimeError("Terminal sandbox user verification failed (root not allowed).")
        sock = PtySocket(master_fd)
        term = TerminalSession(process=process, socket=sock, _fd=master_fd)
        term.resize(cols, rows)
        return term

    def _safe_path(self, user_id: int, rel_path: str) -> pathlib.Path:
        rel = rel_path.strip().lstrip("/")
        base = self._workspace_dir(user_id).resolve()
        full = (base / rel).resolve()
        if full != base and base not in full.parents:
            raise ValueError("Path escapes workspace root")
        return full

    def list_files(self, user_id: int) -> list[FileNode]:
        self.ensure_workspace(user_id)
        root = self._workspace_dir(user_id)
        nodes: list[FileNode] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            rel_dir = pathlib.Path(dirpath).relative_to(root)
            if str(rel_dir) != ".":
                nodes.append(FileNode(path=str(rel_dir), is_dir=True))
            for name in filenames:
                rel = (pathlib.Path(dirpath) / name).relative_to(root)
                nodes.append(FileNode(path=str(rel), is_dir=False))
        nodes.sort(key=lambda n: (not n.is_dir, n.path))
        return nodes

    def read_file(self, user_id: int, rel_path: str) -> str:
        self.ensure_workspace(user_id)
        path = self._safe_path(user_id, rel_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(rel_path)
        if path.stat().st_size > _MAX_FILE_BYTES:
            raise ValueError("File too large to open in the editor")
        return path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, user_id: int, rel_path: str, content: str) -> None:
        self.ensure_workspace(user_id)
        path = self._safe_path(user_id, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
