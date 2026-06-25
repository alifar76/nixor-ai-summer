"""Server-side one-click deploy (Session 3).

Two deploy paths, selected automatically:

  Cluster path (preferred):  CLUSTER_NODE_URLS is set.
    Zips the student's workspace, POSTs it to the assigned cluster node's deploy-agent,
    and streams the agent's Docker build/run log back to the browser as SSE.
    Fast (~20-30 s), no ARM throttling, no Azure CLI required.

  Legacy path: CLUSTER_NODE_URLS is blank but AZURE_CLIENT_ID etc. are set.
    Runs `az webapp up` server-side (original approach). Kept as fallback.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import zipfile

import httpx
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

_SSE_TIMEOUT = httpx.Timeout(connect=10.0, read=settings.deploy_timeout_sec, write=30.0, pool=5.0)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


# --------------------------------------------------------------------------- #
# Pre-deploy validation: make sure the student actually has an app to ship.
# Without this, an untouched workspace deploys the starter skeleton ("dummy app"),
# which looks like a broken/empty deploy to the student.
# --------------------------------------------------------------------------- #

def _normalize(text: str) -> str:
    """Whitespace-insensitive form for comparing an app to the starter template."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def _template_app_source() -> str | None:
    """The starter app.py the workspace is seeded with, if available."""
    template = os.path.join(settings.local_workspace_template_dir, "app.py")
    try:
        with open(template, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _validate_app(workspace_dir: str) -> str | None:
    """Return a friendly error string if there's nothing real to deploy, else None.

    Rejects three cases:
      1. No app.py at all.
      2. app.py is empty / whitespace only.
      3. app.py is byte-for-byte the unmodified starter template — the student
         hasn't built anything yet, so we'd just be shipping the demo skeleton.
    """
    app_path = os.path.join(workspace_dir, "app.py")
    if not os.path.isfile(app_path):
        return ("No app.py found in your workspace. The server is running, but you "
                "need a functioning app to deploy. Open the editor and build your app "
                "first.")
    try:
        with open(app_path, "r", encoding="utf-8") as fh:
            source = fh.read()
    except OSError as exc:
        return f"Could not read app.py: {exc}"

    if not source.strip():
        return ("Your app.py is empty. The server is running, but you need a "
                "functioning app to deploy. Write your Streamlit app in the editor "
                "first.")

    template = _template_app_source()
    if template is not None and _normalize(source) == _normalize(template):
        return ("Your app is still the starter template — you haven't changed it yet. "
                "The server is ready, but deploy your own app once you've customised it "
                "(start with APP_TITLE and SYSTEM_PROMPT in app.py).")

    return None


# --------------------------------------------------------------------------- #
# Cluster path
# --------------------------------------------------------------------------- #

def _zip_workspace(workspace_dir: str) -> bytes:
    """Zip the student's workspace directory in memory and return the bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(workspace_dir):
            # Skip hidden dirs (e.g. .git) except .streamlit config
            dirs[:] = [d for d in dirs if not d.startswith(".") or d == ".streamlit"]
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, workspace_dir)
                zf.write(full, arcname)
    return buf.getvalue()


async def _deploy_cluster(
    sandbox: StudentSandbox,
    workspace_dir: str,
    user: User,
):
    """Generator: zip workspace, POST to cluster node agent, stream its output as SSE."""
    nodes = settings.cluster_nodes
    if not nodes or sandbox.cluster_node_index < 0:
        yield _sse({"error": "No cluster nodes configured. "
                             "Set CLUSTER_NODE_URLS and redeploy the platform."})
        yield _sse({"done": True, "ok": False})
        return

    if sandbox.cluster_node_index >= len(nodes):
        yield _sse({"error": f"Assigned node index {sandbox.cluster_node_index} "
                             f"is out of range (only {len(nodes)} node(s) configured)."})
        yield _sse({"done": True, "ok": False})
        return

    node_url = nodes[sandbox.cluster_node_index]
    port = sandbox.cluster_port
    slug = sandbox.webapp_name.replace("nixor-", "").replace("-app", "") or f"user{user.id}"

    yield _sse({"step": f"Zipping your workspace..."})
    try:
        zip_bytes = _zip_workspace(workspace_dir)
    except OSError as exc:
        yield _sse({"error": f"Could not zip workspace: {exc}"})
        yield _sse({"done": True, "ok": False})
        return
    yield _sse({"log": f"  {len(zip_bytes) // 1024} KB zipped"})

    # Resolve AI credentials: per-student first, then platform shared. Student apps
    # default to a deployable catalog model (gpt-5.5), not the chatbot's gpt-5.3.
    endpoint = sandbox.azure_openai_endpoint or settings.azure_openai_endpoint
    api_key = sandbox.azure_openai_api_key or settings.azure_openai_api_key
    deployment = (
        sandbox.azure_openai_deployment
        or settings.model_gpt55_deployment
        or settings.azure_openai_deployment
    )
    api_version = settings.azure_openai_api_version
    foundry_endpoint = settings.azure_foundry_endpoint
    foundry_api_key = settings.azure_foundry_api_key

    yield _sse({"step": f"Sending to cluster node {sandbox.cluster_node_index + 1}..."})

    deploy_url_final = ""
    error_msg = ""

    try:
        async with httpx.AsyncClient(timeout=_SSE_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{node_url}/deploy",
                params={"slug": slug, "port": port},
                headers={
                    "Authorization": f"Bearer {settings.cluster_agent_secret}",
                    "x-aoai-endpoint": endpoint,
                    "x-aoai-key": api_key,
                    "x-aoai-deployment": deployment,
                    "x-aoai-version": api_version,
                    "x-foundry-endpoint": foundry_endpoint,
                    "x-foundry-key": foundry_api_key,
                    "x-model-gpt55-deployment": settings.model_gpt55_deployment,
                    "x-model-grok43-deployment": settings.model_grok43_deployment,
                    "x-model-deepseek-v4-pro-deployment": settings.model_deepseek_v4_pro_deployment,
                    "x-model-mistral-medium-35-deployment": settings.model_mistral_medium_35_deployment,
                    "x-model-catalog-json": settings.ai_model_catalog_json,
                },
                files={"file": (f"{slug}.zip", zip_bytes, "application/zip")},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield _sse({"error": f"Agent returned {resp.status_code}: {body.decode()[:200]}"})
                    yield _sse({"done": True, "ok": False})
                    return

                async for raw_line in resp.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("RESULT:"):
                        try:
                            result = json.loads(line[7:].strip())
                            if result.get("ok"):
                                deploy_url_final = result.get("url", "")
                            else:
                                error_msg = result.get("error", "Deploy failed.")
                        except json.JSONDecodeError:
                            error_msg = "Agent returned malformed result line."
                    else:
                        # Forward raw log line to browser
                        yield _sse({"log": line})

    except httpx.ConnectError:
        yield _sse({"error": f"Cannot reach cluster node {sandbox.cluster_node_index + 1} "
                             f"at {node_url}. Is it running?"})
        yield _sse({"done": True, "ok": False})
        return
    except httpx.TimeoutException:
        yield _sse({"error": "Deploy timed out. The build may still finish on the server."})
        yield _sse({"done": True, "ok": False})
        return

    if error_msg:
        yield _sse({"error": error_msg})
        yield _sse({"done": True, "ok": False})
        return

    yield _sse({"step": "Done! Your app is live."})
    yield _sse({"url": deploy_url_final})
    yield _sse({"done": True, "ok": True})
    return


# --------------------------------------------------------------------------- #
# Legacy az-webapp-up path (kept as fallback when cluster not configured)
# --------------------------------------------------------------------------- #

def _az_configured() -> bool:
    return all([
        settings.azure_client_id,
        settings.azure_client_secret,
        settings.azure_tenant_id,
        settings.azure_subscription_id,
    ])


async def _stream_cmd(args: list[str], cwd: str, env: dict):
    return await asyncio.create_subprocess_exec(
        *args, cwd=cwd, env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _deploy_legacy(sandbox: StudentSandbox, workspace_dir: str, user: User):
    import shutil
    if not _az_configured():
        yield _sse({"error": "Deploy is not configured. "
                             "Set AZURE_CLIENT_ID/SECRET/TENANT/SUBSCRIPTION or CLUSTER_NODE_URLS."})
        yield _sse({"done": True, "ok": False})
        return
    if shutil.which("az") is None:
        yield _sse({"error": "The Azure CLI is not installed in this image."})
        yield _sse({"done": True, "ok": False})
        return
    if not sandbox.webapp_name or not sandbox.resource_group:
        yield _sse({"error": "Your Azure sandbox isn't set up yet."})
        yield _sse({"done": True, "ok": False})
        return

    webapp = sandbox.webapp_name
    rg = sandbox.resource_group
    location = sandbox.location or settings.deploy_location
    endpoint = sandbox.azure_openai_endpoint or settings.azure_openai_endpoint
    api_key = sandbox.azure_openai_api_key or settings.azure_openai_api_key
    deployment = sandbox.azure_openai_deployment or settings.azure_openai_deployment
    api_version = settings.azure_openai_api_version
    startup = "python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0"

    az_env = {
        **os.environ,
        "AZURE_CONFIG_DIR": f"/tmp/azcli-{user.id}",
        "AZURE_CORE_NO_COLOR": "1",
        "AZURE_CORE_ONLY_SHOW_ERRORS": "false",
    }

    steps: list[tuple[str, list[str]]] = [
        ("Signing in to Azure", [
            "az", "login", "--service-principal",
            "--username", settings.azure_client_id,
            "--password", settings.azure_client_secret,
            "--tenant", settings.azure_tenant_id,
            "--allow-no-subscriptions",
        ]),
        ("Selecting subscription", [
            "az", "account", "set", "--subscription", settings.azure_subscription_id,
        ]),
        (f"Deploying your app to {webapp}", [
            "az", "webapp", "up",
            "--name", webapp, "--resource-group", rg,
            "--location", location,
            "--runtime", settings.deploy_runtime,
            "--sku", settings.deploy_sku,
        ]),
        ("Setting the Streamlit start command", [
            "az", "webapp", "config", "set",
            "--name", webapp, "--resource-group", rg, "--startup-file", startup,
        ]),
        ("Applying app settings", [
            "az", "webapp", "config", "appsettings", "set",
            "--name", webapp, "--resource-group", rg,
            "--settings",
            f"AZURE_OPENAI_ENDPOINT={endpoint}",
            f"AZURE_OPENAI_API_KEY={api_key}",
            f"AZURE_OPENAI_DEPLOYMENT={deployment}",
            f"AZURE_OPENAI_API_VERSION={api_version}",
            f"AZURE_FOUNDRY_ENDPOINT={settings.azure_foundry_endpoint}",
            f"AZURE_FOUNDRY_API_KEY={settings.azure_foundry_api_key}",
            f"MODEL_GPT55_DEPLOYMENT={settings.model_gpt55_deployment}",
            f"MODEL_GROK43_DEPLOYMENT={settings.model_grok43_deployment}",
            f"MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT={settings.model_deepseek_v4_pro_deployment}",
            f"MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT={settings.model_mistral_medium_35_deployment}",
            f"AI_MODEL_CATALOG_JSON={settings.ai_model_catalog_json}",
            "WEBSITES_PORT=8000",
        ]),
    ]

    for label, args in steps:
        yield _sse({"step": label})
        try:
            proc = await _stream_cmd(args, cwd=workspace_dir, env=az_env)
        except OSError as exc:
            yield _sse({"error": f"Could not start az: {exc}"})
            yield _sse({"done": True, "ok": False})
            return
        assert proc.stdout
        while True:
            try:
                raw = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=settings.deploy_timeout_sec
                )
            except asyncio.TimeoutError:
                proc.kill()
                yield _sse({"error": f"Step timed out: {label}"})
                yield _sse({"done": True, "ok": False})
                return
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                yield _sse({"log": line})
        await proc.wait()
        if proc.returncode != 0:
            yield _sse({"error": f"Step failed: {label}"})
            yield _sse({"done": True, "ok": False})
            return

    url = sandbox.deploy_url or f"https://{webapp}.azurewebsites.net"
    yield _sse({"step": "Done! Your app is live."})
    yield _sse({"url": url})
    yield _sse({"done": True, "ok": True})
    return


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #

@router.post("/deploy")
async def deploy(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    sandbox = session.exec(
        select(StudentSandbox).where(StudentSandbox.user_id == user.id)
    ).first()
    if sandbox is None:
        async def _no_sandbox():
            yield _sse({"error": "Sandbox not found. Try refreshing the page."})
            yield _sse({"done": True, "ok": False})
        return StreamingResponse(_no_sandbox(), media_type="text/event-stream")

    get_path = getattr(manager, "workspace_path", None)
    workspace_dir = get_path(user.id) if callable(get_path) else None
    if not workspace_dir or not os.path.isdir(workspace_dir):
        async def _no_ws():
            yield _sse({"error": "Your workspace could not be found on the server."})
            yield _sse({"done": True, "ok": False})
        return StreamingResponse(_no_ws(), media_type="text/event-stream")

    # Guard: don't deploy an empty workspace or the unmodified starter skeleton.
    app_error = _validate_app(workspace_dir)
    if app_error:
        async def _no_app():
            yield _sse({"error": app_error})
            yield _sse({"done": True, "ok": False})
        return StreamingResponse(_no_app(), media_type="text/event-stream")

    # Choose deploy path
    use_cluster = bool(settings.cluster_nodes)

    async def event_stream():
        deploy_url = ""
        if use_cluster:
            async for chunk in _deploy_cluster(sandbox, workspace_dir, user):
                if isinstance(chunk, str) and '"url":' in chunk:
                    # Extract URL for persistence
                    try:
                        payload = json.loads(chunk.split("data: ", 1)[1])
                        if "url" in payload:
                            deploy_url = payload["url"]
                    except Exception:
                        pass
                yield chunk
        else:
            async for chunk in _deploy_legacy(sandbox, workspace_dir, user):
                yield chunk
                if isinstance(chunk, str) and '"url":' in chunk:
                    try:
                        payload = json.loads(chunk.split("data: ", 1)[1])
                        if "url" in payload:
                            deploy_url = payload["url"]
                    except Exception:
                        pass

        # Persist URL + status on success
        if deploy_url:
            sandbox.deploy_url = deploy_url
            sandbox.status = "deployed"
            sandbox.updated_at = _utcnow()
            session.add(sandbox)
            session.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
