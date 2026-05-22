"""
Phân tích & đối soát batch — §10.8. Rule merge + tóm tắt; LLM khi có Ollama.
"""

from __future__ import annotations

import json
import logging

from backend.reconciliation.dedupe_service import build_warnings, merge_by_dedupe
from backend.reconciliation.models import AnalyzeRequest, AnalyzeResponse, TransactionRecord

logger = logging.getLogger(__name__)


def _rule_summary(merged: list[TransactionRecord], warnings_count: int) -> str:
    n = len(merged)
    dup = sum(1 for r in merged if r.is_duplicate)
    parts = [f"Phiên có {n} giao dịch sau gộp trùng."]
    if dup:
        parts.append(f"{dup} bản ghi trùng nguồn A↔B đã đánh dấu.")
    if warnings_count:
        parts.append(f"{warnings_count} cảnh báo cần rà soát.")
    return " ".join(parts)


async def _llm_summary(merged: list[TransactionRecord], warnings: list) -> str | None:
    try:
        from backend.chat.ollama_client import OllamaError, chat_completion
    except ImportError:
        return None

    payload = {
        "transactions": [t.model_dump() for t in merged[:50]],
        "warnings": [w.model_dump() for w in warnings],
    }
    prompt = (
        "Bạn là trợ lý kế toán. Dựa JSON giao dịch đối soát chat (Zalo/Messenger), "
        "viết tóm tắt tiếng Việt ngắn gọn (3–6 câu): tổng số GD, trùng lặp, cảnh báo.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        return await chat_completion(prompt, history=None)
    except OllamaError as exc:
        logger.warning("Ollama analyze: %s", exc)
        return None


async def analyze_session(req: AnalyzeRequest) -> AnalyzeResponse:
    records = list(req.transactions)
    merged = merge_by_dedupe(records)
    warnings = build_warnings(records)

    summary = _rule_summary(merged, len(warnings))
    llm = await _llm_summary(merged, warnings)
    if llm:
        summary = llm

    return AnalyzeResponse(
        merged_transactions=merged,
        warnings=warnings,
        summary_vi=summary,
    )
