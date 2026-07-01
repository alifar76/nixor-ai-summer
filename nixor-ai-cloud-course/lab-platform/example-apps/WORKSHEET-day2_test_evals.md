# Worksheet — Model Playground & Eval Lab (`day2_test_evals.py`)

**Time:** ~60 minutes · **You will:** run real AI model evaluations, edit the grader, reason about cost, and learn how "which model is best?" is actually measured.

### Before you start
1. Open `day2_test_evals.py` in the editor.
2. In the terminal, run it:
   ```bash
   streamlit run day2_test_evals.py --server.port 8501
   ```
3. Your four models are already wired up: **GPT‑5.5** lives on your *Azure OpenAI* resource; **Grok‑4.3, DeepSeek‑V4‑Pro, Mistral‑Medium‑3.5** live on your *Foundry* resource. You don't touch any keys — they're injected for you.

> After each task: **save the file**, and Streamlit will show a "Rerun" button (top‑right). Click it to see your change.

Each task below has: 🎯 the goal · 🛠️ what to do · 🧭 guided steps · 💡 the concept.

---

## Task 1 — Run an eval and read the map (warm‑up, ~5 min)
🎯 **Goal:** understand what the app does before changing it.

🛠️ In the **⚔️ Head‑to‑Head** tab, ask all four models one question. Then in **📊 Benchmark Eval**, click **Run benchmark** and read the leaderboard.

🧭 **Do this and answer in a comment at the top of the file:**
- Which model was *fastest*? Which was *most accurate*? Were they the same model?
- Look at the **Per‑question breakdown**. Find one question where models *disagreed*.

💡 **Concept:** An *eval* = a fixed set of questions + an automatic grader + a score you can compare. The same prompt gives different answers, speeds, and costs across models — there is no single "best" model, only "best for a goal."

---

## Task 2 — Add your own benchmark questions (~8 min)
🎯 **Goal:** extend the test set — the heart of any eval.

🛠️ Add **two** new questions to the `BENCHMARK` list: one `numeric` and one `keywords`.

🧭 **Guided steps** — find the `BENCHMARK = [ ... ]` list and add before the closing `]`:
```python
    BenchItem("q11", "Chemistry",
              "What is the chemical symbol for gold? Reply with one word.",
              "keywords", ["au"]),
    BenchItem("q12", "Arithmetic",
              "What is 144 divided by 12? Reply with just the number.",
              "numeric", [12]),
```
Save → rerun → **Run benchmark** again. Your questions now appear in the leaderboard scoring.

💡 **Concept:** A `BenchItem` has a *grading mode* (`numeric` / `keywords` / `exact`) and a list of acceptable `answers`. Writing good eval questions — clear, unambiguous, auto‑gradable — is a real AI‑engineering skill.

---

## Task 3 — Break the grader, then fix it (~10 min)
🎯 **Goal:** see that the *grader is just code* — and code has bugs.

🛠️ The `keywords` grader uses a **substring** match (`k in answer`). That causes **false positives**: the keyword `"au"` (gold) would also match the word "b**au**xite" or "s**au**ce". Prove it, then fix it to match **whole words only**.

🧭 **Guided steps:**
1. Prove the bug — temporarily change your q11 answer key to `["co"]` and imagine a model answering "carbon". Substring match says ✅ even though "co" ≠ "carbon monoxide". 
2. Add this helper above the `grade()` function:
   ```python
   def keyword_hit(answer, keywords):
       """Whole-word keyword match — avoids 'au' matching inside 'sauce'."""
       low = answer.lower()
       return any(re.search(rf"\b{re.escape(str(k).lower())}\b", low) for k in keywords)
   ```
3. In `grade()`, replace the `keywords` branch:
   ```python
   if item.mode == "keywords":
       return keyword_hit(answer, item.answers)
   ```
4. Rerun the benchmark — scores should be the same for good answers but stricter on sneaky ones.

💡 **Concept:** Evaluation *validity*. A grader that's too loose gives models credit they didn't earn (false positives); too strict punishes correct answers (false negatives). Word‑boundaries (`\b`) are a classic precision fix.

---

## Task 4 — Cost, and the metric that actually matters (~8 min)
🎯 **Goal:** connect accuracy to money.

