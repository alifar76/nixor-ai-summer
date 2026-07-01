# Instructor Answer Key — Model Playground & Eval Lab (`day2_test_evals.py`)

For the instructor. Each section gives the **expected solution code**, the **answers to the reflection prompts**, **talking points** to raise with the class, and **common mistakes** to watch for. Share freely with students *after* they've attempted each task.

> **Run-first reminder for the class:** `streamlit run day2_test_evals.py --server.port 8501`. Save the file, then click **Rerun** (top-right) after each edit. All four models are pre-wired — GPT‑5.5 on the Azure OpenAI resource, the other three on Foundry.

**Big picture to keep returning to:** an *eval* is three things — a fixed **question set**, an automatic **grader**, and a **score** you can compare across models. Everything in this hour is one of those three pieces.

---

## Task 1 — Run an eval and read the map

**What students should observe (results vary run-to-run):**
- The **fastest** model is often *not* the **most accurate**. Small models (Mistral, Grok) frequently answer quickest; GPT‑5.5 / DeepSeek are usually strong on the reasoning traps.
- Models most often **disagree** on: **q3** (bat & ball — the trap answer is $0.10, correct is $0.05), **q6** (letters in "strawberry"), and **q10** (the Urdu *sher*).

**Talking points:**
- **Latency ≠ quality.** Speed and correctness are independent axes.
- The "trap" questions (q3, q6) exist because they expose *how* a model reasons — q6 is hard because models see tokens, not letters.
- There is no single "best" model — only best *for a goal* (accuracy, speed, or cost).

**Common mistake:** assuming the model that "sounds" most confident is correct. Point them to the ✅/❌ marks, not the prose.

---

## Task 2 — Add your own benchmark questions

**Expected solution** — added inside the `BENCHMARK = [ ... ]` list:
```python
    BenchItem("q11", "Chemistry",
              "What is the chemical symbol for gold? Reply with one word.",
              "keywords", ["au"]),
    BenchItem("q12", "Arithmetic",
              "What is 144 divided by 12? Reply with just the number.",
              "numeric", [12]),
```

**Talking points:**
- A good eval question is **unambiguous**, has a **checkable answer**, and matches the right **mode** (`numeric` / `keywords` / `exact`).
- `numeric` uses `extract_numbers()` (pulls every number out and compares with tolerance `tol`); `keywords` checks substrings; `exact` compares a normalized whole string.

**Common mistakes:**
- Using `numeric` for a worded answer (or vice-versa).
- Ambiguous answers, e.g. "name a prime number" (many correct answers) — evals need a *defined* correct set.
- Putting the answer inside the prompt by accident.

---

## Task 3 — Break the grader, then fix it

**Expected solution** — helper added above `grade()`:
```python
def keyword_hit(answer, keywords):
    """Whole-word keyword match — avoids 'au' matching inside 'sauce'."""
    low = answer.lower()
    return any(re.search(rf"\b{re.escape(str(k).lower())}\b", low) for k in keywords)
```
and the `keywords` branch inside `grade()` becomes:
```python
    if item.mode == "keywords":
        return keyword_hit(answer, item.answers)
```

**Why it matters (the concept):**
- The original `k in answer.lower()` is a **substring** test → **false positives** ("au" ⊂ "sauce", "co" ⊂ "cocoa").
- `\b...\b` anchors to **word boundaries**, raising **precision** (fewer wrong ✅) at a small risk to **recall** (see the caveat).

**Two subtleties worth raising with a strong class:**
1. **Unicode/Urdu caveat:** `\b` is defined around ASCII word characters, so it behaves oddly for the **Urdu** keyword strings in q9/q10. Those items also carry Latin transliterations (`"firaq"`, `"mir amman"`), which still match — but this is a real limitation of naive graders on non-Latin scripts.
2. **This will interact with Task 5.** After this stricter matcher, a keyword like `"scatter"` will **no longer** match the word "scatter**ing**". That's not a bug — it's the exact reason open-ended questions need an LLM judge (Task 5). Great callback.

