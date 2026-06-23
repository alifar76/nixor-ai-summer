#!/usr/bin/env python3
"""
provision_student.py — stand up one student's Azure sandbox, end to end.

Flow (order matters — see CLAUDE.md):
  1. Invite the student as an Entra B2B guest (Microsoft Graph).
  2. Create their resource group (tagged for easy teardown).
  3. Deploy infra/main.bicep into it (Azure OpenAI + free-tier Web App).
  4. Assign them a role scoped ONLY to that resource group (least privilege).
  5. Create a budget on the RG (a backstop alert — it does not stop spend).

This shells out to the `az` CLI for transparency (students can read it). The
backend can import and call `provision_student()`, or run this as a subprocess.

Required environment (see platform/backend/.env.example):
  AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID
  (and an authenticated `az login`, or a service principal via env)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("provision")

BICEP_PATH = Path(__file__).parent / "main.bicep"
# Built-in "Contributor" role. Scoped to the RG only, this lets a student create
# and manage resources in their sandbox and nothing else.
CONTRIBUTOR_ROLE = "b24988ac-6180-42a0-ab88-20f7382dd24c"


def _az(args: list[str], capture: bool = True) -> str:
    """Run an `az` command and return stdout. Raises on failure."""
    log.info("az %s", " ".join(args))
    result = subprocess.run(
        ["az", *args], capture_output=capture, text=True, check=True
    )
    return result.stdout.strip()


def invite_guest(email: str, redirect_url: str) -> str:
    """Invite the student as an Entra guest via Microsoft Graph. Returns their object id.

    NOTE: this needs Graph permission `User.Invite.All` on the service principal.
    Inviting a guest is NOT a plain `az` command — it's a Graph call made through
    `az rest`. This is the single trickiest step; verify it against your tenant.
    """
    body = json.dumps(
        {
            "invitedUserEmailAddress": email,
            "inviteRedirectUrl": redirect_url,
            "sendInvitationMessage": True,
        }
    )
    out = _az(
        [
            "rest",
            "--method", "POST",
            "--url", "https://graph.microsoft.com/v1.0/invitations",
            "--headers", "Content-Type=application/json",
            "--body", body,
        ]
    )
    invited = json.loads(out)
    object_id = invited["invitedUser"]["id"]
    log.info("invited %s as guest (object id %s)", email, object_id)
    return object_id


def create_resource_group(rg_name: str, location: str, team: str, expires: str) -> str:
    """Create the RG if it doesn't exist (idempotent). Returns its resource id."""
    out = _az(
        [
            "group", "create",
            "--name", rg_name,
            "--location", location,
            "--tags", "course=nixor-ai-cloud", f"team={team}", f"expires={expires}",
        ]
    )
    rg_id = json.loads(out)["id"]
    return rg_id


def deploy_infra(rg_name: str, team: str, location: str) -> dict:
    """Deploy main.bicep into the RG. Returns the deployment outputs."""
    out = _az(
        [
            "deployment", "group", "create",
            "--resource-group", rg_name,
            "--template-file", str(BICEP_PATH),
            "--parameters", f"team={team}", f"location={location}",
        ]
    )
    outputs = json.loads(out)["properties"]["outputs"]
    return {k: v["value"] for k, v in outputs.items()}


def assign_rbac(object_id: str, rg_id: str) -> None:
    """Give the student Contributor on their RG only."""
    _az(
        [
            "role", "assignment", "create",
            "--assignee-object-id", object_id,
            "--assignee-principal-type", "User",
            "--role", CONTRIBUTOR_ROLE,
            "--scope", rg_id,
        ]
    )


def create_budget(rg_name: str, amount: int, contact_email: str) -> None:
    """A backstop budget on the RG. Reminder: this ALERTS, it does not STOP spend."""
    try:
        _az(
            [
                "consumption", "budget", "create",
                "--budget-name", f"{rg_name}-budget",
                "--amount", str(amount),
                "--resource-group", rg_name,
                "--time-grain", "Monthly",
                "--category", "Cost",
            ]
        )
    except subprocess.CalledProcessError:
        # The consumption budget CLI shape varies by environment; the backend can
        # fall back to a REST call. Non-fatal for provisioning.
        log.warning("budget creation skipped — verify the budget CLI/REST call")


def provision_student(
    email: str,
    team: str,
    location: str | None = None,
    redirect_url: str | None = None,
    budget_amount: int = 20,
) -> dict:
    location = location or os.environ.get("AZURE_LOCATION", "swedencentral")
    redirect_url = redirect_url or os.environ.get(
        "INVITE_REDIRECT_URL", "https://portal.azure.com"
    )
    rg_name = f"rg-nixor-{team}"

    log.info("=== provisioning sandbox for %s (team %s) ===", email, team)
    object_id = invite_guest(email, redirect_url)
    rg_id = create_resource_group(rg_name, location, team, expires="2026-09-01")
    outputs = deploy_infra(rg_name, team, location)
    assign_rbac(object_id, rg_id)
    create_budget(rg_name, budget_amount, email)

    sandbox = {
        "email": email,
        "team": team,
        "resource_group": rg_name,
        **outputs,
    }
    log.info("=== done ===\n%s", json.dumps(sandbox, indent=2))
    return sandbox


def main() -> None:
    p = argparse.ArgumentParser(description="Provision one student Azure sandbox.")
    p.add_argument("--email", required=True)
    p.add_argument("--team", required=True, help="e.g. team01")
    p.add_argument("--location", default=None)
    args = p.parse_args()
    provision_student(email=args.email, team=args.team, location=args.location)


if __name__ == "__main__":
    main()
