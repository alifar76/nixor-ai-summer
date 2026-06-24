#!/usr/bin/env python3
"""
Nixor AI Lab — Happy-Path Integration Test
==========================================

Tests all 4 course days end-to-end against the running platform.
Run from the lab-platform/ directory:

    python test_happypath.py --url https://20.91.209.250.nip.io

Produces:
  - Console output with pass/fail for every check
  - A structured log file: happypath_<timestamp>.log

Share the log file with your instructor to confirm everything works.

Day 4 app: "Karachi Street Food Guide" — the student customises app.py to
become a chatbot that recommends Karachi street food, explains dishes, and
teaches Urdu ordering phrases. This test edits app.py to that persona via
the Files API, then asks the in-platform chatbot to validate the idea.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Logging setup — both console (INFO) and file (DEBUG with full detail)
# ---------------------------------------------------------------------------
_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
_LOG_FILE = Path(f"happypath_{_TS}.log")

_fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(_fmt)
_file_handler.setLevel(logging.DEBUG)

_con_handler = logging.StreamHandler(sys.stdout)
_con_handler.setFormatter(_fmt)
_con_handler.setLevel(logging.INFO)

log = logging.getLogger("happypath")
log.setLevel(logging.DEBUG)
log.addHandler(_file_handler)
log.addHandler(_con_handler)


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
@dataclass
class Result:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)


_results = Result()


def check(label: str, ok: bool, detail: str = "") -> bool:
    """Record one check. Returns ok so callers can gate follow-up checks."""
    if ok:
        _results.passed += 1
        log.info("  ✅ PASS  %s", label)
    else:
        _results.failed += 1
        log.warning("  ❌ FAIL  %s%s", label, f" — {detail}" if detail else "")
    if detail:
        log.debug("       detail: %s", detail)
    _results.details.append(f"{'PASS' if ok else 'FAIL'}  {label}")
    return ok


def skip(label: str, reason: str) -> None:
    _results.skipped += 1
    log.info("  ⏭  SKIP  %s  (%s)", label, reason)
    _results.details.append(f"SKIP  {label}  ({reason})")


def section(title: str) -> None:
    log.info("")
    log.info("=" * 60)
    log.info("  %s", title)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
class Client:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str = ""
        self.session = requests.Session()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get(self, path: str, **kw) -> requests.Response:
        log.debug("GET  %s%s", self.base, path)
        r = self.session.get(f"{self.base}{path}", headers=self._headers(),
                             timeout=self.timeout, **kw)
        log.debug("     → %s", r.status_code)
        return r

    def post(self, path: str, payload: dict | None = None, **kw) -> requests.Response:
        log.debug("POST %s%s  body=%s", self.base, path,
                  json.dumps(payload)[:200] if payload else "-")
        r = self.session.post(f"{self.base}{path}", headers=self._headers(),
                              json=payload, timeout=self.timeout, **kw)
        log.debug("     → %s  %s", r.status_code, r.text[:300])
        return r

    def put(self, path: str, payload: dict | None = None, **kw) -> requests.Response:
        log.debug("PUT  %s%s", self.base, path)
        r = self.session.put(f"{self.base}{path}", headers=self._headers(),
                             json=payload, timeout=self.timeout, **kw)
        log.debug("     → %s  %s", r.status_code, r.text[:300])
        return r


# ---------------------------------------------------------------------------
# Day 0 — Setup: health, signup, login, workspace, files
# ---------------------------------------------------------------------------
def test_day0(c: Client, email: str, password: str) -> bool:
    section("DAY 0 — Setup for Success")

    # --- platform health ---
    r = c.get("/api/health")
    if not check("Platform /api/health returns 200", r.status_code == 200,
                 r.text[:200]):
        log.error("Platform is unreachable. Aborting all tests.")
        return False
    data = r.json()
    check("Health reports status=ok", data.get("status") == "ok", str(data))

    # --- signup ---
    r = c.post("/api/auth/signup", {"email": email, "password": password,
                                     "name": "Happy Path Tester"})
    if r.status_code == 200:
        check("Signup succeeds (new user)", True)
        c.token = r.json()["access_token"]
    elif r.status_code == 400 and "already" in r.text.lower():
        log.info("  ℹ  User already exists, trying login instead")
        r2 = c.post("/api/auth/login", {"email": email, "password": password})
        if check("Login succeeds (existing user)", r2.status_code == 200, r2.text[:200]):
            c.token = r2.json()["access_token"]
        else:
            log.error("Cannot authenticate. Aborting.")
            return False
    else:
        check("Signup or login succeeds", False, r.text[:300])
        return False

    # --- identity ---
    r = c.get("/api/auth/me")
    check("/api/auth/me returns user", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        me = r.json()
        check("me.email matches", me["email"] == email.lower(), str(me))

    # --- workspace start (provisions /workspace dir) ---
    r = c.post("/api/workspace/start")
    check("Workspace /start returns 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        check("Workspace status is running", r.json().get("status") == "running",
              str(r.json()))

    # --- starter files exist in editor ---
    r = c.get("/api/files/list")
    check("File list returns 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        files_data = r.json()
        paths = [f["path"] for f in files_data.get("files", [])]
        log.debug("Workspace files: %s", paths)
        check("app.py present in workspace", "app.py" in paths, str(paths))
        check("requirements.txt present in workspace",
              "requirements.txt" in paths, str(paths))
        check("README.md present in workspace", "README.md" in paths, str(paths))

    # --- read app.py content ---
    r = c.get("/api/files/read?path=app.py")
    if check("Can read app.py", r.status_code == 200, r.text[:100]):
        content = r.json().get("content", "")
        check("app.py contains APP_TITLE", "APP_TITLE" in content)
        check("app.py contains SYSTEM_PROMPT", "SYSTEM_PROMPT" in content)
        check("app.py contains load_dotenv", "load_dotenv" in content)
        check("app.py imports AzureOpenAI", "AzureOpenAI" in content)

    return True


# ---------------------------------------------------------------------------
# Day 1 — First Deployment: edit app, see session content, progress tracking
# ---------------------------------------------------------------------------
def test_day1(c: Client) -> None:
    section("DAY 1 — Zero to First Live Deployment")

    # --- course content loads ---
    r = c.get("/api/course")
    if check("GET /api/course returns 200", r.status_code == 200, r.text[:200]):
        sessions = r.json().get("sessions", [])
        check("All 5 sessions loaded (0-4)", len(sessions) == 5, f"got {len(sessions)}")
        if sessions:
            ids = [s["id"] for s in sessions]
            log.debug("Session IDs: %s", ids)
            check("session-0 present", "session-0" in ids)
            check("session-1 present", "session-1" in ids)
            check("Each session has steps", all(len(s.get("steps", [])) > 0
                  for s in sessions), str([len(s.get("steps",[])) for s in sessions]))
            # Grab a real step id for progress tests
            step_id = sessions[1]["steps"][0]["id"] if len(sessions) > 1 else None
        else:
            step_id = None

    # --- edit APP_TITLE via files API (simulating Day 1 task 2) ---
    r = c.get("/api/files/read?path=app.py")
    if r.status_code == 200:
        original = r.json()["content"]
        edited = original.replace(
            'APP_TITLE = "My AI App"',
            'APP_TITLE = "My Nixor AI App"',
        )
        r2 = c.post("/api/files/write", {"path": "app.py", "content": edited})
        if check("Edit APP_TITLE via files API", r2.status_code == 200, r2.text[:200]):
            # Verify the change persisted
            r3 = c.get("/api/files/read?path=app.py")
            if r3.status_code == 200:
                check("Edit persisted on read-back",
                      "My Nixor AI App" in r3.json()["content"])

    # --- progress tracking ---
    r = c.get("/api/progress")
    check("GET /api/progress returns 200", r.status_code == 200, r.text[:200])

    if step_id:
        r = c.post("/api/progress", {"step_id": step_id, "completed": True})
        if check(f"Mark step {step_id} complete", r.status_code == 200, r.text[:200]):
            completed = r.json().get("completed", [])
            check("Step appears in completed list", step_id in completed, str(completed))

        # Unmark it so re-runs stay idempotent
        r = c.post("/api/progress", {"step_id": step_id, "completed": False})
        check("Unmark step (idempotency)", r.status_code == 200, r.text[:200])

    # --- sandbox info (pre-filled deploy command) ---
    r = c.get("/api/workspace/sandbox")
    check("GET /api/workspace/sandbox returns 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        sb = r.json()
        log.debug("Sandbox info: %s", sb)
        check("sandbox.status field present", "status" in sb)

    r = c.get("/api/workspace/deploy-cmd")
    check("GET /api/workspace/deploy-cmd returns 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        dc = r.json()
        check("deploy-cmd has 'ready' field", "ready" in dc)
        log.debug("Deploy cmd response: %s", dc)


# ---------------------------------------------------------------------------
# Day 2 — Build Core Product Skills: deeper edit, chatbot as pair programmer
# ---------------------------------------------------------------------------
def test_day2(c: Client) -> None:
    section("DAY 2 — Build Core Product Skills")

    # --- rewrite SYSTEM_PROMPT (simulating Day 2 task 2) ---
    r = c.get("/api/files/read?path=app.py")
    if r.status_code == 200:
        content = r.json()["content"]
        new_prompt = (
            '"You are a helpful study buddy for A-level Computer Science students in Karachi. '
            'You explain algorithms clearly using real-world Karachi examples."'
        )
        # Replace the multi-line SYSTEM_PROMPT assignment
        import re
        edited = re.sub(
            r'SYSTEM_PROMPT\s*=\s*\(.*?\)',
            f"SYSTEM_PROMPT = {new_prompt}",
            content,
            flags=re.DOTALL,
        )
        if "SYSTEM_PROMPT" not in edited:
            edited = content  # fallback if regex missed
        r2 = c.post("/api/files/write", {"path": "app.py", "content": edited})
        check("Rewrite SYSTEM_PROMPT via files API", r2.status_code == 200, r2.text[:200])

    # --- chatbot as pair programmer (in-platform Chat pane) ---
    r = c.post("/api/chat", {
        "messages": [
            {"role": "user",
             "content": "Give me a one-line Python code snippet that adds a selectbox to a Streamlit app with options ['Formal', 'Casual', 'Funny']."}
        ]
    })
    if r.status_code == 200:
        # Chat uses SSE streaming — read the raw text
        raw = r.text
        log.debug("Chat raw response (first 500 chars): %s", raw[:500])
        check("Chatbot responds to pair-programmer request",
              "selectbox" in raw.lower() or "st." in raw.lower() or len(raw) > 30,
              raw[:300])
    elif r.status_code == 503:
        skip("Chatbot pair-programmer test", "Azure OpenAI not configured on this deployment")
    else:
        check("Chatbot returns 200", False, f"status={r.status_code} {r.text[:200]}")

    # --- security: blocked command reflected in API (guard test via chat) ---
    # We can't run a terminal command from the test script, but we verify the
    # platform's health still holds (DB survives anything the terminal may have done).
    r = c.get("/api/health")
    check("Platform still healthy after Day 2 operations", r.status_code == 200, r.text[:100])

    # --- write requirements.txt to confirm editor writes work for new deps ---
    r = c.get("/api/files/read?path=requirements.txt")
    if r.status_code == 200:
        orig_reqs = r.json()["content"]
        new_reqs = orig_reqs.rstrip() + "\n# added in session 2\n"
        r2 = c.post("/api/files/write", {"path": "requirements.txt", "content": new_reqs})
        check("Write requirements.txt (simulating pip install step)", r2.status_code == 200,
              r2.text[:200])


# ---------------------------------------------------------------------------
# Day 3 — Production Deployment & Operations
# ---------------------------------------------------------------------------
def test_day3(c: Client) -> None:
    section("DAY 3 — Production Deployment & Operations")

    # --- deploy command is well-formed if sandbox is set ---
    r = c.get("/api/workspace/deploy-cmd")
    if r.status_code == 200:
        dc = r.json()
        if dc.get("ready"):
            cmd = dc.get("command", "")
            check("deploy-cmd contains 'az webapp up'", "az webapp up" in cmd, cmd[:300])
            check("deploy-cmd contains webapp name", dc["webapp_name"] in cmd)
            check("deploy-cmd contains resource group", dc["resource_group"] in cmd)
            check("deploy-cmd contains startup file flag",
                  "startup-file" in cmd or "streamlit run" in cmd)
            check("deploy-cmd contains AZURE_OPENAI_ENDPOINT",
                  "AZURE_OPENAI_ENDPOINT" in cmd)
            log.info("  📋 Deploy command preview:")
            for line in cmd.splitlines()[:6]:
                log.info("     %s", line)
        else:
            skip("deploy-cmd content checks",
                 "No sandbox provisioned — instructor needs to run PUT /api/workspace/sandbox/{id}")
            log.info("  ℹ  To provision a sandbox for a user, the instructor runs:")
            log.info("     PUT /api/workspace/sandbox/<user_id>")
            log.info("     { resource_group, webapp_name, location, azure_openai_endpoint, ... }")

    # --- progress: mark all session-3 steps complete, then verify ---
    r = c.get("/api/course")
    if r.status_code == 200:
        sessions = r.json().get("sessions", [])
        s3 = next((s for s in sessions if s["id"] == "session-3"), None)
        if s3:
            step_ids = [step["id"] for step in s3.get("steps", [])]
            for sid in step_ids:
                c.post("/api/progress", {"step_id": sid, "completed": True})
            r2 = c.get("/api/progress")
            if r2.status_code == 200:
                completed = r2.json().get("completed", [])
                all_done = all(sid in completed for sid in step_ids)
                check(f"All {len(step_ids)} session-3 steps can be marked complete",
                      all_done, f"marked={step_ids}, got={completed}")
            # Clean up
            for sid in step_ids:
                c.post("/api/progress", {"step_id": sid, "completed": False})

    # --- re-login to simulate returning student (token still works) ---
    r = c.get("/api/auth/me")
    check("Session token still valid after Day 3 operations", r.status_code == 200,
          r.text[:100])


# ---------------------------------------------------------------------------
# Day 4 — Polish & Demo
# App idea: "Karachi Street Food Guide"
#   A chatbot that recommends Karachi street food spots, explains dishes
#   (nihari, bun kebab, gola ganda, etc.), and teaches Urdu ordering phrases.
#   Students change APP_TITLE and SYSTEM_PROMPT, add a dish-type selectbox.
# ---------------------------------------------------------------------------
_DAY4_APP_PY = '''\
"""
Karachi Street Food Guide — Nixor AI + Cloud Course
====================================================
Day 4 polished version: helps visitors discover Karachi\'s best street food,
explains dishes, and teaches Urdu ordering phrases.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

