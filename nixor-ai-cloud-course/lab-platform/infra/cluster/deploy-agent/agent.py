"""Nixor cluster deploy agent.

Runs on each of the 5 cluster VMs (port 8080). Accepts a zipped student workspace
from the platform backend, builds a Docker image, and starts/replaces the student's
container on their assigned port. Streams build+run output line by line so the platform
can forward it to the student's browser as live logs.

Auth: Bearer token checked against AGENT_SECRET env var. Port 8080 should be locked
to the platform VM's IP at the NSG level — the secret is a defence-in-depth layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/var/log/nixor-agent/agent.log"),
    ],
)
logger = logging.getLogger(__name__)

AGENT_SECRET = os.environ.get("AGENT_SECRET", "")
BUILD_ROOT = Path(os.environ.get("BUILD_ROOT", "/opt/nixor-builds"))
# Path to the Dockerfile injected when the student's workspace has none.
STUDENT_DOCKERFILE = Path(__file__).parent / "student.Dockerfile"
NODE_PUBLIC_IP = os.environ.get("NODE_PUBLIC_IP", "")

app = FastAPI(title="Nixor Deploy Agent", docs_url=None, redoc_url=None)


def _check_auth(authorization: str) -> None:
    if not AGENT_SECRET:
        raise HTTPException(status_code=503, detail="Agent secret not configured.")
    if authorization != f"Bearer {AGENT_SECRET}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized.")


async def _run(args: list[str], cwd: str) -> "asyncio.subprocess.Process":
    return await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True, "ip": NODE_PUBLIC_IP}


@app.post("/deploy")
async def deploy(
    file: UploadFile,
    slug: str,
    port: int,
    authorization: str = Header(default=""),
    azure_openai_endpoint: str = Header(default="", alias="x-aoai-endpoint"),
    azure_openai_api_key: str = Header(default="", alias="x-aoai-key"),
    azure_openai_deployment: str = Header(default="", alias="x-aoai-deployment"),
    azure_openai_api_version: str = Header(default="2024-10-21", alias="x-aoai-version"),
    azure_foundry_endpoint: str = Header(default="", alias="x-foundry-endpoint"),
    azure_foundry_api_key: str = Header(default="", alias="x-foundry-key"),
    model_gpt55_deployment: str = Header(default="", alias="x-model-gpt55-deployment"),
    model_grok43_deployment: str = Header(default="", alias="x-model-grok43-deployment"),
    model_deepseek_v4_pro_deployment: str = Header(default="", alias="x-model-deepseek-v4-pro-deployment"),
    model_mistral_medium_35_deployment: str = Header(default="", alias="x-model-mistral-medium-35-deployment"),
    model_catalog_json: str = Header(default="", alias="x-model-catalog-json"),
):
    """Deploy a student's app.

    Accepts a zip of their workspace, builds an image, and starts the container.
    Streams plain-text log lines; the final line is always:
        RESULT: {"ok": true/false, "url": "...", "error": "..."}
    """
    _check_auth(authorization)

    if not (1 <= port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid port.")
    if not slug or "/" in slug:
        raise HTTPException(status_code=400, detail="Invalid slug.")

    # Save the zip and unpack it into a fresh build directory.
    build_dir = BUILD_ROOT / slug
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    zip_path = build_dir / "workspace.zip"
    content = await file.read()
    zip_path.write_bytes(content)

    src_dir = build_dir / "src"
    src_dir.mkdir()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(src_dir)
    zip_path.unlink()

    # Inject a standard Dockerfile if the student's workspace doesn't have one.
    if not (src_dir / "Dockerfile").exists():
        shutil.copy(STUDENT_DOCKERFILE, src_dir / "Dockerfile")

    image_tag = f"student-{slug}:latest"
    container_name = f"student-{slug}"
    url = f"http://{NODE_PUBLIC_IP}:{port}"

    env_pairs = [
        ("AZURE_OPENAI_ENDPOINT", azure_openai_endpoint),
        ("AZURE_OPENAI_API_KEY", azure_openai_api_key),
        ("AZURE_OPENAI_DEPLOYMENT", azure_openai_deployment),
        ("AZURE_OPENAI_API_VERSION", azure_openai_api_version),
        ("AZURE_FOUNDRY_ENDPOINT", azure_foundry_endpoint),
        ("AZURE_FOUNDRY_API_KEY", azure_foundry_api_key),
        ("MODEL_GPT55_DEPLOYMENT", model_gpt55_deployment),
        ("MODEL_GROK43_DEPLOYMENT", model_grok43_deployment),
        ("MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT", model_deepseek_v4_pro_deployment),
        ("MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT", model_mistral_medium_35_deployment),
        ("AI_MODEL_CATALOG_JSON", model_catalog_json),
    ]

    async def stream():
        # Step 1: build
        yield f"▶ Building Docker image for {slug}...\n"
        logger.info("Building %s on port %d", slug, port)
        proc = await _run(["docker", "build", "-t", image_tag, "."], cwd=str(src_dir))
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                yield f"  {line}\n"
        await proc.wait()
        if proc.returncode != 0:
            msg = "Docker build failed. Check the log above."
            logger.error("%s: %s", slug, msg)
            yield f"RESULT: {{\"ok\": false, \"url\": \"\", \"error\": \"{msg}\"}}\n"
            return

        # Step 2: stop + remove old container if running
        yield f"▶ Replacing existing container (if any)...\n"
        for cmd in [
            ["docker", "stop", container_name],
            ["docker", "rm", container_name],
        ]:
            proc = await _run(cmd, cwd=str(src_dir))
            await proc.wait()  # ignore exit code — container may not exist

        # Also free the target port from ANY other container squatting on it
        # (e.g. a leftover test/validation container with a different name). Without
        # this, `docker run -p` below fails or the student keeps seeing a stale app.
        proc = await _run(
            ["docker", "ps", "-aq", "--filter", f"publish={port}"], cwd=str(src_dir)
        )
        assert proc.stdout
        ids_out, _ = await asyncio.gather(proc.stdout.read(), proc.wait())
        stale_ids = [cid for cid in ids_out.decode().split() if cid]
        for cid in stale_ids:
            yield f"  freeing port {port} (removing container {cid[:12]})\n"
            proc = await _run(["docker", "rm", "-f", cid], cwd=str(src_dir))
            await proc.wait()

        # Step 3: run
        yield f"▶ Starting container on port {port}...\n"
        run_args = [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"{port}:8000",
            "--restart", "unless-stopped",
            "--memory", "2g",
            "--cpus", "1.5",
        ]
        for k, v in env_pairs:
            if v:
                run_args += ["-e", f"{k}={v}"]
        run_args.append(image_tag)

        proc = await _run(run_args, cwd=str(src_dir))
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                yield f"  {line}\n"
        await proc.wait()

        if proc.returncode != 0:
            msg = "docker run failed. See log above."
            logger.error("%s: %s", slug, msg)
            yield f"RESULT: {{\"ok\": false, \"url\": \"\", \"error\": \"{msg}\"}}\n"
            return

        logger.info("%s deployed → %s", slug, url)
        yield f"▶ Live at {url}\n"
        yield f"RESULT: {{\"ok\": true, \"url\": \"{url}\", \"error\": \"\"}}\n"

    return StreamingResponse(stream(), media_type="text/plain")


@app.get("/containers")
async def list_containers(authorization: str = Header(default="")) -> dict:
    """List running student containers and their ports (instructor/debug use)."""
    _check_auth(authorization)
    proc = await _run(
        ["docker", "ps", "--filter", "name=student-", "--format",
         "{{.Names}}\t{{.Ports}}\t{{.Status}}"],
        cwd="/tmp",
    )
    assert proc.stdout
    out, _ = await asyncio.gather(proc.stdout.read(), proc.wait())
    rows = [line.split("\t") for line in out.decode().strip().splitlines() if line]
    return {"containers": [{"name": r[0], "ports": r[1], "status": r[2]} for r in rows]}
