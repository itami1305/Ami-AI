"""
Tách giao dịch từ đoạn chat (chat_session) — gửi Ollama local, nhận JSON, ghi CSV.

Luồng:
  1. Đóng gói thông tin đoạn chat (text OCR, ngày/giờ, người gửi, mốc thời gian).
  2. Gọi AI local (Ollama) — sửa chính tả OCR, tách từng giao dịch.
  3. Parse JSON → TransactionRecord.
  4. Ghi append vào file CSV trong exports/reconciliation/sessions/{session_id}/.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.config import DEFAULT_EXPORT_DIR, OLLAMA_MODEL
from backend.reconciliation.csv_export import append_transactions_csv
from backend.reconciliation.models import (
    ChatSegmentInfo,
    DetectTransactionRequest,
    LlmSplitResult,
    LlmTransactionItem,
    ParseSummaryRequest,
    SplitTransactionsRequest,
    SplitTransactionsResponse,
    TransactionRecord,
)
from backend.reconciliation.transaction_detector import (
    detect_transaction,
    make_dedupe_key,
    parse_summary_lines,
)

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

_SPLIT_SYSTEM_PROMPT = """Bạn là trợ lý trích xuất giao dịch chuyển khoản từ chat Zalo/Messenger (OCR có thể sai chính tả).
Nhiệm vụ:
- Đọc đoạn chat (có thể nhiều giao dịch dính một khối).
- Có ảnh chụp giao dịch được trích xuất từ OCR (có thể không rõ ràng).
- Sửa lỗi chính tả OCR hợp lý (VD: "Chuyen tlén" → "Chuyển tiền", "V" → "VND").
- Tách thành từng giao dịch riêng.
- CHỈ trả về một JSON hợp lệ, không markdown, không giải thích.

Schema JSON bắt buộc:
{
  "transactions": [
    {
      "transaction_date": "dd/mm/yyyy hoặc rỗng",
      "transaction_time": "HH:MM hoặc rỗng",
      "sender": "self|other|tên người",
      "direction": "in|out|unknown",
      "amount": "số có dấu phẩy nghìn, VD 1,050,000",
      "currency": "VND",
      "bank": "VCB|MB|TCB|NAPAS|...",
      "transaction_code": "FT... nếu có",
      "account_number": "",
      "beneficiary": "",
      "content": "mô tả đã sửa chính tả",
      "raw_text": "đoạn gốc tương ứng trong OCR",
      "confidence": 0.0-1.0
    }
  ],
  "notes": "ghi chú ngắn nếu không tách được GD nào"
}

