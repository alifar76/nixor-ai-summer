# Nixor AI + Cloud Course — Platform Starter

A starter scaffold for a 4-session summer course where A-level students **build and
deploy their own AI app on Microsoft Azure**. The goal of this repository is to grow
(with help from Claude Code) into a single website where a student logs in with their
email and is walked, step by step, through the entire course — without ever having to
worry about Azure entitlements, GitHub setup, or environment configuration.

## What's in here today

```
nixor-ai-cloud-course/
├── README.md              ← you are here
├── CLAUDE.md              ← the brief for Claude Code: goal, conventions, backlog
├── course-content/        ← the 4 sessions as markdown (the walkthrough steps)
├── student-app/           ← the Streamlit AI app skeleton students customize & deploy
│   └── .devcontainer/     ← Codespaces config so setup is one click, identical for all
├── infra/                 ← Infrastructure-as-Code: what each student's sandbox contains
│   ├── main.bicep         ← per-student resource group (Azure OpenAI + App Service)
│   ├── policy-*.bicep     ← guardrail: deny expensive resource types
│   └── provision_student.py  ← orchestrates: invite → resource group → deploy → grant
└── platform/              ← original skeleton/spec for the course website
    ├── backend/           ← FastAPI stub: enrollment, provisioning trigger, progress API
    └── frontend/          ← spec for the student-facing walkthrough site

lab-platform/             ← the BUILT teaching website (what students actually use)
├── backend/              ← FastAPI: auth, progress, in-browser terminal + editor + chatbot
├── frontend/             ← React app (Monaco editor, xterm terminal)
├── Dockerfile            ← builds the platform image (frontend + FastAPI runtime)
└── infra/vm/             ← VM + privileged Docker deployment (see lab-platform/README.md)
```

> **Two layers, don't confuse them.** `platform/` was the initial skeleton/spec; the
> working implementation lives in **`lab-platform/`** and is deployed as one privileged
> Docker container on an Azure VM (the per-terminal isolation jail needs `CAP_SYS_ADMIN`,
> which App Service can't grant). That is a separate concern from the per-student **Azure
> sandboxes** below, which each student gets provisioned to deploy *their own* app.

## The architecture in one picture

```
  Student                Course Website (platform/)              Azure
  -------                ---------------------------             -----
  enters email   ──►  backend validates + triggers   ──►  1. invite as Entra guest
                      provisioning                         2. create resource group
                                                           3. deploy infra/main.bicep
                                                              (Azure OpenAI + Web App)
                                                           4. assign role scoped to the RG
  walks through  ◄──  frontend renders course-content/ ◄──  student now has a sandbox
  4 sessions          and tracks progress                    with everything pre-wired
```

## The honest prerequisites (read before building)

Three real-world facts the code is designed around:

1. **You can't grant Azure access to a bare email.** A student needs an identity in your
   Microsoft Entra tenant first. The flow is: invite them as a B2B **guest**, *then*
   assign an RBAC role scoped to their resource group. `infra/provision_student.py`
   does this in order.

2. **Automated provisioning needs a powerful credential.** Create one **service
   principal** with `Contributor` + `User Access Administrator` at the subscription (or a
   dedicated management group), store its secret in your backend's environment (never in
   code), and let the platform act through it. Treat this credential like a master key.

3. **Budgets only alert — they do not stop spending.** Cost safety is *architected in*,
   not bolted on:
   - Azure OpenAI deployment capacity (TPM) is capped low in `main.bicep`.
   - Hosting uses the **F1 (free)** App Service tier.
   - `policy-deny-expensive-skus.bicep` blocks VMs/GPUs so nothing costly can be created.
   - Budget alerts are a backstop that emails you, nothing more.

## Quickstart for you (the instructor)

```bash
# 1. Try the student app locally (or in Codespaces)
cd student-app
cp .env.example .env        # fill in your Azure OpenAI endpoint/key/deployment
pip install -r requirements.txt
streamlit run app.py

# 2. Provision one test student sandbox
cd ../infra
pip install -r requirements.txt
az login
cp ../platform/backend/.env.example .env   # fill in subscription, SP creds, etc.
python provision_student.py --email test.student@example.com --team team01

# 3. Run the (skeleton) platform backend
cd ../platform/backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## Region & model note

Azure OpenAI model availability **varies by region**. Before committing, confirm
`gpt-4o-mini` is available in your chosen region (UAE North and the India regions are
closest to Karachi, but may not carry every model — Sweden Central / an East US region
are common fallbacks). Set the region in `infra/main.bicep` and the provisioning config.

## License

MIT — see `LICENSE`.
