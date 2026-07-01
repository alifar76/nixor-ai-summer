# Instructor Answer Key — Nixor AI Study Studio (`day2_nixor_study_studio.py`)

For the instructor. Each section gives the **expected solution code**, **model answers** to the trace/reflection prompts, **talking points**, and **common mistakes**. Share with students *after* they attempt each task.

> **Run-first reminder:** `streamlit run day2_nixor_study_studio.py --server.port 8501`. Save + **Rerun** after each edit. Six tabs; every answer shows a caption with the **model**, **tokens**, and **rupee cost**; the sidebar tracks the running **session cost**.

**Big picture:** every feature in this app is the same shape — **system prompt + user prompt → `call_model()` → response → render + record cost**. The tabs differ only in the prompt and what they do with the reply.

---

## Task 1 — Follow one request from click to answer

**Model answers:**
- **The two parts sent to the model** (in `tab_explain()`): a **`system`** prompt ("You are an outstanding A-Level teacher…") and a **`prompt`** (the numbered "Explain '{topic}'… 1. definition 2. explanation 3. analogy…" instruction). System = *who the AI is*; user = *this specific request*.
- **Which function chooses the model:** `ask()` calls **`pick_model(task, settings)`**, which returns the user's forced model, or else `TASK_DEFAULTS[task]`.
- **The line that calls Azure:** inside `call_model()` →
  ```python
  resp = client.chat.completions.create(
      model=deployment, messages=messages,
      temperature=temperature, max_completion_tokens=max_tokens)
  ```

**Talking points:**
- Once students see this system+user→call→render pattern, **every tab is the same** — Quiz, Exam Coach, Planner just change the prompt and parse the reply differently.
- `messages` is a list of role/content dicts — the universal chat format across providers.

**Common mistake:** confusing the *system* prompt (persistent role) with the *user* prompt (the one request). Emphasize the difference.

---

## Task 2 — Route tasks to the right model

**Expected solution** — in `TASK_DEFAULTS`:
```python
    "exam_grade": "Mistral-Medium-3.5",   # was "DeepSeek-V4-Pro"
```

**What students should observe:** the caption under the marked answer now names a different model; marking quality/carefulness changes. DeepSeek (a reasoning model) tends to follow the mark scheme more faithfully; a lighter model may be faster but less rigorous.

**Talking points:**
- **Model routing** = send each job to the model that suits it. Draft/format tasks → cheap+fast; careful marking/reasoning → a reasoning model.
- This is how real products balance **quality vs cost**: you don't pay for a top-tier model on tasks that don't need it.

**Common mistake:** the sidebar **Model routing** dropdown *overrides* `TASK_DEFAULTS` unless it's set to **"Auto (best per task)"**. If a student forced one model globally, editing `TASK_DEFAULTS` seems to do nothing — check `pick_model()` with them:
```python
def pick_model(task, settings):
    forced = settings.get("forced_model")
    if forced and forced != "Auto (best per task)":
        return forced            # forced model wins
    return TASK_DEFAULTS.get(task, "GPT-5.5")
```

---

## Task 3 — Personalize the app

**Expected solution:**
```python
SUBJECTS = [..., "Sociology"]   # add anywhere in the list

LEVELS = ["Explain like I'm 10", "GCSE level", "O-Level level",
          "A-Level level", "University level"]
```

**Talking points:**
- The dropdown values are **slotted into the prompt** (`f"...at this level: {level}."`). Small structured inputs → large behavioural change, with **zero** new AI code — this is prompt *parameterization*.

**Common mistake:** removing `"Chemistry"` from `SUBJECTS`. `tab_explain()` uses `index=SUBJECTS.index("Chemistry")` as its default, so deleting it raises `ValueError`. Add subjects; don't delete the referenced default (or update the `index=` too).

---

## Task 4 — Prompt engineering: "Answer in Urdu"

**Expected solution** — in `tab_explain()`, after the `level = st.select_slider(...)` line:
```python
    in_urdu = st.checkbox("Answer in Urdu اردو میں جواب", key="ex_urdu")
```
and just before `res, model = ask("explain", prompt, ...)`:
```python
        if in_urdu:
            prompt += "\n\nWrite your entire answer in Urdu."
```

**Talking points:**
- You shipped a real feature — **localization** — by appending **one sentence** to the prompt. **Prompt design = product design.**
- Discuss quality: models vary on Urdu fluency; this is a natural lead-in to the Compare tab ("which model writes the best Urdu?").