🛠️ Run the benchmark, then in the **💵 Pricing** editor change one model's **Output $/1M** price and watch **Cost/correct** update instantly.

🧭 **Guided steps:**
1. Run the benchmark so the leaderboard appears.
2. In the pricing table, set GPT‑5.5's *Output $/1M* to `10.0` and DeepSeek's to `3.48` (these are close to real Azure list prices).
3. Read the **Cost/correct (USD)** column. Sort the leaderboard by clicking that column header.

💡 **Concept:** **Cost per correct answer** is the real "best value" metric — the cheapest way to get a right answer, not just the highest accuracy. A model that's 5% more accurate but 8× pricier is often the wrong choice. This is how teams actually pick models in production.

---

## Task 5 — LLM‑as‑judge vs objective rules (~10 min)
🎯 **Goal:** grade open‑ended answers that rules can't handle.

🛠️ Add an **open‑ended** question (rules can't grade it), then compare **Objective** grading vs **LLM‑as‑judge** on it.

🧭 **Guided steps:**
1. Add a question that has no single keyword answer:
   ```python
    BenchItem("q13", "Explanation",
              "In one sentence, explain why the sky appears blue.",
              "keywords", ["scatter"],
              note="Objective grading is weak here — a good LLM-judge case."),
   ```
2. Run the benchmark with grading = **Objective rules** (sidebar). Note the score on q13 — the model may be *right* but marked ❌ if it doesn't say the exact word "scatter".
3. Switch the sidebar **Benchmark grading** to **LLM‑as‑judge**, pick a **Judge model**, and run again. The judge reads the answer and decides correctness.
4. **Stretch:** open `JUDGE_SYSTEM` and make the judge stricter or add "accept answers that mention Rayleigh scattering." Rerun.

💡 **Concept:** **LLM‑as‑judge** — using one model to grade another — scales to subjective/open‑ended tasks where rules fail. But judges have biases (they can favour verbose answers, or their own style), which is why we keep *both* graders and compare.

---

## Task 6 — Parallel vs serial: why the app feels fast (~8 min)
🎯 **Goal:** understand concurrency for cloud API calls.

🛠️ The app asks all four models **at the same time**. Make it ask them **one at a time** and feel the difference.

🧭 **Guided steps:**
1. Find `run_head_to_head()`. It uses:
   ```python
   with ThreadPoolExecutor(max_workers=len(labels)) as ex:
   ```
2. Temporarily change `max_workers=len(labels)` → `max_workers=1`. Save, rerun, and run a Head‑to‑Head. Notice it's now noticeably slower (roughly the sum of all four response times instead of the slowest one).
3. **Change it back to `len(labels)`.**

💡 **Concept:** Calling a cloud API is **I/O‑bound** — most of the time is spent *waiting* on the network, not computing. Running calls in parallel threads overlaps the waiting, so total time ≈ the *slowest* model, not the *sum*. This is a core cloud‑performance idea.

---

## Task 7 (stretch) — Re‑rank the leaderboard by value (~8 min)
🎯 **Goal:** show that the *metric you choose* decides the "winner."

🛠️ The leaderboard ranks by **accuracy first**. Change it to rank by **cheapest‑per‑correct first**.

🧭 **Guided steps** — in `leaderboard_rows()`, find the sort line:
```python
rows.sort(key=lambda r: (r["Accuracy"], -(r.get("Cost (USD)") or 0.0)), reverse=True)
```
Replace it with (cheapest cost‑per‑correct wins; `None` sinks to the bottom):
```python
rows.sort(key=lambda r: (r.get("Cost/correct (USD)") is None,
                         r.get("Cost/correct (USD)") or 9e9))
```
Rerun the benchmark. Did the #1 model change?

💡 **Concept:** "Which model is best?" is **undefined without a metric.** Rank by accuracy and one model wins; rank by cost‑per‑correct and another does. Choosing the right metric for *your* use case is the actual decision.

---

## Wrap‑up (write 3 lines)
1. Which model would *you* deploy for a student app, and why (accuracy? cost? speed?)
2. One weakness you found in the objective grader.
3. One thing an LLM‑judge did better — or worse — than the rules.

**Deploy it:** open the **Deploy** panel and click **Deploy my app** to put your version live on a public URL.
