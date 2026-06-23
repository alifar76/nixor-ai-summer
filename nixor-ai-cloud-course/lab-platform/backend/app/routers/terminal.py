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

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from ..auth import user_from_token_value
from ..db import engine
from ..workspaces import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["terminal"])


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
