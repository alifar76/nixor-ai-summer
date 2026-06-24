"""Websocket PTY: bridges xterm.js in the browser to a bash shell running inside
the student's own container.

Protocol
  server -> client : binary frames = raw PTY output bytes (xterm writes them directly)
  client -> server : text frames = JSON control messages
      {"type": "input",  "data": "<keystrokes>"}
      {"type": "resize", "cols": <int>, "rows": <int>}

Auth: the JWT is passed as the `token` query parameter (browsers can't set
Authorization headers on websocket connects).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from ..auth import user_from_token_value
from ..config import settings
from ..db import engine
from ..workspaces import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["terminal"])
_BLOCK_RE = re.compile(settings.terminal_block_patterns, re.IGNORECASE)


class _CommandGuard:
    def __init__(self) -> None:
        self._buffer = ""

    def _normalize(self, text: str) -> str:
        # Normalize line for matching while keeping enough fidelity for regexes.
        cleaned = "".join(ch for ch in text if ch.isprintable() or ch in {"\t", " "})
        return re.sub(r"\s+", " ", cleaned).strip()

    def check(self, raw_input: str) -> tuple[bool, str]:
        blocked = False
        reason = "Blocked dangerous command by platform policy."
        for ch in raw_input:
            if ch in {"\r", "\n"}:
                line = self._normalize(self._buffer)
                if line and _BLOCK_RE.search(line):
                    blocked = True
                self._buffer = ""
                continue
            if ch in {"\b", "\x7f"}:
                self._buffer = self._buffer[:-1]
                continue
            if ch.isprintable() or ch == "\t":
                self._buffer += ch
        return blocked, reason


@router.websocket("/api/terminal")
async def terminal_ws(
    websocket: WebSocket,
    token: str = Query(...),
    cols: int = Query(80),
    rows: int = Query(24),
) -> None:
    # Authenticate from the query-param token.
    with Session(engine) as session:
        user = user_from_token_value(token, session)
    if user is None:
        await websocket.close(code=4401)  # unauthorized
        return

    await websocket.accept()

    loop = asyncio.get_running_loop()
    term = None
    reader_alive = True
    guard = _CommandGuard()

    try:
        term = await loop.run_in_executor(None, manager.open_terminal, user.id, cols, rows)
    except Exception as exc:
        logger.exception("Failed to open terminal for user %s", user.id)
        await websocket.send_bytes(f"\r\n\x1b[31mCould not start your sandbox: {exc}\x1b[0m\r\n".encode())
        await websocket.close(code=1011)
        return

    sock = term.socket

    def reader() -> None:
        """Blocking thread: read PTY output and ship it to the browser."""
        nonlocal reader_alive
        try:
            while reader_alive:
                data = sock.recv(4096)
                if not data:
                    break
                fut = asyncio.run_coroutine_threadsafe(websocket.send_bytes(data), loop)
                fut.result()  # propagate backpressure / errors
        except Exception as exc:
            logger.debug("terminal reader ended for user %s: %s", user.id, exc)
        finally:
            reader_alive = False
            asyncio.run_coroutine_threadsafe(_safe_close(websocket), loop)

    reader_task = loop.run_in_executor(None, reader)

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                payload = {"type": "input", "data": msg}

            mtype = payload.get("type")
            if mtype == "input":
                data = payload.get("data", "")
                if settings.terminal_block_dangerous_commands:
                    is_blocked, reason = guard.check(data)
                    if is_blocked:
                        await websocket.send_bytes(f"\r\n\x1b[31m{reason}\x1b[0m\r\n".encode())
                        continue
                await loop.run_in_executor(None, sock.sendall, data.encode("utf-8"))
            elif mtype == "resize":
                c = int(payload.get("cols", cols))
                r = int(payload.get("rows", rows))
                term.resize(c, r)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("terminal ws loop ended for user %s: %s", user.id, exc)
    finally:
        # Closing the socket unblocks the reader thread's recv() so it can exit.
        reader_alive = False
        if term is not None:
            term.close()


async def _safe_close(websocket: WebSocket) -> None:
    try:
        await websocket.close()
    except Exception:
        pass