**Common mistakes:**
- Adding the checkbox *inside* the `if st.button(...)` block (so it never renders). It must be at the tab's top level (4-space indent), like the other inputs.
- Appending to `prompt` *after* the `ask()` call (too late — no effect).

---

## Task 5 — Trust, but validate: model JSON

**Expected solution** — in `tab_quiz()`, immediately after
`qs = data.get("questions") if isinstance(data, dict) else None` (same 8-space indent):
```python
        if qs and len(qs) < n:
            st.info(f"The model returned {len(qs)} of {n} questions — using what we got.")
        if qs:
            qs = qs[:n]
```

**Why `parse_json()` exists (the concept):** models are asked for JSON but sometimes wrap it in prose or ```` ```json ```` fences. `parse_json()` strips fences, tries `json.loads`, and if that fails, **regex-extracts** the first `{...}`/`[...]` block. It returns `None` on failure so callers can degrade gracefully instead of crashing.

**Talking points:**
- **Structured output is a contract the model can break.** Production code *always* validates and never assumes the reply is well-formed.
- The `elif res["ok"]: st.warning("Couldn't parse…")` branch is the graceful-failure path — the app stays up even when the model misbehaves.

**Common mistake:** trusting `data["questions"]` directly (a `KeyError`/`TypeError` waiting to happen). The `isinstance(data, dict)` and `.get()` guards are the point.

---

## Task 6 — Cost awareness: budget warning

**Expected solution** — in `sidebar()`, right after `st.sidebar.metric("Total cost", ...)`:
```python
    BUDGET_RS = 5.0
    if cost["usd"] * USD_PKR > BUDGET_RS:
        st.sidebar.warning(f"⚠️ Over Rs {BUDGET_RS:.0f} this session — you're a big spender!")
```

**Where the numbers come from:** `add_cost()` (called after every successful `ask()` / Compare call) accumulates `prompt_tokens`, `completion_tokens`, and USD into `st.session_state["cost"]` using `PRICING`. The sidebar converts USD → PKR with `USD_PKR`.

**Talking points:**
- **Every token costs money**; `PRICING × real tokens` is the true spend. Making it visible changes behaviour.
- A threshold warning is a tiny **FinOps guardrail** — the same idea as Azure budget alerts. "Cost is architected, not discovered on the invoice."

**Common mistake:** referencing `cost` before it's defined — it must go **after** `cost = st.session_state.get("cost", new_cost_acc())` in `sidebar()`.

---

## Task 7 (capstone) — Ship a new Translate tab

**Expected solution:**

1. Routing default — in `TASK_DEFAULTS`:
```python
    "translate": "Mistral-Medium-3.5",
```
2. The tab function (near the other `tab_*` functions):
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
3. Register it in `main()`:
```python
    tabs = st.tabs(["📚 Explain", "📝 Exam Coach", "🧠 Quiz", "✍️ Feedback",
                    "🗓️ Planner", "⚖️ Compare Models", "🌐 Translate"])
    ...
    with tabs[6]:
        tab_translate(settings)
```

**Talking points:**
- Students just completed the **full loop of an AI feature**: UI input → prompt → `ask()`/`call_model()` → render → automatic cost tracking.
- Notice how **little** new code it took — because the app reuses `ask`, `call_model`, and `_last_call_caption`. **Good architecture makes new features cheap.** This is the day's most important professional lesson.

**Common mistakes:**
- Forgetting the `with tabs[6]:` wiring (tab appears but is empty).
- Off-by-one on the tab index (`tabs[5]` already used by Compare; Translate is `tabs[6]`).
- Forgetting the `TASK_DEFAULTS["translate"]` entry — it still works (`pick_model` falls back to GPT‑5.5), but the routing lesson is lost.

---

## Wrap-up discussion (model answers)
1. **Which model for Translate, and why?** Any reasonable choice defended on **cost/quality** — a cheaper model is fine for short translations; test Urdu quality in the Compare tab before committing.
2. **A time a model returned bad JSON/error — how did the app cope?** The `parse_json()` fallback + the `st.warning`/`st.error` branches keep the app running instead of crashing.
3. **Total session cost & priciest feature:** usually the tabs with the largest `max_tokens` (Quiz at 1100, Planner at 1100, Exam grading at 900) and the **Compare** tab (four calls at once) cost the most — a concrete lesson in what drives spend.

**One-line takeaway for the class:** *An AI app is mostly ordinary software — the "AI" is one function call; the craft is the prompt, validating the reply, routing to the right model, and knowing what it costs.*
