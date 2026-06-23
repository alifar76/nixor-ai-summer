#!/usr/bin/env bash
# App Service runs this to start the app. Streamlit must bind to 0.0.0.0 and the
# port Azure expects (set via WEBSITES_PORT app setting, default 8000).
python -m streamlit run app.py --server.port "${PORT:-8000}" --server.address 0.0.0.0