Quy tắc:
- Không bịa số tiền/mã FT không có trong văn bản.
- Nếu không có giao dịch: "transactions": [].
- amount chỉ khi có số tiền rõ (kèm VND/+/- hoặc SMS ngân hàng).
"""


def _session_export_dir(session_id: str) -> Path:
    base = DEFAULT_EXPORT_DIR / "reconciliation" / "sessions" / session_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def _default_csv_path(session_id: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _session_export_dir(session_id) / f"transactions_llm_{stamp}.csv"


def _resolve_csv_path(req: SplitTransactionsRequest) -> Path:
    if req.csv_path:
        return Path(req.csv_path)
    session_dir = _session_export_dir(req.session_id)
    if req.append_csv:
        existing = sorted(session_dir.glob("transactions_llm_*.csv"))
        if existing:
            return existing[-1]
    return _default_csv_path(req.session_id)


def _new_tx_id(session_id: str, seq: int) -> str:
    day = datetime.now().strftime("%Y%m%d")
    return f"tx_{day}_{session_id[:8]}_{seq:03d}"


def _build_user_prompt(segment: ChatSegmentInfo, app_type: str) -> str:
    payload = {
        "app_type": app_type,
        "segment_id": segment.id,
        "chat_id": segment.chat_id,
        "chat_name": segment.chat_name,
        "date": segment.date,
        "time": segment.time,
        "role": segment.role,
        "sender": segment.sender,
        "marker_before": segment.marker_before,
        "marker_after": segment.marker_after,
        "member_count": segment.member_count,
        "ocr_text": segment.text,
    }
    return (
        "Phân tích đoạn chat sau và trả JSON theo schema đã cho:\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def extract_json_from_llm(text: str) -> dict:
    """Trích object JSON từ phản hồi Ollama (có thể bọc ```json)."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Ollama trả về nội dung rỗng.")

    block = _JSON_BLOCK_RE.search(raw)
    if block:
        raw = block.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])

    raise ValueError("Không parse được JSON từ phản hồi Ollama.")


async def _call_ollama_split(segment: ChatSegmentInfo, app_type: str) -> tuple[LlmSplitResult, dict]:
    from backend.chat.ollama_client import chat_completion

    user_prompt = _build_user_prompt(segment, app_type)
    # Prompt tách JSON — ghép system + user trong một message (chat_completion chỉ nhận user_message)
    combined = f"{_SPLIT_SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"
    content = await chat_completion(combined, history=None)

    raw_dict = extract_json_from_llm(content)
    parsed = LlmSplitResult.model_validate(raw_dict)
    return parsed, raw_dict


def _llm_items_to_records(
    items: list[LlmTransactionItem],
    *,
    req: SplitTransactionsRequest,
    segment: ChatSegmentInfo,
    excerpt: str,
) -> list[TransactionRecord]:
    now = datetime.now(timezone.utc).isoformat()
    records: list[TransactionRecord] = []
    message_id = segment.id or "segment"

    for idx, item in enumerate(items):
        if not (item.amount or item.transaction_code):
            continue
        date = item.transaction_date or segment.date
        dedupe = make_dedupe_key(
            item.bank,
            item.amount,
            item.transaction_code,
            date,
            segment.chat_id,
        )
        records.append(
            TransactionRecord(
                id=_new_tx_id(req.session_id, idx + 1),
                session_id=req.session_id,
                app_type=req.app_type,
                chat_id=segment.chat_id,
                chat_name=segment.chat_name,
                message_id=message_id,
                parent_message_id=message_id,
                line_index=idx,
                source_type="llm_chat_segment",
                transaction_date=date,
                transaction_time=item.transaction_time or segment.time,
                sender=item.sender or segment.sender or segment.role,
                direction=item.direction,
                amount=item.amount,
                currency=item.currency or "VND",
                bank=item.bank,
                transaction_code=item.transaction_code,
                account_number=item.account_number,
                beneficiary=item.beneficiary,
                content=item.content or item.raw_text,
                raw_text=item.raw_text or item.content,
                confidence=item.confidence,
                summary_excerpt=excerpt[:500] if excerpt else None,
                dedupe_key=dedupe,
                status="extracted",
                created_at=now,
            )
        )
    return records


def _fallback_rule_split(req: SplitTransactionsRequest) -> list[TransactionRecord]:
    """Fallback rule-based khi Ollama lỗi hoặc use_llm=False."""
    segment = req.segment
    text = (segment.text or "").strip()
    if not text:
        return []

    sender = segment.sender or segment.role
    time_hint = segment.date or segment.time
    parsed = parse_summary_lines(
        ParseSummaryRequest(
            text=text,
            sender=sender,
            time=time_hint,
            message_id=segment.id,
        )
    )
    if parsed.records:
        for i, rec in enumerate(parsed.records):
            rec.session_id = req.session_id
            rec.app_type = req.app_type
            rec.chat_id = segment.chat_id
            rec.chat_name = segment.chat_name
            rec.id = _new_tx_id(req.session_id, i + 1)
            rec.source_type = "rule_chat_segment"
        return parsed.records

    det = detect_transaction(
        DetectTransactionRequest(text=text, sender=sender, time=time_hint)
    )
    if not det.is_transaction:
        return []

    now = datetime.now(timezone.utc).isoformat()
    return [
        TransactionRecord(
            id=_new_tx_id(req.session_id, 1),
            session_id=req.session_id,
            app_type=req.app_type,
            chat_id=segment.chat_id,
            chat_name=segment.chat_name,
            message_id=segment.id,
            parent_message_id=segment.id,
            source_type="rule_chat_segment",
            transaction_date=segment.date,
            transaction_time=segment.time,
            sender=det.sender or sender,
            amount=det.amount,
            bank=det.bank,
            transaction_code=det.transaction_code,
            account_number=det.account_number,
            content=det.content,
            raw_text=text,
            summary_excerpt=text[:500],
            dedupe_key=make_dedupe_key(det.bank, det.amount, det.transaction_code, segment.date, segment.chat_id),
            status="extracted",
            created_at=now,
        )
    ]


async def split_chat_transactions(req: SplitTransactionsRequest) -> SplitTransactionsResponse:
    """
    Tách giao dịch từ đoạn chat → Ollama JSON → TransactionRecord → CSV (tùy chọn).
    """
    segment = req.segment
    text = (segment.text or "").strip()
    if not text:
        return SplitTransactionsResponse(
            success=True,
            model=OLLAMA_MODEL,
            transaction_count=0,
            transactions=[],
            error="Đoạn chat rỗng.",
        )

    raw_llm_json: dict | None = None
    records: list[TransactionRecord] = []
    error: str | None = None

    if req.use_llm:
        try:
            llm_result, raw_llm_json = await _call_ollama_split(segment, req.app_type)
            records = _llm_items_to_records(
                llm_result.transactions,
                req=req,
                segment=segment,
                excerpt=text,
            )
            if not records and llm_result.notes:
                error = llm_result.notes
        except Exception as exc:
            logger.warning("LLM split failed, fallback rules: %s", exc)
            error = str(exc)
            records = _fallback_rule_split(req)
    else:
        records = _fallback_rule_split(req)

    # Re-number ids sequentially
    for i, rec in enumerate(records):
        rec.id = _new_tx_id(req.session_id, i + 1)

    csv_path: str | None = None
    if req.save_csv and records:
        path = _resolve_csv_path(req)
        append_transactions_csv(path, records)
        csv_path = str(path.resolve())

    return SplitTransactionsResponse(
        success=bool(records) or error is None,
        model=OLLAMA_MODEL if req.use_llm else "",
        transaction_count=len(records),
        transactions=records,
        csv_path=csv_path,
        raw_llm_json=raw_llm_json,
        error=error if not records else None,
    )
