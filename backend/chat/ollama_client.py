"""
# Client gọi Ollama (model gemma4:e2b)
Hỗ trợ chat completion thường + streaming chunk.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from backend.chat.prompt_builder import build_messages, build_ollama_payload
from backend.config import HTTP_TIMEOUT, OLLAMA_BASE_URL, OLLAMA_MODEL


class OllamaError(Exception):
    """Lỗi khi gọi Ollama."""


def _ollama_url() -> str:
    return f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"


async def chat_completion(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> str:
    """
    # Gọi Ollama chat API (non-stream), trả nội dung assistant
    """
    model_name = model or OLLAMA_MODEL
    messages = build_messages(user_message, history)
    payload = build_ollama_payload(messages, model_name, stream=False)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.post(_ollama_url(), json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Không kết nối được Ollama: {exc}") from exc

    data = response.json()
    content = (data.get("message") or {}).get("content", "").strip()

    if not content:
        raise OllamaError("Ollama trả về nội dung rỗng.")

    return content


async def chat_completion_stream(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """
    # Gọi Ollama chat API ở chế độ streaming
    Yield từng đoạn text (chunk) khi Ollama emit ra. Kết thúc khi `done=true`.
    """
    model_name = model or OLLAMA_MODEL
    messages = build_messages(user_message, history)
    payload = build_ollama_payload(messages, model_name, stream=True)

    timeout = httpx.Timeout(HTTP_TIMEOUT, read=None)  # read=None: stream giữ kết nối
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", _ollama_url(), json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="ignore")
                    raise OllamaError(
                        f"Ollama trả mã {resp.status_code}: {body[:300]}"
                    )

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    chunk = (data.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        return
    except httpx.HTTPError as exc:
        raise OllamaError(f"Không kết nối được Ollama: {exc}") from exc
