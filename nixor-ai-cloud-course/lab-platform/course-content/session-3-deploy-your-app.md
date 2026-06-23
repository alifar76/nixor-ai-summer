# Session 3 — Deploy YOUR App

**Goal:** take the app you built and put it on the internet for real.

## Key ideas
- **Deploying** = your code now runs on a server you rent, not just your browser.
- **Config vs code** — your secret key lives in the server's settings, not in the code you
  push. Same code, different secrets per environment. This is how professionals do it.
- **The loop** — deploy → something breaks → read the logs → fix → redeploy. This is real
  cloud work, and it's satisfying once it clicks.

## Steps
1. From your app folder, run the deploy command (the site pre-fills it with *your* web app
   name and resource group):
   `az webapp up --name <your-app> --resource-group rg-nixor-<your-team>`
2. Set your secrets as **App Settings** (the site gives you the exact command).
3. Open your public URL. If it errors, open the **logs**, find the problem, fix, redeploy.
4. Add one feature — e.g. let users upload an image and have the AI describe it.

## You learned
What deployment really is, why config and code are separated, how to read logs, and the
deploy-fix-redeploy loop.
