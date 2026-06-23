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
             AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini WEBSITES_PORT=8000
```

The course website walks you through all of this — you won't have to memorise it.
