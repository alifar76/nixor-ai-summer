"""Central configuration, loaded from environment variables.

Nothing secret is hardcoded here — every credential comes from the environment
(see .env.example). This mirrors the project's hard constraint: no secrets in code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Repo layout: this file is lab-platform/backend/app/config.py.
# Course assets are bundled under lab-platform/course-content and lab-platform/student-app.
_THIS = Path(__file__).resolve()
_LAB_PLATFORM = _THIS.parents[2]            # .../lab-platform
_COURSE_ROOT = _LAB_PLATFORM


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Auth ---
    # Used to sign session JWTs. MUST be overridden in production.
    session_signing_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    session_ttl_hours: int = 24 * 7
    # Optional shared code required to sign up — gatekeeps to your cohort.
    signup_access_code: str = ""

    # --- Database ---
    # IMPORTANT (security): on Azure App Service the live DB must live on a path the
    # student terminal cannot reach. The interactive terminal runs as an unprivileged
    # sandbox user (uid 1000); we keep the SQLite file in a root-owned 0700 directory on
    # the container's *local* disk (see startup.sh / main.bicep DATABASE_URL), NOT under
    # the world-writable /home mount. That way a malicious `rm -rf /` in the terminal gets
    # permission-denied on the DB and login/signup keep working.
    database_url: str = "sqlite:///./lab_platform.db"
    # Optional persistent backup location (e.g. on the /home Azure Files mount). When set,
    # the app periodically snapshots the live DB here and restores from it on boot, so
    # ordinary restarts/redeploys keep student accounts and progress.
    db_backup_path: str = ""
    db_backup_interval_sec: int = 60

    # --- Course content ---
    course_content_dir: str = str(_COURSE_ROOT / "course-content")

    # --- Azure AI Foundry (the in-app chatbot) ---
    azure_openai_endpoint: str = ""        # https://<resource>.openai.azure.com/  or  https://<resource>.cognitiveservices.azure.com/
    azure_openai_api_key: str = ""
    # Deployment that backs the in-app coding chatbot (the platform tutor). This is a
    # lighter/cheaper model than the deployable catalog below — gpt-5.3.
    azure_openai_deployment: str = "oai-gpt53"
    azure_openai_api_version: str = "2024-10-21"
    # Azure AI Foundry endpoint/key for the broader multi-model catalog available to
    # students in terminal/workspace and deploy targets.
    azure_foundry_endpoint: str = ""
    azure_foundry_api_key: str = ""
    # Deployment names for the 4 approved deployable models.
    model_gpt55_deployment: str = "oai-gpt55"
    model_grok43_deployment: str = "xai-grok43"
    model_deepseek_v4_pro_deployment: str = "ds-v4pro"
    model_mistral_medium_35_deployment: str = "mstr-med35"
    # JSON override for the UI model catalog. If blank, built-in defaults are used.
    # Expected shape: [{"id","provider","label","model","input","output","chat_eligible"}...]
    ai_model_catalog_json: str = ""
    # Model id for the built-in chatbot. The chatbot always falls back to
    # azure_openai_deployment (gpt-5.3) when this id isn't a chat-eligible catalog entry.
    chat_default_model_id: str = "gpt-5.3"

    # --- Server-side deploy (Session 3 one-click "Deploy to Azure") ---
    # The platform deploys each student's app into THEIR resource group on their behalf,
    # using a service principal (the master provisioning credential). Students never need
    # their own `az login`. Scope safety comes from targeting only their RG/web app, which
    # are server-controlled (read from StudentSandbox), never from user input.
    # Leave blank to disable the deploy endpoint (it returns a clear 503).
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    azure_subscription_id: str = ""
    # Runtime/SKU for the student web apps. F1 is free; bump to B1 for demo-day warmth.
    deploy_runtime: str = "PYTHON:3.11"
    deploy_sku: str = "F1"
    # Azure region every student web app + resource group is created in. One source of
    # truth: used both when auto-provisioning the sandbox row and by the deploy endpoint.
    deploy_location: str = "eastus"
    # Hard cap on a single deploy so a hung `az` can't run forever (seconds).
    deploy_timeout_sec: int = 600

    # --- Student app cluster (Session 3 VM-cluster deploy path) ---
    # Comma-separated list of deploy-agent base URLs, one per node, in order.
    # e.g. "http://1.2.3.4:8080,http://5.6.7.8:8080,...". Leave blank to use
    # the legacy `az webapp up` path instead.
    cluster_node_urls: str = ""
    # Shared secret for the deploy-agent REST API. Must match AGENT_SECRET on each node.
    cluster_agent_secret: str = ""
    # Host ports reserved for student containers on cluster nodes.
    cluster_port_base: int = 9000   # user_id % 100 is added to this

    @property
    def cluster_nodes(self) -> list[str]:
        """Parsed list of cluster node base URLs."""
        return [u.strip() for u in self.cluster_node_urls.split(",") if u.strip()]

    # --- Per-student workspace containers ---
    workspace_driver: str = "local"        # local | docker
    workspace_image: str = "nixor-workspace:latest"
    workspace_cpus: float = 1.0            # CPU quota per student container
    workspace_memory_mb: int = 1024        # memory cap per student container
    workspace_network: str = "bridge"      # students need internet (pip, az). Use a custom net to isolate students from each other.
    workspace_home: str = "/home/student"  # where the persistent volume mounts
    workspace_idle_timeout_min: int = 120  # stop idle containers to save resources
    docker_host: str = ""                  # empty => default (unix socket / DOCKER_HOST)
    local_workspace_root: str = str(_LAB_PLATFORM / ".workspace-data")
    local_workspace_template_dir: str = str(_COURSE_ROOT / "student-app")
    terminal_require_non_root: bool = True
    local_sandbox_uid: int = 1000
    local_sandbox_gid: int = 1000
    # Terminal filesystem isolation. The interactive shell is confined to a chroot +
    # bind-mount jail in a private mount namespace: system dirs (/usr, /bin, /lib, ...)
    # are mounted read-only and only the student's own workspace is writable, so a
    # destructive command like `rm -rf /` cannot touch system binaries, the DB, the app,
    # or other students. Modes:
    #   "preferred" (default) - use the jail when the kernel/host allows it; if the
    #                           required syscalls are blocked, fall back to an unjailed
    #                           shell (guard-only) so the terminal still works.
    #   "required"            - jail or nothing: refuse to open a terminal if the jail
    #                           cannot be built (fail closed, maximum safety).
    #   "off"                 - no jail (legacy behaviour).
    terminal_isolation: str = "preferred"
    # Mount point used to assemble each session's jail (ephemeral tmpfs per session).
    terminal_jail_root: str = "/var/lib/nixor-lab/jail"
    # Path the workspace is mounted at inside the jail (becomes HOME / cwd).
    terminal_jail_home: str = "/workspace"
    terminal_block_dangerous_commands: bool = True
    # Regex families for obviously destructive / system-level commands. Note these are a
    # *deterrent* layer only: recursive `rm` on absolute paths is handled more precisely in
    # terminal.py, and the real safety guarantee is filesystem reach (DB off /home,
    # workspace re-seeded). Patterns are matched case-insensitively against each command
    # segment, with quotes stripped so `bash -c 'rm -rf /'` payloads are still caught.
    terminal_block_patterns: str = (
        r"(^|\s)rm\s+(-\S+\s+)*--no-preserve-root(\s|$)|"
        r"(^|\s)rm\s+-\S*r\S*\s+/(\s|$)|"
        r"(^|\s)(mkfs(\.\w+)?|fdisk|sfdisk|wipefs|blkdiscard)(\s|$)|"
        r"(^|\s)dd\s+\S*.*\bof=/dev/[a-z]|"
        r"(^|\s)(chmod|chown)\s+\S*r\S*\s+\S*\s*/(\s|$)|"
        r"(^|\s)(shutdown|reboot|poweroff|halt)(\s|$)|"
        r"(^|\s)init\s+[06](\s|$)|"
        r">\s*/dev/(sd|nvme|vd|hd|mmcblk)|"
        r":\(\)\s*\{\s*:\|:\s*&\s*\};:"
    )

    # --- CORS / frontend ---
    # Comma-separated list of allowed origins. "*" for dev only.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ai_models(self) -> list[dict[str, object]]:
        default_models = [
            {
                "id": "gpt-5.5",
                "provider": "azure_openai",
                "label": "GPT-5.5",
                "model": self.model_gpt55_deployment or "oai-gpt55",
                "input": ["text", "image"],
                "output": ["text"],
                "chat_eligible": False,
            },
            {
                "id": "grok-4.3",
                "provider": "xai",
                "label": "Grok-4.3",
                "model": self.model_grok43_deployment,
                "input": ["text", "image"],
                "output": ["text"],
                "chat_eligible": False,
            },
            {
                "id": "DeepSeek-V4-Pro",
                "provider": "deepseek",
                "label": "DeepSeek-V4-Pro",
                "model": self.model_deepseek_v4_pro_deployment,
                "input": ["text", "image"],
                "output": ["text"],
                "chat_eligible": False,
            },
            {
                "id": "mistral-medium-3-5",
                "provider": "mistral",
                "label": "mistral-medium-3-5",
                "model": self.model_mistral_medium_35_deployment,
                "input": ["text", "image"],
                "output": ["text"],
                "chat_eligible": False,
            },
        ]
        if not self.ai_model_catalog_json.strip():
            return default_models
        try:
            parsed = json.loads(self.ai_model_catalog_json)
        except json.JSONDecodeError:
            return default_models
        if not isinstance(parsed, list):
            return default_models
        safe: list[dict[str, object]] = []
        for row in parsed:
            if not isinstance(row, dict):
                continue
            if not row.get("id") or not row.get("provider") or not row.get("label"):
                continue
            safe.append(
                {
                    "id": str(row["id"]),
                    "provider": str(row["provider"]),
                    "label": str(row["label"]),
                    "model": str(row.get("model", "")),
                    "input": list(row.get("input", [])),
                    "output": list(row.get("output", [])),
                    "chat_eligible": bool(row.get("chat_eligible", False)),
                }
            )
        return safe or default_models


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
