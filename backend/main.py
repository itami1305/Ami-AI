"""
# Backend FastAPI — Entry point
Chạy: uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.reconciliation import router as reconciliation_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Khởi động/tắt backend — plan worker kích hoạt theo phiên qua API."""
    yield


app = FastAPI(
    title="Ami-AI Backend",
    description="API Chat (Ollama) + Reconciliation đối soát",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(reconciliation_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ami-ai-backend"}
