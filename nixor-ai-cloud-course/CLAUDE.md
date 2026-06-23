# CLAUDE.md — brief for Claude Code

You are extending this repository into a working course platform. Read this fully before
writing code. The human is an AI/ML engineer running this course at Nixor College,
Karachi. Optimize for **a working product students can actually use**, not a demo.

## The goal

A website where an A-level student:
1. Logs in with their email (magic link — no passwords).
2. On first login, a personal Azure sandbox is provisioned automatically for them.
3. Is walked through 4 course sessions step by step, with their progress saved.
4. Never has to think about Azure entitlements, GitHub access, or local setup.

By the end, every student has a custom AI app deployed at a public URL.

## Architecture & where things live

- `course-content/` — source of truth for the 4 sessions (markdown). The frontend renders
  these. Do not hardcode lesson text in the frontend; read from these files / the API.
- `student-app/` — the Streamlit app skeleton students fork, customize, and deploy. Keep
  it beginner-readable; students will read this code.
- `infra/` — Infrastructure-as-Code. `main.bicep` defines exactly what one student's
  resource group contains. `provision_student.py` orchestrates the full provisioning flow.
- `platform/backend/` — FastAPI. Owns enrollment, provisioning triggers, and progress.
- `platform/frontend/` — the student-facing site. See `platform/frontend/README.md` for
  the UX spec. You will build most of this.

## Hard constraints (do not violate)

1. **No secrets in code or git.** Service principal creds, API keys, magic-link signing
   keys all come from environment variables. `.env` is gitignored; keep it that way.
2. **Provisioning order matters:** invite Entra guest → create resource group → deploy
   `main.bicep` → assign RBAC scoped to *that RG only* (least privilege). Never grant
   subscription-wide access to a student.
3. **Cost is architected, not monitored.** Keep Azure OpenAI capacity (TPM) capped low,
   keep hosting on F1, keep the deny-policy in place. If you add a resource, justify its
   cost and default it to the cheapest viable SKU.
4. **Idempotency.** Re-running provisioning for an existing student must not create
   duplicates or error out — check-then-create.
5. **Verify Azure API versions and model/region availability** against the live
   subscription; the apiVersion strings and model versions here are reasonable defaults,
   not guarantees.

## Conventions

- Python: type hints, `ruff`/`black` formatting, no bare excepts. Log, don't print, in
  backend/provisioning code.
- Naming: resource groups `rg-nixor-<team>`, resources `<team>-<service>` (lowercase,
  hyphenated). Tag every resource with `course=nixor-ai-cloud`, `team=<team>`,
  `expires=<date>` for easy teardown.
- Keep the student app dependency list tiny — every extra package is a setup risk.

## Suggested backlog (rough priority order)

1. **Magic-link auth** in the backend (email in → signed token → session). Stub exists.
2. **Wire provisioning to enrollment**: `POST /api/enroll` should run
   `provision_student.py` as a background job and stream status to the frontend.
3. **Persist state**: swap the in-memory store in `backend/` for SQLite (then Postgres).
   Tables: students, sandboxes, progress.
4. **Build the frontend** per `platform/frontend/README.md`: login → provisioning status
   → session walkthrough with completable steps and a saved progress bar.
5. **Embed the deploy step**: in Session 3, give students a one-click / copy-paste
   `az webapp up` flow that targets *their* resource group.
6. **Instructor dashboard**: list students, sandbox status, live spend per team, and a
   "tear down all sandboxes" button that deletes the resource groups.
7. **Deprovisioning**: finish `infra/deprovision_student.py` and expose it to the dashboard.

## Things that are easy to get wrong

- Inviting a guest user requires Microsoft Graph (`/invitations`), not plain `az` — see
  the documented call in `provision_student.py`.
- App Service F1 is free but sleeps and has a daily CPU quota; fine for a class demo. If
  apps need to stay warm for demo day, document switching to B1 temporarily.
- Streamlit on App Service needs the right startup command and port (`WEBSITES_PORT`).
  This is wired in `main.bicep`; preserve it.