APP_TITLE = "Karachi Street Food Guide"

SYSTEM_PROMPT = (
    "You are an enthusiastic Karachi street food expert. "
    "You know every famous stall, every dish, and every Urdu phrase needed to order like a local. "
    "Recommend specific spots, explain ingredients simply, and always include the Urdu name "
    "of the dish and a phonetic Urdu ordering phrase the visitor can use. "
    "Keep answers friendly, concise, and under 150 words."
)

client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
)
DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

DISH_TYPES = ["All", "Chaats & Snacks", "Grills & Kababs", "Sweets & Drinks", "Breakfast"]


def ask_the_ai(messages: list[dict]) -> str:
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=messages,
        temperature=0.7,
        max_tokens=300,
    )
    return response.choices[0].message.content


st.set_page_config(page_title=APP_TITLE, page_icon="\\U0001f9c6")
st.title(APP_TITLE)
st.caption("Your AI guide to Karachi\'s legendary street food · Nixor AI + Cloud Course")

dish_filter = st.selectbox("What are you craving?", DISH_TYPES)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

for msg in st.session_state.messages:
    if msg["role"] != "system":
        st.chat_message(msg["role"]).write(msg["content"])

prompt = f"[Filter: {dish_filter}] " if dish_filter != "All" else ""
if user_text := st.chat_input("Ask about a dish, area, or Urdu phrase..."):
    full_input = prompt + user_text
    st.session_state.messages.append({"role": "user", "content": full_input})
    st.chat_message("user").write(user_text)
    with st.chat_message("assistant"):
        with st.spinner("Checking with the locals..."):
            reply = ask_the_ai(st.session_state.messages)
        st.write(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
'''


def test_day4(c: Client) -> None:
    section("DAY 4 — Polish, Explain, and Demo  (app: Karachi Street Food Guide)")

    # --- Write the Day 4 polished app ---
    r = c.post("/api/files/write", {"path": "app.py", "content": _DAY4_APP_PY})
    if check("Write Day 4 app.py (Karachi Street Food Guide)", r.status_code == 200,
             r.text[:200]):
        # Verify key content
        r2 = c.get("/api/files/read?path=app.py")
        if r2.status_code == 200:
            content = r2.json()["content"]
            check("APP_TITLE updated to Karachi Street Food Guide",
                  "Karachi Street Food Guide" in content)
            check("SYSTEM_PROMPT updated with food expert persona",
                  "street food" in content.lower())
            check("Dish type selectbox present in Day 4 app",
                  "selectbox" in content and "DISH_TYPES" in content)
            check("load_dotenv() still present", "load_dotenv" in content)
            check("AzureOpenAI still wired up", "AzureOpenAI" in content)

    # --- Live chatbot demo smoke test ---
    r = c.post("/api/chat", {
        "messages": [
            {"role": "system",
             "content": "You are a Karachi street food expert. Keep answers under 50 words."},
            {"role": "user",
             "content": "What is bun kebab and what Urdu phrase do I use to order one?"},
        ]
    })
    if r.status_code == 200:
        raw = r.text
        log.debug("Day 4 chatbot response (first 600): %s", raw[:600])
        check("Chatbot answers Karachi food question",
              len(raw) > 20,
              raw[:300])
        has_food_word = any(w in raw.lower() for w in
                            ["kebab", "bun", "karachi", "urdu", "order", "street"])
        check("Response contains food-relevant content", has_food_word, raw[:300])
    elif r.status_code == 503:
        skip("Day 4 live chatbot demo", "Azure OpenAI not configured")
    else:
        check("Day 4 chatbot returns 200", False, f"{r.status_code} {r.text[:200]}")

    # --- Final full progress sweep: mark all steps in all sessions ---
    r = c.get("/api/course")
    if r.status_code == 200:
        sessions = r.json().get("sessions", [])
        all_steps = [step["id"] for s in sessions for step in s.get("steps", [])]
        log.info("  Marking all %d course steps complete for final demo...", len(all_steps))
        for sid in all_steps:
            c.post("/api/progress", {"step_id": sid, "completed": True})

        r2 = c.get("/api/progress")
        if r2.status_code == 200:
            completed = set(r2.json().get("completed", []))
            check(f"All {len(all_steps)} steps can be marked complete (full course done)",
                  set(all_steps) == completed,
                  f"missing={set(all_steps)-completed}")

    # --- Final health check ---
    r = c.get("/api/health")
    check("Platform healthy at end of Day 4", r.status_code == 200, r.text[:100])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Nixor Lab happy-path test suite")
    parser.add_argument("--url", default=os.environ.get("LAB_URL", "http://localhost:8000"),
                        help="Lab platform base URL")
    parser.add_argument("--email", default=f"happypath_{uuid.uuid4().hex[:6]}@test.nixor.edu",
                        help="Test account email (unique by default)")
    parser.add_argument("--password", default="HappyPath123!",
                        help="Test account password")
    parser.add_argument("--reuse-email", action="store_true",
                        help="Use a fixed email so re-runs hit the login path")
    args = parser.parse_args()

    if args.reuse_email:
        args.email = "happypath_reuse@test.nixor.edu"

    log.info("=" * 60)
    log.info("  NIXOR LAB — HAPPY PATH TEST SUITE")
    log.info("  Platform : %s", args.url)
    log.info("  Email    : %s", args.email)
    log.info("  Log file : %s", _LOG_FILE)
    log.info("  Started  : %s", datetime.now().isoformat())
    log.info("=" * 60)

    c = Client(args.url)

    ok = test_day0(c, args.email, args.password)
    if ok:
        test_day1(c)
        test_day2(c)
        test_day3(c)
        test_day4(c)
    else:
        log.error("Day 0 setup failed — skipping Days 1-4")

    # ---------- Summary ----------
    total = _results.passed + _results.failed + _results.skipped
    section("SUMMARY")
    log.info("  Total   : %d", total)
    log.info("  ✅ Pass  : %d", _results.passed)
    log.info("  ❌ Fail  : %d", _results.failed)
    log.info("  ⏭  Skip  : %d", _results.skipped)
    log.info("")
    log.info("  Results by check:")
    for line in _results.details:
        log.info("    %s", line)
    log.info("")
    log.info("  Log file: %s", _LOG_FILE.resolve())

    if _results.failed == 0:
        log.info("  🎉 ALL CHECKS PASSED — platform is ready for the course!")
    else:
        log.warning("  ⚠  %d check(s) failed — review the log above.", _results.failed)

    sys.exit(0 if _results.failed == 0 else 1)


if __name__ == "__main__":
    main()
