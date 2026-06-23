"""Loads the 4 course sessions from the markdown files in course-content/.

The frontend renders the raw markdown body; we additionally parse the numbered
list under a "## Steps" heading into discrete, completable steps so each one can
be checked off and saved to a student's progress.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from .config import settings

_NUM_PREFIX = re.compile(r"^\s*(\d+)\.\s+(.*)$")
_FILE_ORDER = re.compile(r"session-(\d+)")
_BOLD_LEAD = re.compile(r"\*\*(.+?)\*\*")


@dataclass
class Step:
    id: str          # "session-1/step-2"
    index: int
    text: str        # short label derived from the numbered item


@dataclass
class CourseSession:
    id: str          # "session-1"
    order: int
    title: str
    markdown: str
    steps: list[Step]


def _slug(path: Path) -> tuple[str, int]:
    m = _FILE_ORDER.search(path.stem)
    order = int(m.group(1)) if m else 999
    return f"session-{order}", order


def _title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _extract_steps(session_id: str, markdown: str) -> list[Step]:
    """Pull numbered items from the '## Steps' section into discrete steps."""
    lines = markdown.splitlines()
    in_steps = False
    steps: list[Step] = []
    idx = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_steps = stripped.lower().startswith("## steps")
            continue
        if not in_steps:
            continue
        m = _NUM_PREFIX.match(line)
        if m:
            idx += 1
            raw = m.group(2).strip()
            # Prefer a bold lead-in as the short label, else first sentence.
            bold = _BOLD_LEAD.search(raw)
            label = bold.group(1) if bold else re.split(r"(?<=[.!?:])\s", raw)[0]
            label = re.sub(r"[`*]", "", label).strip()
            steps.append(Step(id=f"{session_id}/step-{idx}", index=idx, text=label[:120]))
    return steps


@lru_cache
def load_sessions() -> list[CourseSession]:
    content_dir = Path(settings.course_content_dir)
    sessions: list[CourseSession] = []
    for path in sorted(content_dir.glob("session-*.md")):
        markdown = path.read_text(encoding="utf-8")
        sid, order = _slug(path)
        sessions.append(
            CourseSession(
                id=sid,
                order=order,
                title=_title(markdown, path.stem),
                markdown=markdown,
                steps=_extract_steps(sid, markdown),
            )
        )
    sessions.sort(key=lambda s: s.order)
    return sessions


def sessions_as_dicts() -> list[dict]:
    return [asdict(s) for s in load_sessions()]


def all_step_ids() -> set[str]:
    return {step.id for s in load_sessions() for step in s.steps}
