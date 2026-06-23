# infra/ — what each student's sandbox is made of

- **main.bicep** — the resource group contents: an Azure OpenAI resource with a
  capacity-capped `gpt-4o-mini` deployment, plus a free-tier App Service Web App
  pre-wired to talk to it. This is the heart of "they get all Azure services set up."
- **policy-deny-expensive-skus.bicep** — a subscription-scope guardrail that blocks
  VMs, GPUs, etc. Deploy once, before provisioning students.
- **provision_student.py** — orchestrates the full flow per student: invite guest →
  create RG → deploy bicep → assign scoped role → set budget.
- **deprovision_student.py** — deletes a student's RG (teardown).

## One-time setup (instructor)
```bash
az login
# Deploy the guardrail policy at the subscription holding the sandboxes:
az deployment sub create --location swedencentral \
  --template-file policy-deny-expensive-skus.bicep

# Create the service principal the platform will act through (master key — guard it):
az ad sp create-for-rbac --name "nixor-course-provisioner" \
  --role "Contributor" --scopes /subscriptions/<SUB_ID>
# Then also grant it "User Access Administrator" (to assign student roles) and the
# Microsoft Graph "User.Invite.All" permission (to invite guests). See CLAUDE.md.
```

## Provision one student
```bash
python provision_student.py --email amna@example.com --team team01
```

## Verify before the course
- `gpt-4o-mini` is available in your chosen region (`--location`).
- The `modelVersion` in main.bicep matches what's offered in that region.
- Re-running provisioning for the same team does not error (idempotency).
