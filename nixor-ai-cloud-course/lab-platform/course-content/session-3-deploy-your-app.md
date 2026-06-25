# Session 3 — Ship It: Real Cloud Deployment

**Goal:** push your custom AI app to a public URL on a real Azure VM — the same way
engineers ship software at scale.

---

## What you're deploying to

You are not deploying to a simulated environment. There is a cluster of **3 Azure VMs**
(16 vCPU / 64 GB each) running in Microsoft's East US data centre. Every student gets a
reserved slot: one specific VM and one specific port number, assigned at signup.

```
┌──────────────────────── Nixor AI Cluster (Azure East US) ──────────────────────────┐
│                                                                                      │
│  nixornode-1.eastus.cloudapp.azure.com     nixornode-2   nixornode-3                │
│  ┌──────────────────────┐                  ┌──────┐      ┌──────┐                  │
│  │ student-ali    :9000 │◄── your browser  │ ...  │      │ ...  │                  │
│  │ student-sara   :9001 │                  │ ...  │      │ ...  │                  │
│  │ student-hamza  :9002 │                  └──────┘      └──────┘                  │
│  │ ...            :...  │                                                            │
│  └──────────────────────┘                                                            │
│         VM (16 vCPU / 64 GB)                                                        │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Your URL will look like: `http://nixornode-2.eastus.cloudapp.azure.com:9004`

Break it down:
- **`nixornode-2`** — the DNS label we assigned to this VM in Azure
- **`.eastus.cloudapp.azure.com`** — free Azure-managed subdomain, no domain purchase needed
- **`:9004`** — your port, reserved only for you

---

## How the deploy pipeline works

When you click **Deploy**, here is exactly what happens — nothing is hidden:

```
Your editor → ZIP → Upload to VM → docker build → docker run -p 9004:8501 → Public URL
```

**Step 1 — Zip** 
The platform zips everything in your `/workspace` folder (your `app.py`,
`requirements.txt`, etc.).

**Step 2 — Send to VM** 
The ZIP is sent over HTTPS to a small agent process running on your assigned VM
(port 8080, protected so only the platform server can reach it).

**Step 3 — Docker build** 
On the VM, Docker reads your `requirements.txt` and builds an image. You will see the
output live in the build log — this is real `docker build` output.

**Step 4 — Start container** 
Docker starts a container from that image. The agent runs:
```
docker run -d --name student-<yourslug> \
  -p 9004:8501 \
  -e AZURE_OPENAI_ENDPOINT=... \
  -e AZURE_OPENAI_KEY=... \
  student-<yourslug>:latest
```
Your Azure keys are injected as environment variables at runtime — they are **never
baked into the image**.

**Step 5 — Public URL** 
Port 9004 on the VM is open to the internet. Your container is listening on it.
Anyone with your URL can reach your app.

---

## Steps for today

1. **Customise your app** from Session 2. Confirm it works in your in-browser terminal:
   ```
   streamlit run app.py --server.port 8501
   ```

2. **Check `requirements.txt`** lists every package your `app.py` imports.
   Missing packages = failed Docker build. Add them now, not after deploy.

3. **Click Deploy** in the Deploy panel (left column). Watch the build log stream in
   real time. This is the same output you would see running `docker build` yourself.

4. **Open your URL** when the green "Your app is live" card appears.
   Copy the URL and paste it to the class WhatsApp group.

5. **Read your logs** — ask your instructor to run on the VM:
   ```
   docker logs student-<yourslug> --tail 50
   ```
   Get comfortable reading logs: they are your only window into a running server.

6. **Break something on purpose.** Add a Python syntax error to `app.py`, hit Deploy,
   and watch the build fail. Fix it, redeploy, succeed. This is a core skill.

7. **Measure latency.** Send 3 prompts. Is the response time faster or slower than your
   local run in Session 1? Why? (Hint: think about where the Azure OpenAI endpoint is.)

---

## Starter track
- Deploy successfully and share your live URL.

## Stretch track
- Open the `student.Dockerfile` (ask instructor to show you). Could you write a leaner
  version? What layers would you combine?
- What happens if you deploy twice? Does the old container keep running?
  Run `docker ps` on your VM (ask instructor) and check.
- What is the difference between the *image* and the *container*? Write one sentence for
  each in your own words.
- Document one reliability risk and one cost risk of running 50 student apps on 3 shared VMs.

---

## Concepts you just used

| Concept | Where you saw it |
|---|---|
| Virtual Machine | The Azure VM your container is running on |
| Docker image | Built from your code during deploy; immutable snapshot |
| Docker container | The running instance of your image; has its own process and filesystem |
| Port mapping | `-p 9004:8501` maps your public port → Streamlit's internal port |
| DNS label | `nixornode-2.eastus.cloudapp.azure.com` — how the internet finds your VM |
| Environment variable | Your Azure keys injected at `docker run`, not stored in the image |
| Build log | Live output of `docker build`; your first debugging tool |
| Deploy agent | The small HTTP server on each VM that receives builds and manages containers |

---

## The real takeaway

Production deployment is not magic. It is:

> **Your code** → **packaged as a container image** → **running on a computer in a data
> centre** → **a port the internet can reach**.

Every deployment platform (Azure App Service, AWS ECS, Google Cloud Run, Heroku) is just
a managed version of exactly what you did today.
