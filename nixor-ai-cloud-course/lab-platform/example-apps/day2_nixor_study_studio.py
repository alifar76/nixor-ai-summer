"""
Nixor AI Study Studio 🎓
========================
A study companion for A-Level students, powered by four Azure-hosted models
(GPT-5.5, Grok-4.3, DeepSeek-V4-Pro, Mistral-Medium-3.5) — built for the Nixor
College Karachi summer AI program.

It solves real study problems AND teaches AI literacy on every screen (which
model, how many tokens, and the real rupee cost of each request).

Features
  📚 Explain      — any concept at your level, with analogies + auto-flashcards
  📝 Exam Coach   — AI examiner: generates an exam question + mark scheme, then
                    marks YOUR answer against it with feedback  ⭐ the star feature
  🧠 Quiz         — interactive MCQ quiz, scored, with explanations
  ✍️ Feedback     — rubric feedback on an essay / long answer
  🗓️ Planner      — a revision timetable from your subjects + exam dates
  ⚖️ Compare      — ask all four models at once and see how they differ

Run with:  streamlit run study_studio.py
"""

import os
import re
import json
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
from openai import AzureOpenAI

load_dotenv()
# also load the course creds file if present (same folder), in addition to .env
_creds = Path(__file__).with_name(".nixor_creds")
if _creds.exists():
    load_dotenv(_creds)

# --------------------------------------------------------------------------- #
# Config: model registry + real Azure retail prices (USD per 1M tokens)
# --------------------------------------------------------------------------- #
OPENAI_EP = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
OPENAI_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
FOUNDRY_EP = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
FOUNDRY_KEY = os.environ.get("AZURE_FOUNDRY_API_KEY", "")
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

MODELS = {
    "GPT-5.5": (os.environ.get("MODEL_GPT55_DEPLOYMENT", "gpt-5-5"), OPENAI_EP, OPENAI_KEY),
    "Grok-4.3": (os.environ.get("MODEL_GROK43_DEPLOYMENT", "xai-grok43"), FOUNDRY_EP, FOUNDRY_KEY),
    "DeepSeek-V4-Pro": (os.environ.get("MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT", "ds-v4pro"), FOUNDRY_EP, FOUNDRY_KEY),
    "Mistral-Medium-3.5": (os.environ.get("MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT", "mstr-med35"), FOUNDRY_EP, FOUNDRY_KEY),
}

PRICING = {  # Azure retail list price, USD per 1,000,000 tokens
    "GPT-5.5": {"input": 1.25, "output": 10.00},
    "Grok-4.3": {"input": 1.25, "output": 2.50},
    "DeepSeek-V4-Pro": {"input": 1.74, "output": 3.48},
    "Mistral-Medium-3.5": {"input": 1.50, "output": 7.50},
}
USD_PKR = 278.0

# Which model each task defaults to in "Auto" routing (a teaching point in itself).
TASK_DEFAULTS = {
    "explain": "GPT-5.5",
    "flashcards": "Mistral-Medium-3.5",
    "exam_generate": "GPT-5.5",
    "exam_grade": "DeepSeek-V4-Pro",   # reasoning model for careful marking
    "quiz": "GPT-5.5",
    "feedback": "GPT-5.5",
    "plan": "Mistral-Medium-3.5",
}

SUBJECTS = ["Mathematics", "Further Maths", "Physics", "Chemistry", "Biology",
            "Computer Science", "Economics", "Business", "Accounting",
            "English Literature", "History", "Psychology", "Urdu", "Islamiyat"]

# --------------------------------------------------------------------------- #
# Pure helpers — NO Streamlit here, so this section is unit-testable.
# --------------------------------------------------------------------------- #


def parse_json(text):
    """Best-effort JSON extraction from a model reply (handles ```json fences)."""
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


def model_cost(prompt_tokens, completion_tokens, price):
    pt, ct = prompt_tokens or 0, completion_tokens or 0
    return (pt / 1_000_000) * price["input"] + (ct / 1_000_000) * price["output"]


def new_cost_acc():
    return {"prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0, "calls": 0,
            "by_model": {}}


