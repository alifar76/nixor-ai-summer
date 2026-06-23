# Session 2 — Build It Yourself

**Goal:** stop using a ready-made app and build your *own* with a few lines of Python.

## Key ideas
- **API / SDK** — how your code talks to the AI model over the internet.
- **System prompt** — the AI's job description. Change this and you change everything.
- **Secrets** — your API key is a password. It goes in settings, NEVER in your code.
- **Tokens** — the AI reads and writes in chunks called tokens. Tokens cost money. Cheap
  here, but real — this is why we use the small, fast `gpt-4o-mini`.

## Steps
1. Open your **Codespace** (browser VS Code, already set up).
2. Open `student-app/app.py`. Find the two lines marked `# 👈 EDIT THIS`.
3. Change `APP_TITLE` and `SYSTEM_PROMPT` to invent your app: a Physics study buddy, a
   Karachi food guide, a debate coach — your call. This is now *your* app.
4. Run `streamlit run app.py` and chat with your creation in the preview window.

## You learned
How an app calls an AI model, how a system prompt shapes behaviour, why keys are secret,
and why tokens cost money.
