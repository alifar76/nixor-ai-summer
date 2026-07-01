# Worksheet — Nixor AI Study Studio (`day2_nixor_study_studio.py`)

**Time:** ~60 minutes · **You will:** trace how an AI feature works end‑to‑end, route tasks to different models, engineer prompts, validate model JSON, track real cost, and ship a brand‑new feature.

Each task: 🎯 goal · 🛠️ do · 🧭 guided steps · 💡 concept.

---

## Task 1 — Follow one request from click to answer (~7 min)
🎯 **Goal:** build a correct mental model of how the app talks to AI.

🛠️ Trace the **Explain** feature by reading three functions in order: `tab_explain()` → `ask()` → `call_model()`.

🧭 **Find and answer (as comments):**
- In `tab_explain()`, what are the two parts sent to the model? (Hint: look for `system=` and `prompt=`.)
- In `ask()`, which function decides *which* model is used?
- In `call_model()`, which line actually calls Azure? (Hint: `client.chat.completions.create(...)`.)

💡 **Concept:** Every AI feature is the same shape: a **system prompt** (the AI's job description) + a **user prompt** (this specific request) → a model call → a response. Once you see this pattern, every tab in the app looks the same.

---

## Task 2 — Route tasks to the right model (~8 min)
🎯 **Goal:** learn that different jobs suit different models.

🛠️ Change which model **marks exams**, then test it.

🧭 **Guided steps:**
1. Find the `TASK_DEFAULTS` dictionary near the top. Note `"exam_grade": "DeepSeek-V4-Pro"` — a reasoning model chosen for careful marking.
2. Change it to `"exam_grade": "Mistral-Medium-3.5"`. Save, rerun.
3. In **Exam Coach**: generate a question, write a short answer, click **Mark my answer**. The caption now shows a different model marked it.
4. Try both models on the *same* answer. Which gave more careful, mark‑scheme‑faithful feedback?

💡 **Concept:** **Model routing.** Cheap/fast models are great for drafting; reasoning models are better for careful, step‑by‑step tasks like marking. Picking the right model per task (instead of one model for everything) is how real AI products control both quality and cost.

---

## Task 3 — Personalize the app (~7 min)
🎯 **Goal:** a quick, safe edit to build confidence.

🛠️ Add your own **subject** and a new **explanation level**.

🧭 **Guided steps:**
1. Find the `SUBJECTS = [...]` list and add one, e.g. `"Sociology"`.
2. Find `LEVELS = [...]` (just above `tab_explain`) and add `"O-Level level"`:
   ```python
   LEVELS = ["Explain like I'm 10", "GCSE level", "O-Level level", "A-Level level", "University level"]
   ```
3. Rerun → in **Explain**, your new subject and level now appear in the dropdowns and are fed into the prompt.

💡 **Concept:** **Prompt parameterization.** The UI controls (subject, level) get slotted into the prompt string. Small, structured inputs → big changes in the AI's behaviour, with zero new AI code.

---

## Task 4 — Prompt engineering: add an "Answer in Urdu" option (~10 min)
🎯 **Goal:** change model behaviour purely through the prompt.

🛠️ Add a checkbox to **Explain** that makes the answer come back in Urdu.

🧭 **Guided steps** — inside `tab_explain()`, after the `level = st.select_slider(...)` line, add:
```python
    in_urdu = st.checkbox("Answer in Urdu اردو میں جواب", key="ex_urdu")
```
Then, just before the line `res, model = ask("explain", prompt, ...)`, add:
```python
        if in_urdu:
            prompt += "\n\nWrite your entire answer in Urdu."
```
Save, rerun, tick the box, and Explain a topic. The whole answer should now be in Urdu.

💡 **Concept:** **Prompt design = product design.** You added a real feature (localization) without touching the model or the API — just by appending one instruction. This is the single most powerful lever in AI app development.

---

## Task 5 — Trust, but validate: model JSON (~10 min)
🎯 **Goal:** handle the reality that models don't always return perfect data.

🛠️ Make the **Quiz** more robust: enforce the number of questions and fail gracefully.

🧭 **Guided steps:**
1. Read `parse_json()` — it strips ```` ```json ```` fences and tries hard to recover a JSON object. Ask yourself: *why is this function necessary?* (Because models sometimes wrap JSON in prose or code fences.)
2. In `tab_quiz()`, immediately **after** the line `qs = data.get("questions") if isinstance(data, dict) else None` and **before** the existing `if qs:` — at the same 8‑space indentation — add a guard that trims to the requested count and warns if the model returned too few:
   ```python
        if qs and len(qs) < n:
            st.info(f"The model returned {len(qs)} of {n} questions — using what we got.")
        if qs:
            qs = qs[:n]
   ```
3. Test it: generate a quiz a few times. Notice the app never crashes even if the model misbehaves.

💡 **Concept:** **Structured outputs are a contract the model can break.** Production AI code *always* validates model JSON and degrades gracefully. `parse_json()` and your guard are defensive programming — a core professional habit.

---

## Task 6 — Cost awareness: add a budget warning (~8 min)
🎯 **Goal:** turn the invisible cost of AI into a visible guardrail.

🛠️ Show a warning in the sidebar when a student's session cost passes a threshold.

🧭 **Guided steps** — inside `sidebar()`, just after the `st.sidebar.metric("Total cost", ...)` line, add:
```python
    BUDGET_RS = 5.0
    if cost["usd"] * USD_PKR > BUDGET_RS:
        st.sidebar.warning(f"⚠️ Over Rs {BUDGET_RS:.0f} this session — you're a big spender!")
```
Rerun, then use a few tabs until you cross Rs 5 and watch the warning appear. Open **Cost by model** to see where the money went.

💡 **Concept:** **Cost is architected, not discovered later.** Every token costs money; `PRICING × real tokens` is your true spend. Budgets and alerts (this is a tiny "FinOps" guardrail) are how cloud teams stop a runaway bill.

---

## Task 7 (capstone) — Ship a brand‑new feature (~12 min)
🎯 **Goal:** add a full working tab, end‑to‑end.

🛠️ Add a **🌐 Translate** tab that translates any text into a chosen language.

🧭 **Guided steps:**
1. Add a routing default — in `TASK_DEFAULTS`, add:
   ```python
       "translate": "Mistral-Medium-3.5",
   ```
2. Add the tab function (put it near the other `tab_*` functions):
   ```python
   def tab_translate(settings):
       st.subheader("🌐 Translate")
       st.caption("Translate notes or questions into another language.")
       text = st.text_area("Text to translate", height=140, key="tr_text")
       lang = st.selectbox("Into", ["Urdu", "English", "Arabic", "French", "Sindhi"], key="tr_lang")
       if st.button("Translate", key="tr_go", type="primary"):
           if not text.strip():
               st.warning("Enter some text first.")
               return
           system = "You are a precise translator. Preserve meaning, names, and tone."
           prompt = f"Translate the following into {lang}. Return only the translation.\n\n{text}"
           res, model = ask("translate", prompt, settings, system=system,
                            max_tokens=600, spinner="Translating")
           if res["ok"]:
               st.markdown(res["answer"])
               _last_call_caption(res, model)
           else:
               st.error(res["error"])
   ```
3. Register it in `main()`. Change the tabs line to include a 7th tab and wire it up:
   ```python
       tabs = st.tabs(["📚 Explain", "📝 Exam Coach", "🧠 Quiz", "✍️ Feedback",
                       "🗓️ Planner", "⚖️ Compare Models", "🌐 Translate"])
   ```
   …and after the `with tabs[5]:` block add:
   ```python
       with tabs[6]:
           tab_translate(settings)
   ```
4. Rerun → your new tab is live, routes to a model, tracks its own cost, and reuses the same call/cost plumbing as every other feature.

💡 **Concept:** You just did the **full loop of adding an AI feature**: UI → prompt → model call → cost tracking → render. Notice how little new code it took because the app is built from reusable pieces (`ask`, `call_model`, `_last_call_caption`). Good architecture makes new features cheap.

---

## Wrap‑up (write 3 lines)
1. Which model did you route your new Translate feature to, and why?
2. One time a model returned imperfect JSON or an error — how did the app cope?
3. What was your total session cost in rupees, and which feature was the most expensive?

**Deploy it:** open the **Deploy** panel and click **Deploy my app** — your customized Study Studio goes live at a public URL you can share.
