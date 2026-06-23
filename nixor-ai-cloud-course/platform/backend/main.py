"""
platform/backend/main.py — the course website's API.

This is a SKELETON with a working shape and clear TODOs. It exists so the frontend
(which Claude Code will build) has a stable contract to build against, and so the
enrollment → provisioning wiring is sketched in the right place.

Run:  uvicorn main:app --reload
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import EnrollRequest, ProgressUpdate, Sandbox, StudentStatus

# Let the backend import the provisioning logic from infra/.
sys.path.append(str(Path(__file__).resolve().parents[2] / "infra"))
from provision_student import provision_student  # noqa: E402

app = FastAPI(title="Nixor AI + Cloud Course API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: lock to the frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- TEMPORARY in-memory store. Replace with SQLite/Postgres (see CLAUDE.md). ---
STUDENTS: dict[str, StudentStatus] = {}
COURSE_DIR = Path(__file__).resolve().parents[2] / "course-content"


# ---------------------------------------------------------------------------
# Auth (STUB)
# ---------------------------------------------------------------------------
# TODO (Claude Code): magic-link auth. POST email -> email a signed token link ->
# token exchanged for a session. No passwords. For now, enrollment trusts the email.


# ---------------------------------------------------------------------------
# Enrollment + provisioning
# ---------------------------------------------------------------------------
def _provision_in_background(email: str, team: str) -> None:
    """Runs the real Azure provisioning. Updates the student's status as it goes."""
    STUDENTS[email].sandbox_status = "provisioning"
    try:
        result = provision_student(email=email, team=team)
        STUDENTS[email].sandbox = Sandbox(**result)
        STUDENTS[email].sandbox_status = "ready"
    except Exception as exc:  # noqa: BLE001 — surface failures to the dashboard
        STUDENTS[email].sandbox_status = "failed"
        STUDENTS[email].error = str(exc)


@app.post("/api/enroll", response_model=StudentStatus)
def enroll(req: EnrollRequest, background: BackgroundTasks) -> StudentStatus:
    """Enroll a student by email and kick off sandbox provisioning."""
    email = req.email.lower()
    if email not in STUDENTS:
        # Simple team allocation; swap for pair-assignment logic if desired.
        team = f"team{len(STUDENTS) + 1:02d}"
        STUDENTS[email] = StudentStatus(email=email, team=team, sandbox_status="pending")
        background.add_task(_provision_in_background, email, team)
    return STUDENTS[email]


@app.get("/api/students/{email}", response_model=StudentStatus)
def get_status(email: str) -> StudentStatus:
    student = STUDENTS.get(email.lower())
    if not student:
        raise HTTPException(404, "Not enrolled")
    return student


# ---------------------------------------------------------------------------
# Course content + progress
# ---------------------------------------------------------------------------
@app.get("/api/course")
def get_course() -> list[dict]:
    """List the sessions, read from course-content/*.md (source of truth)."""
    sessions = []
    for md in sorted(COURSE_DIR.glob("session-*.md")):
        text = md.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        sessions.append({"id": md.stem, "title": title, "body": text})
    return sessions


@app.post("/api/progress", response_model=StudentStatus)
def update_progress(update: ProgressUpdate) -> StudentStatus:
    student = STUDENTS.get(update.email.lower())
    if not student:
        raise HTTPException(404, "Not enrolled")
    student.completed_steps = sorted(set(student.completed_steps) | {update.step_id})
    return student


# ---------------------------------------------------------------------------
# Instructor (STUB) — TODO: auth-gate these to the instructor only.
# ---------------------------------------------------------------------------
@app.get("/api/admin/students", response_model=list[StudentStatus])
def list_students() -> list[StudentStatus]:
    return list(STUDENTS.values())
