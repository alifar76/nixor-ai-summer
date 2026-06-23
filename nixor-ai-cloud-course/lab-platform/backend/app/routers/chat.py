"""AI coding-helper chatbot, proxied to an Azure AI Foundry (Azure OpenAI) model.

Streams tokens to the browser as Server-Sent Events so the chat feels live.
The model's API key never reaches the browser — the backend holds it and proxies.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..config import settings
from ..models import ChatRequest, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

SYSTEM_PROMPT = (
    "You are a friendly coding tutor inside a learning platform for A-level students "
    "(ages 16-18) at Nixor College who are new to programming and the cloud. They are "
    "building and deploying an AI app on Microsoft Azure across a 4-session course. "
    "Explain simply, avoid jargon (or define it), give short runnable code, and never "
    "just dump a full solution — nudge them toward understanding. When they share code "
    "or an error, point at the specific line and explain the fix. Keep answers concise."
)


def _chat_url() -> str:
    base = settings.azure_openai_endpoint.rstrip("/")
    return (
        f"{base}/openai/deployments/{settings.azure_openai_deployment}"
        f"/chat/completions?api-version={settings.azure_openai_api_version}"
    )


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(get_current_user)):
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI is not configured yet. Set AZURE_OPENAI_ENDPOINT and API key.",
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if body.context.strip():
        messages.append(
            {"role": "system", "content": f"The student is currently looking at:\n{body.context[:4000]}"}
        )
    messages += [{"role": m.role, "content": m.content} for m in body.messages]

    payload = {"messages": messages, "stream": True, "temperature": 0.4, "max_tokens": 800}
    headers = {"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"}

    async def event_stream():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                async with client.stream("POST", _chat_url(), json=payload, headers=headers) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "replace")[:500]
                        logger.warning("Azure chat error %s: %s", resp.status_code, detail)
                        yield _sse({"error": f"AI error ({resp.status_code})"})
                        return
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {}).get("content")
                        if delta:
                            yield _sse({"delta": delta})
        except httpx.HTTPError as exc:
            logger.warning("Chat upstream failed: %s", exc)
            yield _sse({"error": "Could not reach the AI service."})
        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
