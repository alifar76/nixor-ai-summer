# Session 1 — From Zero to First Live Deployment

**Goal:** deploy your first real AI app and understand what each cloud piece does.

## Big ideas for today
- **Cloud compute**: your code runs on remote infrastructure, not your laptop.
- **Resource group**: a project container for everything your app needs.
- **Endpoint + key**: how your app reaches an AI model securely.
- **Deployment loop**: change code -> run -> verify -> repeat.

## Steps
1. **Map your architecture**: identify the frontend app, backend runtime, and AI model endpoint in your own words.
2. **Inspect the starter app**: open `app.py` and find where user input, model call, and model output happen.
3. **Run locally first**: in terminal, run `streamlit run app.py`, test 2 prompts, and note response quality.
4. **Understand your secrets flow**: explain why API keys belong in environment variables, not source code.
5. **Deploy to Azure Web App**: run the provided deployment command for your assigned app/resource group.
6. **Verify production behavior**: open your live URL and compare local vs deployed behavior.
7. **Record your first ship log**: write 3 lines: what worked, what broke, what you fixed.

## Starter track (if new to coding)
- Change only app title and one prompt instruction.
- Validate deployment and capture one screenshot of your live app.

## Stretch track (if experienced)
- Add one input control (mode selector or temperature-like behavior).
- Explain trade-offs between speed, cost, and output quality.

## You learned
How a cloud AI app is structured, why secret management matters, and how to ship version 1 quickly.