def add_cost(acc, model, pt, ct):
    """Accumulate token usage + USD cost for one call. Returns the same dict."""
    pt, ct = pt or 0, ct or 0
    price = PRICING.get(model, {"input": 0, "output": 0})
    cost = model_cost(pt, ct, price)
    acc["prompt_tokens"] += pt
    acc["completion_tokens"] += ct
    acc["usd"] += cost
    acc["calls"] += 1
    bm = acc["by_model"].setdefault(
        model, {"prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0, "calls": 0})
    bm["prompt_tokens"] += pt
    bm["completion_tokens"] += ct
    bm["usd"] += cost
    bm["calls"] += 1
    return acc


def score_quiz(quiz, answers):
    """quiz: list of {q, options, answer_index, explanation}. answers: {i: chosen_index}.
    Returns (num_correct, total, per_question list)."""
    details, correct = [], 0
    for i, item in enumerate(quiz):
        chosen = answers.get(i)
        is_right = chosen is not None and chosen == item.get("answer_index")
        correct += int(is_right)
        details.append({"i": i, "chosen": chosen, "correct": is_right,
                        "answer_index": item.get("answer_index"),
                        "explanation": item.get("explanation", "")})
    return correct, len(quiz), details


def days_until(target, today=None):
    today = today or dt.date.today()
    return (target - today).days


def pick_model(task, settings):
    """Auto routing chooses per-task; otherwise the user's forced model wins."""
    forced = settings.get("forced_model")
    if forced and forced != "Auto (best per task)":
        return forced
    return TASK_DEFAULTS.get(task, "GPT-5.5")


def build_client(endpoint, key, api_version):
    return AzureOpenAI(api_key=key, azure_endpoint=endpoint, api_version=api_version)


def call_model(label, prompt, system=None, max_tokens=700, temperature=1.0):
    """Call one model; always returns a dict, never raises."""
    deployment, endpoint, key = MODELS[label]
    out = {"label": label, "ok": False, "answer": "", "error": None, "latency": None,
           "prompt_tokens": None, "completion_tokens": None}
    if not endpoint or not key:
        out["error"] = f"{label}: endpoint or key not set in environment"
        return out
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    t0 = time.perf_counter()
    try:
        client = build_client(endpoint, key, API_VERSION)
        resp = client.chat.completions.create(
            model=deployment, messages=messages,
            temperature=temperature, max_completion_tokens=max_tokens)
        out["latency"] = time.perf_counter() - t0
        out["answer"] = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        if usage is not None:
            out["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
            out["completion_tokens"] = getattr(usage, "completion_tokens", None)
        out["ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["latency"] = time.perf_counter() - t0
        out["error"] = str(exc)
    return out


# --------------------------------------------------------------------------- #
# Streamlit glue
# --------------------------------------------------------------------------- #
def _ensure_state():
    ss = st.session_state
    ss.setdefault("cost", new_cost_acc())
    ss.setdefault("quiz", None)
    ss.setdefault("quiz_submitted", False)
    ss.setdefault("exam", None)
    ss.setdefault("exam_result", None)
    ss.setdefault("flashcards", None)
    ss.setdefault("fc_index", 0)
    ss.setdefault("fc_flipped", False)
    ss.setdefault("explanation", None)


def ask(task, prompt, settings, system=None, max_tokens=700, spinner="Thinking…"):
    """Route to a model, call it, record cost into the session, and return (res, model)."""
    model = pick_model(task, settings)
    with st.spinner(f"{spinner}  ·  using {model}"):
        res = call_model(model, prompt, system=system, max_tokens=max_tokens,
                         temperature=settings["temperature"])
    if res["ok"]:
        add_cost(st.session_state["cost"], model,
                 res["prompt_tokens"], res["completion_tokens"])
    return res, model


def _last_call_caption(res, model):
    bits = [f"🤖 {model}"]
    if res.get("latency") is not None:
        bits.append(f"⏱️ {res['latency']:.1f}s")
    if res.get("completion_tokens") is not None:
        c = model_cost(res.get("prompt_tokens"), res.get("completion_tokens"),
                       PRICING.get(model, {"input": 0, "output": 0}))
        bits.append(f"🔢 {res.get('completion_tokens')} tokens")
        bits.append(f"💰 Rs {c * USD_PKR:.3f}")
    st.caption("  ·  ".join(bits))


# ---------------------------- Tab: Explain --------------------------------- #
LEVELS = ["Explain like I'm 10", "GCSE level", "A-Level level", "University level"]


def tab_explain(settings):
    st.subheader("📚 Explain a concept")
    st.caption("Stuck on a topic? Get it explained at your level, with an analogy "
               "and a worked example — then turn it into flashcards.")
    c1, c2 = st.columns([2, 1])
    topic = c1.text_input("What do you want explained?",
                          "Le Chatelier's principle", key="ex_topic")
    subject = c2.selectbox("Subject", SUBJECTS, index=SUBJECTS.index("Chemistry"),
                           key="ex_subject")
    level = st.select_slider("Level", LEVELS, value="A-Level level", key="ex_level")

    if st.button("✨ Explain it", key="ex_go", type="primary"):
        system = ("You are an outstanding A-Level teacher who makes hard ideas click. "
                  "Be accurate, encouraging, and clear.")
        prompt = (f"Explain '{topic}' in {subject} at this level: {level}.\n"
                  "Structure your answer as:\n"
                  "1. A one-line plain-language definition.\n"
                  "2. A clear explanation (a few short paragraphs).\n"
                  "3. A memorable analogy.\n"
                  "4. A worked example or application.\n"
                  "5. One common misconception to avoid.")
        res, model = ask("explain", prompt, settings, system=system, max_tokens=800,
                         spinner="Explaining")
        if res["ok"]:
            st.session_state["explanation"] = {"text": res["answer"], "topic": topic,
                                               "subject": subject}
            st.session_state["_explain_meta"] = (res, model)
            st.session_state["flashcards"] = None
        else:
            st.error(res["error"])

    exp = st.session_state.get("explanation")
    if exp:
        st.markdown(exp["text"])
        if "_explain_meta" in st.session_state:
            _last_call_caption(*st.session_state["_explain_meta"])
        st.divider()
        if st.button("🗂️ Turn this into flashcards", key="ex_cards"):
            system = "You create concise, high-quality revision flashcards."
            prompt = (f"From the topic '{exp['topic']}' ({exp['subject']}), create 6 "
                      "revision flashcards. Return ONLY JSON of the form "
                      '{"cards":[{"front":"question/term","back":"answer"}]}.')
            res, model = ask("flashcards", prompt, settings, system=system,
                             max_tokens=700, spinner="Making flashcards")
            data = parse_json(res["answer"]) if res["ok"] else None
            if data and isinstance(data.get("cards"), list):
                st.session_state["flashcards"] = data["cards"]
                st.session_state["fc_index"] = 0
                st.session_state["fc_flipped"] = False
            else:
                st.warning("Couldn't parse flashcards — try again "
                           "(a good lesson in why we validate model JSON!).")
        _render_flashcards()


def _render_flashcards():
    cards = st.session_state.get("flashcards")
    if not cards:
        return
    i = st.session_state["fc_index"] % len(cards)
    card = cards[i]
    st.markdown(f"**Flashcard {i + 1} / {len(cards)}**")
    side = card["back"] if st.session_state["fc_flipped"] else card["front"]
    label = "Answer" if st.session_state["fc_flipped"] else "Front"
    with st.container(border=True):
        st.caption(label)
        st.markdown(f"### {side}")
    a, b, c = st.columns(3)
    if a.button("⬅️ Prev", key="fc_prev"):
        st.session_state["fc_index"] = (i - 1) % len(cards)
        st.session_state["fc_flipped"] = False
    if b.button("🔄 Flip", key="fc_flip"):
        st.session_state["fc_flipped"] = not st.session_state["fc_flipped"]
    if c.button("Next ➡️", key="fc_next"):
        st.session_state["fc_index"] = (i + 1) % len(cards)
        st.session_state["fc_flipped"] = False
    csv = pd.DataFrame(cards).to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download all flashcards (CSV — Anki-ready)", csv,
                       "flashcards.csv", "text/csv", key="fc_csv")


# ---------------------------- Tab: Exam Coach ------------------------------ #
BOARDS = ["Cambridge (CAIE)", "Edexcel", "AQA", "Generic"]


def tab_exam(settings):
    st.subheader("📝 Exam Coach — practise past-paper style questions")
    st.caption("Generate an exam-style question, write your answer, and get it "
               "**marked against a mark scheme** with feedback — like a real examiner.")

    c1, c2, c3 = st.columns(3)
    subject = c1.selectbox("Subject", SUBJECTS, key="exm_subject")
    board = c2.selectbox("Board", BOARDS, key="exm_board")
    marks = c3.slider("Marks", 2, 12, 6, key="exm_marks")
    topic = st.text_input("Topic (optional)", "", key="exm_topic",
                          placeholder="e.g. electromagnetic induction")

    if st.button("🎲 Generate a question", key="exm_gen", type="primary"):
        system = (f"You are an experienced {board} A-Level examiner for {subject}.")
        prompt = (f"Write ONE exam-style question worth {marks} marks"
                  + (f" on '{topic}'" if topic else "") + ".\n"
                  "Also produce a mark scheme as a list of creditable points "
                  "(one mark each unless stated). Return ONLY JSON of the form "
                  '{"question":"...","total_marks":' + str(marks) +
                  ',"mark_scheme":["point (1)","point (1)"]}.')
        res, model = ask("exam_generate", prompt, settings, system=system,
                         max_tokens=700, spinner="Setting a question")
        data = parse_json(res["answer"]) if res["ok"] else None
        if data and data.get("question"):
            st.session_state["exam"] = data
            st.session_state["exam_result"] = None
            st.session_state["_exam_meta"] = (res, model)
        elif res["ok"]:
            st.warning("Couldn't parse the question JSON — try again.")
        else:
            st.error(res["error"])

    exam = st.session_state.get("exam")
    if not exam:
        return

    st.markdown(f"#### 🧾 Question  ·  *{exam.get('total_marks', marks)} marks*")
    with st.container(border=True):
        st.markdown(exam["question"])
    if "_exam_meta" in st.session_state:
        _last_call_caption(*st.session_state["_exam_meta"])

    answer = st.text_area("✍️ Your answer", height=180, key="exm_answer")
    if st.button("✅ Mark my answer", key="exm_mark", type="primary"):
        if not answer.strip():
            st.warning("Write an answer first!")
        else:
            scheme = "\n".join(f"- {p}" for p in exam.get("mark_scheme", []))
            system = ("You are a fair but rigorous A-Level examiner. Mark strictly to "
                      "the mark scheme, award whole marks, and be specific and kind.")
            prompt = (f"QUESTION ({exam.get('total_marks', marks)} marks):\n{exam['question']}\n\n"
                      f"MARK SCHEME:\n{scheme}\n\nSTUDENT ANSWER:\n{answer}\n\n"
                      "Mark it. Return ONLY JSON of the form "
                      '{"marks_awarded":int,"total_marks":int,'
                      '"criteria":[{"point":"...","awarded":true,"comment":"..."}],'
                      '"overall":"2-3 sentences of feedback",'
                      '"model_answer":"a concise full-mark answer"}.')
            res, model = ask("exam_grade", prompt, settings, system=system,
                             max_tokens=900, spinner="Marking")
            data = parse_json(res["answer"]) if res["ok"] else None
            if data and "marks_awarded" in data:
                st.session_state["exam_result"] = data
                st.session_state["_grade_meta"] = (res, model)
            elif res["ok"]:
                st.warning("Couldn't parse the marking JSON — try again.")
            else:
                st.error(res["error"])

    _render_exam_result(exam, marks)


def _render_exam_result(exam, marks):
    result = st.session_state.get("exam_result")
    if not result:
        return
    awarded = result.get("marks_awarded", 0)
    total = result.get("total_marks", exam.get("total_marks", marks))
    pct = (awarded / total * 100) if total else 0
    st.markdown("#### 🏁 Result")
    m1, m2 = st.columns([1, 2])
    m1.metric("Marks", f"{awarded} / {total}", f"{pct:.0f}%")
    m2.progress(min(1.0, awarded / total if total else 0))
    if result.get("criteria"):
        df = pd.DataFrame([{
            "Creditable point": c.get("point", ""),
            "You got it": "✅" if c.get("awarded") else "❌",
            "Examiner comment": c.get("comment", ""),
        } for c in result["criteria"]])
        st.dataframe(df, hide_index=True, width="stretch")
    if result.get("overall"):
        st.info("🧑‍🏫 **Examiner feedback:** " + result["overall"])
    if result.get("model_answer"):
        with st.expander("📘 See a full-mark model answer"):
            st.markdown(result["model_answer"])
    with st.expander("🔍 See the mark scheme"):
        for p in exam.get("mark_scheme", []):
            st.markdown(f"- {p}")
    if "_grade_meta" in st.session_state:
        _last_call_caption(*st.session_state["_grade_meta"])


# ---------------------------- Tab: Quiz ------------------------------------ #
def tab_quiz(settings):
    st.subheader("🧠 Quick-fire quiz")
    st.caption("Generate a multiple-choice quiz on any topic, then test yourself.")
    c1, c2, c3 = st.columns(3)
    subject = c1.selectbox("Subject", SUBJECTS, key="qz_subject")
    topic = c2.text_input("Topic", "Photosynthesis", key="qz_topic")
    n = c3.slider("Questions", 3, 10, 5, key="qz_n")
    difficulty = st.radio("Difficulty", ["Easy", "Medium", "Hard"], horizontal=True,
                          index=1, key="qz_diff")

    if st.button("🎯 Generate quiz", key="qz_gen", type="primary"):
        system = "You write accurate, unambiguous multiple-choice questions."
        prompt = (f"Create a {difficulty.lower()} {n}-question multiple-choice quiz on "
                  f"'{topic}' ({subject}) for A-Level students. Each question has 4 "
                  "options and exactly one correct answer. Return ONLY JSON of the form "
                  '{"questions":[{"q":"...","options":["a","b","c","d"],'
                  '"answer_index":0,"explanation":"why"}]}.')
        res, model = ask("quiz", prompt, settings, system=system, max_tokens=1100,
                         spinner="Writing your quiz")
        data = parse_json(res["answer"]) if res["ok"] else None
        qs = data.get("questions") if isinstance(data, dict) else None
        if qs:
            st.session_state["quiz"] = qs
            st.session_state["quiz_submitted"] = False
            st.session_state["_quiz_meta"] = (res, model)
        elif res["ok"]:
            st.warning("Couldn't parse the quiz JSON — try again.")
        else:
            st.error(res["error"])

    quiz = st.session_state.get("quiz")
    if not quiz:
        return
    st.divider()
    answers = {}
    for i, item in enumerate(quiz):
        st.markdown(f"**Q{i + 1}. {item['q']}**")
        answers[i] = st.radio("Choose one", item["options"], index=None,
                              key=f"qz_ans_{i}", label_visibility="collapsed")

    if st.button("📊 Submit answers", key="qz_submit", type="primary"):
        st.session_state["quiz_submitted"] = True

    if st.session_state.get("quiz_submitted"):
        idx_answers = {i: (quiz[i]["options"].index(a) if a in quiz[i]["options"] else None)
                       for i, a in answers.items()}
        correct, total, details = score_quiz(quiz, idx_answers)
        st.markdown(f"### Score: {correct} / {total}  ({correct/total*100:.0f}%)")
        if correct == total:
            st.balloons()
        for d in details:
            item = quiz[d["i"]]
            right = item["options"][d["answer_index"]]
            mark = "✅" if d["correct"] else "❌"
            st.markdown(f"{mark} **Q{d['i']+1}** — correct answer: *{right}*")
            st.caption("💡 " + d["explanation"])
        if "_quiz_meta" in st.session_state:
            _last_call_caption(*st.session_state["_quiz_meta"])


# ---------------------------- Tab: Feedback -------------------------------- #
def tab_feedback(settings):
    st.subheader("✍️ Feedback on your writing")
    st.caption("Paste an essay or long answer and get structured, rubric-style feedback.")
    kind = st.selectbox("Type", ["Essay", "Long-answer response", "Personal statement",
                                 "Report"], key="fb_kind")
    subject = st.selectbox("Subject", SUBJECTS, key="fb_subject")
    text = st.text_area("Paste your writing here", height=220, key="fb_text")
    if st.button("🔎 Get feedback", key="fb_go", type="primary"):
        if len(text.strip()) < 40:
            st.warning("Paste a bit more text so the feedback is meaningful.")
        else:
            system = ("You are a supportive but honest A-Level teacher giving actionable "
                      "feedback. Never rewrite the whole thing for them.")
            prompt = (f"Give feedback on this {kind.lower()} for {subject}. Use these "
                      "headings: **Strengths**, **Structure & argument**, "
                      "**Evidence & accuracy**, **Language & style**, "
                      "**Top 3 priorities to improve**. Be specific and quote briefly.\n\n"
                      f"TEXT:\n{text}")
            res, model = ask("feedback", prompt, settings, system=system,
                             max_tokens=900, spinner="Reading your work")
            if res["ok"]:
                st.markdown(res["answer"])
                st.download_button("⬇️ Save feedback", res["answer"].encode("utf-8"),
                                   "feedback.md", "text/markdown", key="fb_dl")
                _last_call_caption(res, model)
            else:
                st.error(res["error"])


# ---------------------------- Tab: Planner --------------------------------- #
def tab_planner(settings):
    st.subheader("🗓️ Revision planner")
    st.caption("Turn your subjects and exam date into a realistic revision timetable.")
    subs = st.multiselect("Your subjects", SUBJECTS,
                          default=["Physics", "Chemistry", "Mathematics"], key="pl_subs")
    c1, c2 = st.columns(2)
    exam_date = c1.date_input("First exam date",
                              value=dt.date.today() + dt.timedelta(days=30), key="pl_date")
    hours = c2.slider("Hours you can study per day", 1, 10, 4, key="pl_hours")
    weak = st.text_input("Weakest areas (optional)", "", key="pl_weak")

    if st.button("🧭 Build my plan", key="pl_go", type="primary"):
        if not subs:
            st.warning("Pick at least one subject.")
            return
        left = days_until(exam_date)
        if left <= 0:
            st.warning("Pick a future exam date.")
            return
        system = "You are a study coach who builds realistic, motivating revision plans."
        prompt = (f"Build a {left}-day revision plan. Subjects: {', '.join(subs)}. "
                  f"Study hours available per day: {hours}. "
                  + (f"Prioritise these weak areas: {weak}. " if weak else "")
                  + "Give: (1) a short strategy, (2) a week-by-week breakdown as a table "
                  "with days, subjects/topics, and activities (learn/practice/past-paper), "
                  "and (3) 3 study tips. Keep it practical and encouraging.")
        res, model = ask("plan", prompt, settings, system=system, max_tokens=1100,
                         spinner="Planning")
        if res["ok"]:
            st.success(f"You have **{left} days** until your exam. Here's your plan:")
            st.markdown(res["answer"])
            st.download_button("⬇️ Save my plan", res["answer"].encode("utf-8"),
                               "revision_plan.md", "text/markdown", key="pl_dl")
            _last_call_caption(res, model)
        else:
            st.error(res["error"])


# ---------------------------- Tab: Compare --------------------------------- #
def tab_compare(settings):
    st.subheader("⚖️ Ask all four models")
    st.caption("The AI-literacy screen: send one question to all four models and see "
               "how their answers — and costs — differ. There's no single 'best' model.")
    prompt = st.text_area("Your question",
                          "Explain the difference between accuracy and precision, with an "
                          "example.", key="cmp_prompt")
    if st.button("🚀 Ask all four", key="cmp_go", type="primary"):
        labels = list(MODELS.keys())
        results = {}
        with st.spinner("Asking four models in parallel…"):
            with ThreadPoolExecutor(max_workers=len(labels)) as ex:
                futs = {ex.submit(call_model, l, prompt, None, 600,
                                  settings["temperature"]): l for l in labels}
                for f in as_completed(futs):
                    results[futs[f]] = f.result()
        for l, r in results.items():
            if r["ok"]:
                add_cost(st.session_state["cost"], l,
                         r["prompt_tokens"], r["completion_tokens"])
        st.session_state["compare"] = results

    results = st.session_state.get("compare")
    if not results:
        return
    labels = [l for l in MODELS if l in results]
    for i in range(0, len(labels), 2):
        cols = st.columns(2)
        for col, l in zip(cols, labels[i:i + 2]):
            with col.container(border=True):
                col.markdown(f"**{l}**")
                r = results[l]
                if not r["ok"]:
                    col.error(r["error"])
                    continue
                col.markdown(r["answer"])
                cost = model_cost(r["prompt_tokens"], r["completion_tokens"],
                                  PRICING.get(l, {"input": 0, "output": 0}))
                lat = f"{r['latency']:.1f}s" if r["latency"] else "—"
                col.caption(f"⏱️ {lat}  ·  🔢 {r.get('completion_tokens')} tok  ·  "
                            f"💰 Rs {cost*USD_PKR:.3f}")


# ------------------------------ Sidebar + main ----------------------------- #
def sidebar(settings_key="settings"):
    st.sidebar.title("🎓 Study Studio")
    st.sidebar.caption("Nixor College · Summer AI Program")
    name = st.sidebar.text_input("Your name", key="student_name")
    if name:
        st.sidebar.markdown(f"Assalam-o-alaikum, **{name}**! 👋")

    st.sidebar.divider()
    forced = st.sidebar.selectbox(
        "Model routing",
        ["Auto (best per task)"] + list(MODELS.keys()),
        help="Auto picks a suitable model per feature. Or force one model everywhere "
             "and compare — that's a real AI-engineering skill.",
    )
    temperature = st.sidebar.slider("Creativity (temperature)", 0.0, 2.0, 1.0, 0.1,
                                    help="Lower = focused, higher = creative. Some "
                                         "models only accept 1.0.")

    st.sidebar.divider()
    st.sidebar.markdown("### 💰 Session cost")
    cost = st.session_state.get("cost", new_cost_acc())
    total_tok = cost["prompt_tokens"] + cost["completion_tokens"]
    st.sidebar.metric("Total cost", f"Rs {cost['usd']*USD_PKR:.3f}",
                      f"${cost['usd']:.5f}")
    st.sidebar.caption(f"{cost['calls']} requests · {total_tok:,} tokens")
    if cost["by_model"]:
        with st.sidebar.expander("Cost by model"):
            rows = [{"Model": m,
                     "Calls": d["calls"],
                     "Rs": round(d["usd"] * USD_PKR, 3)}
                    for m, d in cost["by_model"].items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.sidebar.caption("Real Azure list prices × real tokens. This is what your usage "
                       "actually costs — a habit every AI builder needs.")

    missing = [l for l in MODELS if not (MODELS[l][1] and MODELS[l][2])]
    if missing:
        st.sidebar.warning("No credentials for: " + ", ".join(missing))

    return {"forced_model": forced, "temperature": temperature, "name": name}


def main():
    st.set_page_config(page_title="Nixor AI Study Studio", page_icon="🎓",
                       layout="wide")
    _ensure_state()
    settings = sidebar()
    st.title("🎓 Nixor AI Study Studio")
    st.caption("Your AI study partner for A-Levels — powered by four models running on "
               "Azure. Every screen shows which model answered and what it cost.")
    tabs = st.tabs(["📚 Explain", "📝 Exam Coach", "🧠 Quiz", "✍️ Feedback",
                    "🗓️ Planner", "⚖️ Compare Models"])
    with tabs[0]:
        tab_explain(settings)
    with tabs[1]:
        tab_exam(settings)
    with tabs[2]:
        tab_quiz(settings)
    with tabs[3]:
        tab_feedback(settings)
    with tabs[4]:
        tab_planner(settings)
    with tabs[5]:
        tab_compare(settings)


if __name__ == "__main__":
    main()