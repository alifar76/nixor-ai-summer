# Session 3 — Deploy Your App to a Real Server

**Goal:** ship your custom AI app to a live public URL on a cloud VM — the same way real engineers deploy software.

## Big ideas for today

- **A server is just a computer that runs your code 24/7** — instead of your laptop, it's a VM in an Azure data centre.
- **Docker containers** let you package your app and its dependencies so they run identically everywhere: your laptop, a VM, a data centre rack.
- **Ports and URLs** are how the public reaches your running process. Port 8000 on your container → a public URL your friends can open.
- **Logs are your eyes** into a running server. When something breaks, `docker logs` tells you what happened.

## How it works today

Your app runs on a dedicated cluster of 5 Azure VMs managed by the course platform. Each student gets a fixed port on one of those VMs. When you click **Deploy**:

1. Your workspace is zipped and sent to your assigned VM.
2. A Docker image is built from your code on that VM.
3. A container starts, listening on your port.
4. A public URL appears — that's your live app.

This is the real deployment model: code → image → running container → public URL.

## Steps

1. **Customise your app** (from Session 2). Make sure `app.py` runs locally in the terminal:
   ```
   cd /workspace
   streamlit run app.py --server.port 8501
   ```
2. **Check `requirements.txt`** lists every package your app imports. Missing packages = failed build.
3. **Click Deploy** in the left panel. Watch the build log — this is Docker building your image live on the server.
4. **Open your live URL** when the deploy finishes. Share it with someone else in the room.
5. **Read the logs** — in your terminal, run:
   ```
   # The platform instructor can show you this, or use the terminal:
   echo "Your app is on node $NODE — ask instructor for: docker logs student-<yourslug>"
   ```
6. **Break something on purpose**: add a syntax error to `app.py`, deploy again, watch the build fail in the log. Fix it and redeploy successfully.
7. **Measure latency**: send 3 prompts, note the response time. Is it faster or slower than your local run? Why?

## Starter track
- Deploy successfully and open your live URL.
- Fix one issue you find after deploying.

## Stretch track
- Look at the `student.Dockerfile` that gets injected into your build (ask instructor). Can you write a better one?
- What happens if two students have a naming conflict? How would you prevent it in a real system?
- Document one reliability risk and one cost risk of this architecture.

## Concepts you just used

| Concept | Where you saw it |
|---|---|
| Virtual Machine | The Azure VM your app is running on |
| Docker image | Built from your code during deploy |
| Docker container | The running process; has its own filesystem and network |
| Port | 8000 inside the container → your public port on the VM |
| Public IP | The VM's address; your URL uses it |
| Build log | Streaming output of `docker build` |
| Environment variable | AZURE_OPENAI_* injected at container start, not baked into the image |

## You learned
Production deployment isn't magic — it's your code in a container on a computer in a data centre, with a port number the internet can reach.
