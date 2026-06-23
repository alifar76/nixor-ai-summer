# platform/frontend/ — build spec for Claude Code

This folder is intentionally (mostly) empty. Build the student-facing site here. The
backend API contract is in `platform/backend/` — build against it; don't duplicate state.

## What the student experiences

1. **Landing / login** — student enters their email. Triggers `POST /api/enroll`, then
   magic-link auth (see backend TODO). No passwords.

2. **Provisioning screen** — after first login, poll `GET /api/students/{email}` and show
   friendly status while their sandbox spins up: `pending → provisioning → ready`.
   Reassure them this is a one-time wait. On `ready`, reveal their sandbox details
   (resource group, web app URL).

3. **Course walkthrough** — the core. Render the 4 sessions from `GET /api/course`
   (sourced from `course-content/*.md`). Each session is a checklist of steps the student
   ticks off; persist via `POST /api/progress`. Show a progress bar. A student should be
   able to leave and come back exactly where they were.

   Within a step, where there's a command to run (e.g. `az webapp up`), pre-fill it with
   *that student's* values (their web app name, their resource group) pulled from their
   sandbox object — so they never hunt for IDs. A copy button per command.

4. **"My app" panel** — always-visible link to their deployed app URL once it exists, and
   their sandbox quick facts.

## Design direction

- Audience is 16–18, bright, mostly new to cloud. Friendly, confident, low-jargon.
  Celebrate milestones (first deploy = confetti moment).
- Mobile-friendly — students will check it on phones.
- Match Nixor branding if assets are provided.

## Suggested stack

React + Vite (or Next.js). Keep it simple; this is a guided walkthrough, not a SPA epic.
Talk to the backend over the documented JSON API.
