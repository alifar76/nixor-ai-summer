"""
Model Playground — Nixor AI + Cloud Course (Day 4 stretch)
==========================================================

Send one prompt to any of your 4 sandbox models and compare the answers in the
browser. The teaching point: not every model lives in the same place.

  • GPT-5.5            → your Azure OpenAI resource   (AZURE_OPENAI_* env vars)
  • Grok-4.3           → your Foundry resource         (AZURE_FOUNDRY_* env vars)
  • DeepSeek-V4-Pro    → your Foundry resource
  • Mistral-Medium-3.5 → your Foundry resource

Each model carries its own (deployment, endpoint, key) so the request always
goes to the resource that actually hosts it.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

OPENAI_EP = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
OPENAI_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
FOUNDRY_EP = os.environ.get("AZURE_FOUNDRY_ENDPOINT", "")
FOUNDRY_KEY = os.environ.get("AZURE_FOUNDRY_API_KEY", "")
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

# label -> (deployment name, endpoint, api key)
MODELS = {
    "GPT-5.5": (os.environ.get("MODEL_GPT55_DEPLOYMENT", "gpt-5-5"), OPENAI_EP, OPENAI_KEY),
    "Grok-4.3": (os.environ.get("MODEL_GROK43_DEPLOYMENT", "xai-grok43"), FOUNDRY_EP, FOUNDRY_KEY),
    "DeepSeek-V4-Pro": (os.environ.get("MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT", "ds-v4pro"), FOUNDRY_EP, FOUNDRY_KEY),
    "Mistral-Medium-3.5": (os.environ.get("MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT", "mstr-med35"), FOUNDRY_EP, FOUNDRY_KEY),
}

st.set_page_config(page_title="Model Playground", page_icon="🧪")
st.title("🧪 Model Playground")
st.caption("One prompt, four models. Notice how style, speed, and depth differ.")

choice = st.selectbox("Pick a model", list(MODELS.keys()))
prompt = st.text_area(
    "Your prompt",
    "Explain what a neural network is in exactly 3 sentences, for a 16-year-old.",
)

if st.button("Run"):
    deployment, endpoint, key = MODELS[choice]
    if not endpoint or not key:
        st.error("This model's endpoint or key isn't set in your environment.")
        st.stop()

    client = AzureOpenAI(api_key=key, azure_endpoint=endpoint, api_version=API_VERSION)
    with st.spinner(f"Asking {choice}…"):
        try:
            resp = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
                max_completion_tokens=400,
            )
            answer = resp.choices[0].message.content
        except Exception as exc:
            st.error(f"{choice} could not answer: {exc}")
            st.stop()

    st.markdown(f"**{choice} says:**")
    st.write(answer)
