"""
Study Coach (Polished) — Nixor AI + Cloud Course (Day 4)
========================================================

The Day 2 app, polished like an engineer would before a demo:
  • streaming replies (text appears live, not after a long pause)
  • graceful error handling (the app never shows a raw crash)
  • a "New conversation" reset button
  • a clear footer telling users what it runs on

Same deploy flow as every other app — one click in the Deploy panel.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

APP_TITLE = "O/A-Level Study Coach"
SYSTEM_PROMPT = (
    "You are a patient, encouraging study coach for O/A-level students in Karachi. "
    "Explain simply, use one local example, and never just hand over full answers — "
    "guide the student to the answer themselves."
)

_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
_api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
client = AzureOpenAI(
    api_key=_api_key,
    azure_endpoint=_endpoint,
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
)
DEPLOYMENT = os.environ.get("MODEL_GPT55_DEPLOYMENT", "gpt-5-5")


def stream_reply(messages: list[dict]):
    """Yield the AI's answer piece by piece so the page feels alive."""
    stream = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=messages,
        temperature=1,
        max_completion_tokens=700,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


st.set_page_config(page_title=APP_TITLE, page_icon="📚")
st.title(APP_TITLE)

with st.sidebar:
    if st.button("🔄 New conversation"):
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    st.caption("Runs on GPT-5.5, hosted on Microsoft Azure.")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

for msg in st.session_state.messages:
    if msg["role"] != "system":
        st.chat_message(msg["role"]).write(msg["content"])

if user_text := st.chat_input("Ask me anything about your subject..."):
    # Reliability guard #1: ignore empty / whitespace-only input.
    if not user_text.strip():
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_text})
    st.chat_message("user").write(user_text)

    with st.chat_message("assistant"):
        # Reliability guard #2: if the API call fails, show a friendly message
        # instead of a red Python traceback.
        try:
            reply = st.write_stream(stream_reply(st.session_state.messages))
        except Exception:
            reply = "⚠️ Sorry — the AI is unavailable right now. Please try again in a moment."
            st.error(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