**Common mistake:** forgetting `re.escape(...)` — a keyword containing regex metacharacters (like `co2`'s… fine, but `c++`) would otherwise break the pattern.

---

## Task 4 — Cost, and the metric that actually matters

**Expected outcome:** after running the benchmark and editing the **💵 Pricing** table, the **Cost/correct (USD)** column recomputes live (no re-run), and clicking that column header re-sorts.

**The math (show it on the board):**
```
cost_usd = (input_tokens / 1e6) * input_price + (output_tokens / 1e6) * output_price
cost_per_correct = cost_usd / number_correct
```
This is exactly `model_cost()` + the `Cost/correct (USD)` field in `leaderboard_rows()`.

**Talking points:**
- **Cost per correct answer** is the real "value" metric — the cheapest way to buy a right answer.
- Tie back to the architecture: GPT‑5.5 is billed on the **Azure OpenAI** resource; Grok/DeepSeek/Mistral on the **Foundry** resource — different price sheets, same app.
- Output tokens usually cost several× input tokens — that's why concise answers are cheaper.

**Common mistake:** comparing raw **Cost (USD)** instead of **Cost/correct** — a model that answers nothing is "cheap" but worthless.

---

## Task 5 — LLM-as-judge vs objective rules

**Expected solution** — an open-ended `BenchItem`:
```python
    BenchItem("q13", "Explanation",
              "In one sentence, explain why the sky appears blue.",
              "keywords", ["scatter"],
              note="Objective grading is weak here — a good LLM-judge case."),
```

**What students should see:**
- With **Objective rules**, a fully correct answer that says "the atmosphere **scatters** blue light" is marked ✅, but "Rayleigh **scattering** of shorter wavelengths" may be marked ❌ (especially after Task 3's `\b` fix, since "scattering" ≠ `\bscatter\b`). The grader is judging *wording*, not *meaning*.
- With **LLM-as-judge**, the judge model reads the answer's *meaning* and both are accepted.

**Optional `JUDGE_SYSTEM` tweak** to make the judge accept synonyms:
```python
JUDGE_SYSTEM = (
    "You are a strict but fair grader. Given a QUESTION, a REFERENCE answer, and a "
    "CANDIDATE answer, mark the candidate correct if it is factually right and answers "
    'the question, even if worded differently. Respond ONLY with JSON: '
    '{"correct": true|false, "reason": "<short reason>"}.'
)
```

**Talking points:**
- **LLM-as-judge** scales grading to subjective/open-ended tasks where rules can't.
- **Costs and caveats:** the judge makes *extra* API calls (one per graded answer → `len(BENCHMARK) × len(models)` more calls), and judges have **biases** — verbosity bias, and *self-preference* (a model tends to favour answers in its own style). This is why we keep the objective grader too and compare.
- `parse_judge_verdict()` shows a real production pattern: parse the model's JSON, but **fall back** to a keyword heuristic if the JSON is malformed.

**Common mistake:** picking a weak model as the judge and trusting it blindly. Suggest DeepSeek or GPT‑5.5 as judges and discuss why.

---

## Task 6 — Parallel vs serial

**Expected change** in `run_head_to_head()`:
```python
with ThreadPoolExecutor(max_workers=1) as ex:   # serial (temporary)
```
then **revert** to `max_workers=len(labels)`.

**What students should measure:**
- Serial total time ≈ **sum** of the four models' latencies.
- Parallel total time ≈ the **slowest single** model's latency.
- On four models each taking ~2–6 s, that's roughly 16 s → ~6 s.

**Talking points:**
- Calling a cloud API is **I/O-bound** — the program mostly *waits* on the network. Threads let those waits **overlap**.
- Python's GIL does **not** block this: while a thread waits on a socket, it releases the GIL, so other threads run. Threads are perfect for I/O-bound work (network), less so for CPU-bound work.
- This is why real apps fan out requests concurrently — user-perceived latency drops dramatically.

**Common mistake:** thinking parallelism makes each *individual* call faster. It doesn't — it overlaps the waiting.

---

## Task 7 (stretch) — Re-rank the leaderboard by value

**Expected solution** — replace the sort in `leaderboard_rows()`:
```python
# was: rows.sort(key=lambda r: (r["Accuracy"], -(r.get("Cost (USD)") or 0.0)), reverse=True)
rows.sort(key=lambda r: (r.get("Cost/correct (USD)") is None,
                         r.get("Cost/correct (USD)") or 9e9))
```

**Why the key looks like that:**
- `(... is None, ...)` pushes rows with **no** cost/correct (a model that got 0 correct → `None`) to the **bottom**.
- `or 9e9` gives those a huge sentinel so they never sort to the top.
- Lower cost-per-correct now ranks **first** (note: no `reverse=True`).

**Talking points:**
- "Which model is best?" is **undefined without a metric.** Rank by accuracy → one winner; by cost/correct → possibly a different winner (a cheaper model that's *almost* as accurate often wins on value).
- Choosing the metric that matches *your* use case (a free student tool vs. a paid legal assistant) is the real engineering decision.

**Common mistake:** leaving `reverse=True` in (which would rank the *most expensive* first) or crashing on the `None` cost/correct — hence the two-part key.

---

## Wrap-up discussion (model answers)
1. **Which model would you deploy for a student app?** A strong answer weighs **cost/correct** and **latency** over raw accuracy — a free classroom tool favours a cheap, fast, "good-enough" model; a high-stakes app favours accuracy.
2. **A weakness of the objective grader:** substring false positives; can't judge meaning/paraphrase; brittle on non-Latin scripts.
3. **LLM-judge better/worse:** better on open-ended/paraphrased answers; worse in cost (extra calls), consistency, and bias (verbosity/self-preference).

**One-line takeaway for the class:** *Evals turn "I feel like this model is better" into a number you can defend — and the number you choose to optimize is itself a design decision.*
