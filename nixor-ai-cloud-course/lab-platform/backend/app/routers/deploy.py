"""Server-side one-click deploy (Session 3).

The platform deploys each student's app into THEIR Azure resource group on their
behalf, using a service principal — students never run `az login` or touch Azure
auth. The target web app / resource group are read from StudentSandbox (server
state), never from the request body, so a student can only ever deploy into their
own assigned sandbox.

Output from `az` is streamed to the browser as Server-Sent Events so the deploy
feels live (like the chat panel).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..auth import get_current_user
from ..config import settings
from ..db import get_session
from ..models import StudentSandbox, User
from ..models import _utcnow
from ..workspaces import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["deploy"])


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _deploy_configured() -> bool:
    return all(
        [
            settings.azure_client_id,
            settings.azure_client_secret,
            settings.azure_tenant_id,
            settings.azure_subscription_id,
        ]
    )


async def _stream_cmd(args: list[str], cwd: str, env: dict) -> "asyncio.subprocess.Process":
    """Start an az subprocess with stdout+stderr merged. Caller streams .stdout."""
    return await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


@router.post("/deploy")
async def deploy(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Deploy the student's current workspace to their Azure Web App and stream logs.

    Steps (all server-side, using the platform service principal):
      1. az login --service-principal  (scoped account set to the subscription)
      2. az webapp up   — zip+deploy the student's app into their resource group
      3. az webapp config set --startup-file  — correct Streamlit start command
      4. az webapp config appsettings set  — wire AZURE_OPENAI_* + WEBSITES_PORT
      5. persist deploy_url + status on StudentSandbox
    """
    sandbox = session.exec(
        select(StudentSandbox).where(StudentSandbox.user_id == user.id)
    ).first()

    # Resolve workspace path up front (also ensures it exists).
    get_path = getattr(manager, "workspace_path", None)
    workspace_dir = get_path(user.id) if callable(get_path) else None

    async def event_stream():
        # --- Pre-flight checks (fail fast with a clear message) ---
        if not _deploy_configured():
            yield _sse({"error": "Deploy is not configured on this platform. "
                                 "Set AZURE_CLIENT_ID/SECRET/TENANT/SUBSCRIPTION."})
            yield _sse({"done": True, "ok": False})
            return
        if shutil.which("az") is None:
            yield _sse({"error": "The Azure CLI is not installed in this image."})
            yield _sse({"done": True, "ok": False})
            return
        if sandbox is None or not sandbox.webapp_name or not sandbox.resource_group:
            yield _sse({"error": "Your Azure sandbox isn't set up yet. Ask your instructor."})
            yield _sse({"done": True, "ok": False})
            return
        if not workspace_dir or not os.path.isdir(workspace_dir):
            yield _sse({"error": "Your workspace could not be found on the server."})
            yield _sse({"done": True, "ok": False})
            return

        webapp = sandbox.webapp_name
        rg = sandbox.resource_group
        location = sandbox.location or "eastus"

        # az needs a writable config dir; keep it off the student's workspace.
        az_env = {
            **os.environ,
            "AZURE_CONFIG_DIR": f"/tmp/azcli-{user.id}",
            "AZURE_CORE_NO_COLOR": "1",
            "AZURE_CORE_ONLY_SHOW_ERRORS": "false",
        }

        # Endpoint/key to wire into the deployed app (student's own, else platform shared).
        endpoint = sandbox.azure_openai_endpoint or settings.azure_openai_endpoint
        api_key = sandbox.azure_openai_api_key or settings.azure_openai_api_key
        deployment = sandbox.azure_openai_deployment or settings.azure_openai_deployment
        api_version = settings.azure_openai_api_version
        startup = ("python -m streamlit run app.py "
                   "--server.port 8000 --server.address 0.0.0.0")

        # Step list — each is (human label, az args). Secrets are passed as args to az
        # but never echoed back to the browser (we print the label, not the command).
        steps: list[tuple[str, list[str]]] = [
            ("Signing in to Azure", [
                "az", "login", "--service-principal",
                "--username", settings.azure_client_id,
                "--password", settings.azure_client_secret,
                "--tenant", settings.azure_tenant_id,
                "--allow-no-subscriptions",
            ]),
            ("Selecting subscription", [
                "az", "account", "set",
                "--subscription", settings.azure_subscription_id,
            ]),
            (f"Deploying your app to {webapp} (this can take a few minutes)", [
                "az", "webapp", "up",
                "--name", webapp,
                "--resource-group", rg,
                "--location", location,
                "--runtime", settings.deploy_runtime,
                "--sku", settings.deploy_sku,
            ]),
            ("Setting the Streamlit start command", [
                "az", "webapp", "config", "set",
                "--name", webapp, "--resource-group", rg,
                "--startup-file", startup,
            ]),
            ("Applying app settings (AI keys, port)", [
                "az", "webapp", "config", "appsettings", "set",
                "--name", webapp, "--resource-group", rg,
                "--settings",
                f"AZURE_OPENAI_ENDPOINT={endpoint}",
                f"AZURE_OPENAI_API_KEY={api_key}",
                f"AZURE_OPENAI_DEPLOYMENT={deployment}",
                f"AZURE_OPENAI_API_VERSION={api_version}",
                "WEBSITES_PORT=8000",
            ]),
        ]

        for label, args in steps:
            yield _sse({"step": label})
            logger.info("Deploy (user %s): %s", user.id, label)
            try:
                proc = await _stream_cmd(args, cwd=workspace_dir, env=az_env)
            except OSError as exc:
                yield _sse({"error": f"Could not start az: {exc}"})
                yield _sse({"done": True, "ok": False})
                return

            try:
                assert proc.stdout is not None
                while True:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=settings.deploy_timeout_sec
                    )
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").rstrip()
                    if line:
                        yield _sse({"log": line})
                await proc.wait()
            except asyncio.TimeoutError:
                proc.kill()
                yield _sse({"error": f"Step timed out: {label}"})
                yield _sse({"done": True, "ok": False})
                return

            if proc.returncode != 0:
                yield _sse({"error": f"Step failed ({label}). See the log above."})
                yield _sse({"done": True, "ok": False})
                return

        # --- Success: persist the live URL + status ---
        url = sandbox.deploy_url or f"https://{webapp}.azurewebsites.net"
        sandbox.deploy_url = url
        sandbox.status = "deployed"
        sandbox.updated_at = _utcnow()
        session.add(sandbox)
        session.commit()

        yield _sse({"step": "Done! Your app is live."})
        yield _sse({"url": url})
        yield _sse({"done": True, "ok": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
