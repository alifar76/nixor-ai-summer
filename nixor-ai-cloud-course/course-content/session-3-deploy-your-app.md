# Session 3 — Production Deployment and Operations

**Goal:** deploy your custom version confidently and operate it like an engineer.

## Big ideas for today
- **Production is a different environment** than local development.
- **Config over hardcoding** keeps apps portable and secure.
- **Observability** (logs + checks) is how you debug real systems.

## Steps
1. **Prepare release notes**: list exactly what changed since Session 1.
2. **Deploy your current branch** to your assigned Azure Web App and wait for completion.
3. **Set/verify app settings**: endpoint, API key, model deployment, and runtime essentials.
4. **Run post-deploy smoke tests**: homepage load, one successful prompt, one failure case.
5. **Debug using logs**: if anything fails, inspect logs first, then patch, redeploy, retest.
6. **Measure latency and quality**: test 3 prompts and compare response speed and usefulness.
7. **Stabilize v1.1**: make one improvement based on test evidence, not guesswork.

## Starter track
- Deploy successfully and pass smoke tests.
- Fix at least one issue found in logs.

## Stretch track
- Add a basic rollback plan (what change would you revert first and why).
- Document one reliability risk and one cost risk.

## You learned
How to think beyond coding: release quality, runtime diagnostics, and reliable iteration in cloud.
