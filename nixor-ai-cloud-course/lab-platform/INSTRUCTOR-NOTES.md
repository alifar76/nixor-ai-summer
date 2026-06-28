# Instructor Notes — Nixor AI + Cloud Course (4 Days)

Ready-to-teach notes for each day, mapped to the in-platform sessions
(`course-content/session-*.md`) and the apps in `example-apps/`. Each student already
has a browser sandbox (Course pane, Monaco editor, Linux terminal, AI tutor) and a
reserved deploy slot — you don't manage any setup per student.

**What every app uses (say this once on Day 1 and keep pointing back to it):**

| Thing | Where it comes from |
|---|---|
| The AI model | **GPT‑5.5**, deployment `gpt-5-5`, on your **Azure OpenAI** resource |
| Endpoint / key | `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` (env vars, never in code) |
| Deployment name | `MODEL_GPT55_DEPLOYMENT` |
| The other 3 models | Grok‑4.3, DeepSeek‑V4‑Pro, Mistral‑Medium‑3.5 — on the **Foundry** resource (`AZURE_FOUNDRY_*`) |

The students never type a key. The platform injects these into the terminal and into
every deployed app. The whole course is one loop: **edit `app.py` → run → deploy → open the URL → improve.**

---

## Day 0 — Pre-flight (run as a 15-min warm-up, or assign as homework)

**Goal:** everyone can log in and sees a live workspace before Day 1, so Day 1 isn't lost to setup.

Walk the room through `session-0`:
1. Log in with school email → confirm the three panes are visible.
2. Terminal: `python --version`, then `pwd` (should be `/workspace`).
3. Editor: open `app.py`, `requirements.txt`, `README.md`.
4. Terminal: `pip install -r requirements.txt`.
5. Ask the **AI tutor** one question: *"What's the difference between running an app locally and deploying it?"*

**Exit check:** thumbs-up from every student that they logged in and ran a command. Note who couldn't — fix before Day 1.

---

## Day 1 — From Zero to First Live Deployment

**Arc (≈90 min):** 20 min concept → 25 min read the starter → 20 min first deploy → 15 min verify → 10 min ship log.

### The one idea to land
*Your code doesn't run on your laptop anymore. It runs on a computer in a data centre, and the internet can reach it.* Draw this on the board and keep it up all four days:

```
[ Browser ]  →  [ Your app.py running on Azure ]  →  [ GPT-5.5 model endpoint ]
   user            (the thing you deploy)              (the "brain", reached by key)
```

