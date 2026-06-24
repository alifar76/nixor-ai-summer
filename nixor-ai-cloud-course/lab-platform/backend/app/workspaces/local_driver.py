"""Local filesystem + PTY workspace manager.

This driver is designed for environments like Azure App Service where running a
Docker daemon inside the API process is not practical. Each student gets a
private folder on disk and interactive shell sessions run as child processes.
"""

from __future__ import annotations

import ctypes
import fcntl
import logging
import os
import pathlib
import pty
import shutil
import struct
import sys
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

# --- Mount-namespace jail primitives -------------------------------------------------- #
# We confine each interactive shell to a chroot built from read-only bind mounts of the
# host's system directories plus a writable bind of the student's own workspace. This runs
# in the forked child (preexec_fn) while still root, before dropping to the sandbox user.
_CLONE_NEWNS = 0x00020000
_MS_RDONLY = 1
_MS_REMOUNT = 32
_MS_BIND = 4096
_MS_REC = 16384
_MS_PRIVATE = 1 << 18

# System directories bind-mounted read-only into every jail. NOTE: /var is deliberately
# excluded so the protected DB dir (/var/lib/nixor-lab) is never exposed inside a jail.
_JAIL_RO_DIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/opt", "/etc")

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


def _c(value: str | None) -> bytes | None:
    return value.encode() if value is not None else None


def _mount(source: str | None, target: str, fstype: str | None, flags: int, data: str | None) -> None:
    if _libc.mount(_c(source), _c(target), _c(fstype), ctypes.c_ulong(flags), _c(data)) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), target)


def _unshare(flags: int) -> None:
    if _libc.unshare(ctypes.c_int(flags)) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def _build_jail(jail_root: str, workspace_dir: str, home: str) -> None:
    """Assemble and chroot into a confined root. Raises OSError if the essential
    namespace/mount syscalls are unavailable (caller decides fallback)."""
    _unshare(_CLONE_NEWNS)
    # Don't propagate our mounts back to the host mount namespace.
    _mount("none", "/", None, _MS_REC | _MS_PRIVATE, None)

    os.makedirs(jail_root, exist_ok=True)
    # Ephemeral, per-session root. Everything not explicitly bound is gone on exit.
    _mount("tmpfs", jail_root, "tmpfs", 0, "mode=0755")

    # Read-only system directories (binaries, libs, python, certs, configs).
    bound_any = False
    for d in _JAIL_RO_DIRS:
        if not os.path.isdir(d):
            continue
        target = jail_root + d
        os.makedirs(target, exist_ok=True)
        _mount(d, target, None, _MS_BIND | _MS_REC, None)
        try:  # best-effort read-only remount
            _mount("none", target, None, _MS_REMOUNT | _MS_BIND | _MS_RDONLY, None)
        except OSError:
            logger.debug("ro remount failed for %s", target, exc_info=True)
        bound_any = True
    if not bound_any:
        raise OSError("no system directories could be bind-mounted into the jail")

    # Device nodes (read-only bind: writes to /dev/null etc. still work; no node create/del).
    dev_target = jail_root + "/dev"
    os.makedirs(dev_target, exist_ok=True)
    try:
        _mount("/dev", dev_target, None, _MS_BIND | _MS_REC, None)
        _mount("none", dev_target, None, _MS_REMOUNT | _MS_BIND | _MS_RDONLY, None)
    except OSError:
        logger.debug("dev bind failed", exc_info=True)

    # /proc (so ps, top, etc. work) — best-effort.
    proc_target = jail_root + "/proc"
    os.makedirs(proc_target, exist_ok=True)
    try:
        _mount("proc", proc_target, "proc", 0, None)
    except OSError:
        logger.debug("proc mount failed", exc_info=True)

    # Writable scratch /tmp.
    tmp_target = jail_root + "/tmp"
    os.makedirs(tmp_target, exist_ok=True)
    try:
        _mount("tmpfs", tmp_target, "tmpfs", 0, "mode=1777")
    except OSError:
        logger.debug("tmp mount failed", exc_info=True)

    # The student's workspace, writable, at HOME. This is the ONLY place a destructive
    # command can actually delete anything.
    ws_target = jail_root + home
    os.makedirs(ws_target, exist_ok=True)
    _mount(workspace_dir, ws_target, None, _MS_BIND, None)

    os.chroot(jail_root)
    os.chdir(home)


