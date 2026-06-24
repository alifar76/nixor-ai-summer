"""Central configuration, loaded from environment variables.

Nothing secret is hardcoded here — every credential comes from the environment
(see .env.example). This mirrors the project's hard constraint: no secrets in code.
"""

from __future__ import annotations

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
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_api_version: str = "2024-10-21"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
