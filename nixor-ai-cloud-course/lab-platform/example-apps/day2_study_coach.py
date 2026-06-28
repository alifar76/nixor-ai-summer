"""
Study Coach — Nixor AI + Cloud Course (Day 2)
=============================================

A *purposeful* AI product, not just a chatbot: the user picks a MODE, and the AI
does a specific job for that mode. This is the Day 2 lesson in one file — prompt
design IS product design.

Make it yours: change APP_TITLE and the three prompts in MODES below.
Deploy it exactly like the starter app (Deploy panel → one click).
"""

import os

import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# 1. Your product: a name and a set of "jobs" the AI can do.
#    Each mode is just a different system prompt = a different job description.
# ---------------------------------------------------------------------------
APP_TITLE = "O/A-Level Study Coach"  # 👈 EDIT THIS

MODES = {
    "Explain simply": (  # 👈 EDIT THESE PROMPTS
        "You are a patient tutor for O/A-level students in Karachi. Explain the "
        "concept in plain language with ONE everyday example. Keep it under 150 words."
    ),
    "Quiz me": (
        "You are a quizmaster. Ask the student ONE multiple-choice question on their "
        "topic, wait for their answer, then say if they're right and explain why. "
        "Only one question at a time."
    ),
    "Summarise my notes": (
        "You turn a student's messy notes into 5 clean bullet points plus a one-line "
        "summary at the end."
    ),
}

# ---------------------------------------------------------------------------
# 2. Connect to GPT-5.5 on Azure. These values come from your sandbox; locally
#    they're read from .env, in the cloud they're set as environment variables.
# ---------------------------------------------------------------------------
_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
_api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
client = AzureOpenAI(
    api_key=_api_key,
    azure_endpoint=_endpoint,
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
)
DEPLOYMENT = os.environ.get("MODEL_GPT55_DEPLOYMENT", "gpt-5-5")


def ask_the_ai(messages: list[dict]) -> str:
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=messages,
        temperature=1,
        max_completion_tokens=600,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# 3. The web page.
# ---------------------------------------------------------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="📚")
st.title(APP_TITLE)

mode = st.sidebar.radio("What do you need?", list(MODES.keys()))
st.sidebar.caption("Switching mode starts a fresh conversation.")

# When the mode changes, reset the conversation with that mode's system prompt.
if st.session_state.get("mode") != mode:
    st.session_state.mode = mode
    st.session_state.messages = [{"role": "system", "content": MODES[mode]}]

for msg in st.session_state.messages:
    if msg["role"] != "system":
        st.chat_message(msg["role"]).write(msg["content"])

if user_text := st.chat_input("Type your topic or question..."):
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.chat_message("user").write(user_text)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = ask_the_ai(st.session_state.messages)
        st.write(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
