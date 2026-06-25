# Your AI App

This is the app you'll build and customize during the course.

## Run it locally / in the platform terminal

Your sandbox already has all environment variables set. Inside the platform terminal:

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

## Deploy to the VM Cluster (Session 3)

There are no Azure Web Apps or GitHub Actions to configure. Deployment is one click:

1. Open the **Deploy** tab in the platform UI.
2. Click **Deploy App** — your code is zipped and sent to your assigned VM node.
3. Docker builds an image from your `app.py`, then starts a container on your
   reserved port.
4. A public URL appears: `http://nixornode-N.eastus.cloudapp.azure.com:PORT/`

That's it. Every push of **Deploy App** rebuilds from your latest saved code.

> **Why this matters:** This is real cloud deployment — your code runs in a Docker
> container on a Linux server in Microsoft Azure's East US data centre. The same
> pattern (containerise → push → run) is used by every major tech company.

## Multi-model playground

The platform injects a 4-model Azure AI Foundry catalog into your environment.
Each model has its own deployment and env var:

| Model               | Env var                         | Deployment      |
|---------------------|---------------------------------|-----------------|
| GPT-5.5             | `MODEL_GPT55_DEPLOYMENT`        | `gpt-5-5`       |
| Grok-4.3            | `MODEL_GROK43_DEPLOYMENT`       | `xai-grok43`    |
| DeepSeek-V4-Pro     | `MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT` | `ds-v4pro`   |
| mistral-medium-3-5  | `MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT` | `mstr-med35` |

Use `AZURE_FOUNDRY_ENDPOINT` and `AZURE_FOUNDRY_API_KEY` from your environment to
call these. See `compare_models.py` for a working example.