def jail_self_test() -> bool:
    """Best-effort probe: can this host create a mount namespace and mount a tmpfs?
    Run in a throwaway child so it never affects the server. Used only for logging."""
    if os.geteuid() != 0:
        return False
    pid = os.fork()
    if pid == 0:  # child
        try:
            _unshare(_CLONE_NEWNS)
            _mount("none", "/", None, _MS_REC | _MS_PRIVATE, None)
            probe = "/tmp/.nixor-jail-probe"
            os.makedirs(probe, exist_ok=True)
            _mount("tmpfs", probe, "tmpfs", 0, "mode=0700")
            os._exit(0)
        except Exception:
            os._exit(1)
    _, status = os.waitpid(pid, 0)
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0



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
        """Restore the starter template into the workspace.

        Per-entry (not all-or-nothing): copy any top-level template file/dir that is
        missing, and leave everything else alone. This means a student who runs
        ``rm -rf /`` (which the jail confines to wiping their own workspace) gets the
        starter files back the next time a terminal opens or the editor refreshes,
        while files they created themselves are preserved.
        """
        template = pathlib.Path(settings.local_workspace_template_dir)
        if not template.exists() or not template.is_dir():
            return
        for item in template.iterdir():
            if item.name.startswith(".") and item.name not in {".env.example", ".gitignore"}:
                continue
            dst = target / item.name
            if dst.exists():
                continue
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
        mode = settings.terminal_isolation.lower().strip()

        can_jail = mode in {"preferred", "required"} and os.geteuid() == 0
        if can_jail:
            try:
                return self._spawn(cwd, cols, rows, jailed=True)
            except Exception as exc:
                logger.warning("Could not start isolated (jailed) terminal for user %s: %s", user_id, exc)
                if mode == "required":
                    raise RuntimeError(
                        "Isolated sandbox is unavailable on this host (TERMINAL_ISOLATION=required)."
                    ) from exc
                logger.warning("Falling back to unjailed terminal for user %s.", user_id)
        return self._spawn(cwd, cols, rows, jailed=False)

    def _spawn(self, cwd: pathlib.Path, cols: int, rows: int, *, jailed: bool) -> TerminalSession:
        creds = self._sandbox_credentials()
        # A jailed shell must never run as root inside the chroot (root could escape it),
        # so force a drop to the sandbox user even if terminal_require_non_root is off.
        if jailed and creds is None:
            if os.geteuid() != 0:
                raise RuntimeError("Jailing requires the API process to run as root.")
            uid, gid = settings.local_sandbox_uid, settings.local_sandbox_gid
            if uid <= 0 or gid <= 0:
                raise RuntimeError("Invalid sandbox UID/GID for jailed terminal.")
            creds = (uid, gid)

        home = settings.terminal_jail_home if jailed else str(cwd)
        env = {
            "HOME": home,
            "PWD": home,
            "TERM": "xterm-256color",
            "PATH": f"{home}/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "PIP_USER": "1",
            "LANG": "C.UTF-8",
        }
        jail_root = settings.terminal_jail_root
        if jailed:
            # Pre-create the jail mount point as root on the host (best-effort).
            try:
                os.makedirs(jail_root, exist_ok=True)
            except OSError:
                logger.debug("could not pre-create jail root %s", jail_root, exc_info=True)

        def _drop_privs() -> None:
            os.setsid()
            if jailed:
                _build_jail(jail_root, str(cwd), home)
            if creds is not None:
                uid, gid = creds
                os.setgid(gid)
                os.setuid(uid)

        master_fd, slave_fd = pty.openpty()
        process: Optional[Popen] = None
        try:
            process = Popen(
                ["/bin/bash", "--noprofile", "--norc", "-i"],
                cwd=None if jailed else str(cwd),  # jailed: chdir happens inside the chroot
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=_drop_privs,
            )
            os.close(slave_fd)
            slave_fd = -1
            if settings.terminal_require_non_root or jailed:
                runtime_uid = self._read_process_uid(process.pid)
                if runtime_uid in {None, 0}:
                    raise RuntimeError("Terminal sandbox user verification failed (root not allowed).")
        except Exception:
            # Clean up so a failed (e.g. jailed) attempt doesn't leak fds before fallback.
            if process is not None and process.poll() is None:
                process.terminate()
            for fd in (slave_fd, master_fd):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            raise
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