Define the four words from `session-1` in plain language: **cloud compute**, **resource group** (a labelled box holding one project's stuff), **endpoint + key** (address + password to the model), **deploy loop**.

### Live teach — read the starter `app.py` together
Open the starter app and point at the three universal parts of *every* AI app:
1. **Input** — `st.chat_input(...)`
2. **Model call** — `client.chat.completions.create(...)`
3. **Output** — `st.write(reply)`

Then point at the connection block and ask: *"Where's the API key?"* → It's read from the environment, not written in the file. This is the **secrets** lesson — keys in code get leaked; keys in env vars don't ship to GitHub.

### Hands-on lab
- Change exactly **two things**: `APP_TITLE` and one line of `SYSTEM_PROMPT`. Save.
- (Optional local sanity) `python compare_models.py` in the terminal — proves the sandbox can reach the models and shows all 4 answering.
- **Deploy:** Deploy panel → **Deploy my app** → watch the build log stream → open the live URL → paste it in the class chat.
- **Verify:** send 2 prompts on the live URL. Same behaviour as the editor? Good — that's "it works in production."

### App to deploy today
The **starter `app.py`** already in the workspace (a minimal chatbot). Day 1 is about the *loop*, not the app — keep changes tiny so the first deploy succeeds fast and everyone gets a win.

### Common pitfalls (and the fix)
- **Empty/unchanged app** → the deploy guard says "still the starter template." Tell them to actually edit `APP_TITLE`/`SYSTEM_PROMPT` first.
- **Build fails** → 90% of the time a package isn't in `requirements.txt`. Read the red line in the build log together — this is the debugging lesson.
- **App loads but errors on send** → endpoint/key/deployment mismatch; almost always an env issue on the platform, not their code.

### Exit ticket (the "ship log" from `session-1`)
Three lines: *what worked, what broke, what I fixed.* Collect these — they're your attendance + comprehension check.

---

## Day 2 — Build Core Product Skills

**Arc (≈90 min):** 15 min concept → 20 min rewrite the prompt → 30 min add a UI control → 20 min structured testing → 5 min checklist.

### The one idea to land
*Prompt design IS product design.* The same model becomes a tutor, a debate coach, or a Karachi food guide purely through its instructions. A vague prompt makes a vague product.

### Live teach
Take one weak prompt (*"You are a helpful assistant"*) and improve it live with the class into something specific (audience + job + constraints + tone). Show how the output changes. Then introduce **modes**: one app, several jobs, chosen by the user.

### Hands-on lab → deploy `day2_study_coach.py`
This is the day's centrepiece — copy `example-apps/day2_study_coach.py` over `app.py`. It demonstrates everything in `session-2`:
- A clear **mission** (study help for O/A‑level students).
- **System behaviour** rewritten per mode.
- A **UI control** (`st.sidebar.radio`) that switches the AI's job and resets the chat.

Have students **make it theirs**: change `APP_TITLE` and the three prompts in `MODES` to their own audience (a cricket tactics coach, an Urdu poetry explainer, a chemistry quiz bot…). Then redeploy.

**Structured testing (the discipline lesson):** run 5 prompts per `session-2` — easy, ambiguous, adversarial, off-topic, edge case — and write down how the app behaved. This is their first taste of *evaluation*.

**Use the tutor as a pair programmer:** tell them to ask the AI tutor for *"a minimal change to add a second mode,"* not a full rewrite. They apply the diff and test it.

### Exit ticket
A 4-line quality checklist for their app: correctness, clarity, safety, failure behaviour.

---

## Day 3 — Ship It: Real Cloud Deployment

**Arc (≈90 min):** 25 min how-it-works → 25 min deploy + read logs → 20 min break-and-fix → 20 min latency + concepts.

> Day 3 is the systems day. Less new app code, more *understanding what deploy actually does.* Most code is already written — they're shipping the Day 2 app.

### The one idea to land
*Production deployment is not magic.* Walk the pipeline from `session-3` end to end:

```
Your editor → ZIP → upload to your VM → docker build → docker run -p <port>:8000 → public URL
```

Explain **image vs container** (recipe vs the cake), **port mapping**, **DNS label**, and that **keys are injected at `docker run`, never baked into the image**. Use the concept table at the bottom of `session-3` as your board notes.

### Hands-on lab
1. Confirm the app still runs, then **check `requirements.txt`** lists every import. (Tie back to Day 1's failed builds.)
2. **Deploy** and watch the real `docker build` log stream.
3. **Read logs:** run `docker logs student-<slug> --tail 50` on the VM and project it — show them logs are the only window into a running server.
4. **Break it on purpose:** add a syntax error → Deploy → watch it fail → fix → redeploy → succeed. *This is the lesson*, not an accident.
5. **Measure latency:** 3 prompts on the live app vs the local run — why the difference? (network hop to the model endpoint).

### App to deploy today
Their **Day 2 app**, now hardened for deployment. The teaching value is in the *pipeline and debugging*, so don't introduce a new app — keep the variable that changes to "the deploy," not "the code."

### Stretch
`docker ps` on the VM (deploy twice — does the old container linger?); skim `student.Dockerfile` and propose a leaner version; name one reliability risk + one cost risk of 50 apps on 3 shared VMs.

### Exit ticket
One sentence each, in their own words: *what is a Docker image* and *what is a container.*

---

## Day 4 — Polish, Explain, and Demo Like an Engineer

**Arc (≈90 min):** 30 min polish lab → 20 min cost/architecture → 25 min demo prep + rehearsal → 15 min demos.

### The one idea to land
*Engineering value = code + communication.* A working app nobody can understand or rely on isn't done. Today is reliability, cost-awareness, and a clear story.

### Hands-on lab → deploy `day4_polished_coach.py`
Copy `example-apps/day4_polished_coach.py` over `app.py`. It upgrades the Day 2 coach with exactly the `session-4` polish goals:
- **Streaming** replies (`st.write_stream`) — feels instant.
- **Graceful failure** — `try/except` shows a friendly message instead of a red traceback; empty input is ignored.
- **Reset button** + a footer that says what it runs on.

Have students port their own Day 2 prompt/modes into it, then redeploy.

**Stretch → `day4_model_playground.py`:** a model picker that sends one prompt to any of the 4 models and shows the answer. This is the concrete payoff of the two-resource setup — GPT‑5.5 routes to Azure OpenAI, the other three to Foundry. Great for a "compare the models" demo moment.

### Cost & architecture (talk, 20 min)
From `session-4`: what drives spend (tokens × calls, always-on hosting) and what controls it (token caps, the F1/free tier, shared VMs). Then each student explains their architecture in four boxes: **app runtime → model endpoint → secrets/config → deploy target.** If they can draw it, they understand it.

### Demo day
Each student gives a **3-minute demo**: problem → approach → live walkthrough on their public URL → one lesson learned. Do one full uninterrupted rehearsal (login → live app) first so nothing surprises them on stage.

**Suggested 10-point rubric:** live app works (3) · clear problem & audience (2) · one polish/reliability feature shown (2) · explains architecture in plain words (2) · one honest lesson learned (1).

### Exit ticket / reflection
*"If you had two more weeks, what would you build next?"* — closes the course on momentum.

---

## Quick reference — the apps in `example-apps/`

| File | Use on | What it teaches |
|---|---|---|
| (starter `app.py` in workspace) | Day 1 | the deploy loop; input → model → output; secrets in env |
| `day2_study_coach.py` | Day 2 | prompt = product; a mode selector; structured testing |
| `day4_polished_coach.py` | Day 4 | streaming, error handling, reset — production polish |
| `day4_model_playground.py` | Day 4 stretch | the 4-model catalog; routing GPT‑5.5 vs Foundry models |

All four are beginner-readable, deploy with one click, and share the same tiny
`requirements.txt` (streamlit, openai, python-dotenv). To use one: paste its contents
into `app.py`, make it yours, and hit **Deploy**.
