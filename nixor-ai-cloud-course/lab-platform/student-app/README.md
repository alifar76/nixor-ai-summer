# Your AI App

This is the app you'll build and deploy during the course.

## Run it locally / in Codespaces
```bash
cp .env.example .env     # then fill in your sandbox values
pip install -r requirements.txt
streamlit run app.py
```

## Deploy it to your Azure sandbox (Session 3)
Your sandbox already has a Web App waiting. From this folder:
```bash
az webapp up --name <your-web-app-name> --resource-group rg-nixor-<your-team>
```
Then set your secrets as App Settings (so they're never in your code):
```bash
az webapp config appsettings set \
  --name <your-web-app-name> --resource-group rg-nixor-<your-team> \
  --settings AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_API_KEY=... \
             AZURE_OPENAI_DEPLOYMENT=gpt-5-5 WEBSITES_PORT=8000
```

The course website walks you through all of this — you won't have to memorise it.

## Multi-model playground
The platform injects a 6-model Azure Foundry catalog into your environment:
`gpt-5.5`, `grok-4.3`, `DeepSeek-V4-Pro`, `mistral-medium-3-5`, `FLUX.2-pro`, `sora-2`.
Use `AZURE_FOUNDRY_ENDPOINT`, `AZURE_FOUNDRY_API_KEY`, and the `MODEL_*_DEPLOYMENT`
variables from `.env` to build your own text/image/video experiments.
