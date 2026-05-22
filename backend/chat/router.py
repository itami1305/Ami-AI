"""
# API Router — Module Chat
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.chat.ollama_client import OllamaError, chat_completion, chat_completion_stream
from backend.config import OLLAMA_MODEL

router = APIRouter(prefix="/chat", tags=["Chat"])


# --- Schema request/response ---
class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Tin nhắn người dùng")
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    model: str


@router.post("/completions", response_model=ChatResponse)
async def completions(body: ChatRequest) -> ChatResponse:
    """
    # Endpoint chat (non-stream)
    Giữ nguyên cho compatibility với code cũ.
    """
    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]

    try:
        reply = await chat_completion(body.message, history_dicts)
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(reply=reply, model=OLLAMA_MODEL)


@router.post("/stream")
async def stream(body: ChatRequest) -> StreamingResponse:
    """
    # Endpoint chat streaming (NDJSON)
    Mỗi dòng là 1 object JSON:
      - `{"chunk": "..."}` — đoạn text mới
      - `{"done": true, "model": "..."}` — kết thúc
      - `{"error": "..."}` — lỗi (chỉ phát 1 lần, sau đó kết thúc)
    """
    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]

    async def gen():
        try:
            async for chunk in chat_completion_stream(body.message, history_dicts):
                yield json.dumps({"chunk": chunk}, ensure_ascii=False) + "\n"
            yield json.dumps({"done": True, "model": OLLAMA_MODEL}) + "\n"
        except OllamaError as exc:
            yield json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001 — chuyển toàn bộ lỗi vào stream
            yield json.dumps({"error": f"Lỗi nội bộ: {exc}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
