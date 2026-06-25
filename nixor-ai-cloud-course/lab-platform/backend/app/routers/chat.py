"""AI coding-helper chatbot, proxied to an Azure AI Foundry (Azure OpenAI) model.

Streams tokens to the browser as Server-Sent Events so the chat feels live.
The model's API key never reaches the browser — the backend holds it and proxies.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..config import settings
from ..models import AIModelInfo, ChatRequest, User

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
_MAX_HISTORY_MESSAGES = 8
_MAX_MESSAGE_CHARS = 2000
_MAX_CONTEXT_CHARS = 2000
_MAX_RETRIES_ON_429 = 2


def _chat_endpoint() -> str:
    """Prefer the Foundry endpoint (all 4 catalog models live there); fall back to the
    classic Azure OpenAI endpoint so existing deployments keep working."""
    return (settings.azure_foundry_endpoint or settings.azure_openai_endpoint).rstrip("/")


def _chat_api_key() -> str:
    return settings.azure_foundry_api_key or settings.azure_openai_api_key


def _chat_url(deployment: str) -> str:
    base = _chat_endpoint()
    return (
        f"{base}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={settings.azure_openai_api_version}"
    )


@router.get("/ai/models")
def ai_models(user: User = Depends(get_current_user)):
    _ = user
    models = [AIModelInfo(**m).model_dump() for m in settings.ai_models()]
    return {"models": models, "default_model_id": settings.chat_default_model_id}


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(get_current_user)):
    _ = user
    # The in-app coding tutor runs on the dedicated chat deployment (GPT-5.5). A request
    # may still name a model; we only honour it if it's a chat-eligible Azure OpenAI entry
    # in the catalog. Otherwise (the normal case — the 4-model catalog is deploy-only) we
    # fall back to the dedicated chat deployment rather than rejecting the request.
    selected_id = (body.model_id or settings.chat_default_model_id).strip()
    selected = next(
        (
            m
            for m in settings.ai_models()
            if m.get("id") == selected_id
            and m.get("provider") == "azure_openai"
            and m.get("chat_eligible", False)
        ),
        None,
    )
    deployment = str((selected or {}).get("model") or settings.azure_openai_deployment).strip()
    if not deployment:
        raise HTTPException(status_code=503, detail="Azure chat deployment is not configured.")
    if not _chat_endpoint() or not _chat_api_key():
        raise HTTPException(
            status_code=503,
            detail="AI is not configured yet. Set AZURE_FOUNDRY_ENDPOINT/AZURE_OPENAI_ENDPOINT and the matching API key.",
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if body.context.strip():
        messages.append(
            {"role": "system", "content": f"The student is currently looking at:\n{body.context[:_MAX_CONTEXT_CHARS]}"}
        )
    for m in body.messages[-_MAX_HISTORY_MESSAGES:]:
        content = (m.content or "").strip()
        if not content:
            continue
        messages.append({"role": m.role, "content": content[:_MAX_MESSAGE_CHARS]})

    payload = {
        "messages": messages,
        "stream": True,
        "max_completion_tokens": 350,
    }
    headers = {"api-key": _chat_api_key(), "Content-Type": "application/json"}

    async def event_stream():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                for attempt in range(_MAX_RETRIES_ON_429 + 1):
                    async with client.stream("POST", _chat_url(deployment), json=payload, headers=headers) as resp:
                        if resp.status_code == 429:
                            detail = (await resp.aread()).decode("utf-8", "replace")[:500]
                            logger.warning("Azure chat rate-limited (attempt %s): %s", attempt + 1, detail)
                            if attempt >= _MAX_RETRIES_ON_429:
                                yield _sse(
                                    {"error": "AI is busy right now (rate limit). Wait ~10 seconds and try again."}
                                )
                                return
                            retry_after = resp.headers.get("retry-after", "").strip()
                            try:
                                wait_s = float(retry_after)
                            except ValueError:
                                wait_s = 1.5 * (attempt + 1)
                            await asyncio.sleep(max(0.5, min(wait_s, 8.0)))
                            continue
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
                        return
        except httpx.HTTPError as exc:
            logger.warning("Chat upstream failed: %s", exc)
            yield _sse({"error": "Could not reach the AI service."})
        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
