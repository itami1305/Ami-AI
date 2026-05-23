"""Trích xuất TransactionRecord — nguồn A/B (§10)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable

from app.logic.reconciliation.models import CaptureAppType, SourceType, TransactionRecord
from backend.transaction_money import strict_money_line_match

SUMMARY_KEYWORDS = (
    "tổng hợp",
    "danh sách giao dịch",
    "báo cáo",
    "giao dịch ngày",
)

NUMBERED_LINE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)


def make_dedupe_key(bank: str, amount: str, code: str, date: str, chat_id: str) -> str:
    parts = [
        (bank or "").lower(),
        re.sub(r"[^\d]", "", amount or ""),
        (code or "").upper(),
        date or "",
        chat_id or "",
    ]
    return "|".join(parts)


def is_summary_message(text: str) -> bool:
    if not text or len(text) < 20:
        return False
    low = text.lower()
    if any(kw in low for kw in SUMMARY_KEYWORDS):
        return True
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    amount_lines = sum(1 for ln in lines if strict_money_line_match(ln))
    return amount_lines >= 2 or bool(NUMBERED_LINE.search(text))


def split_summary_lines(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return [text.strip()] if text.strip() else []
    numbered = [ln for ln in lines if NUMBERED_LINE.match(ln) or strict_money_line_match(ln)]
    return numbered if len(numbered) >= 2 else lines


def new_tx_id(session_id: str, seq: int) -> str:
    day = datetime.now().strftime("%Y%m%d")
    return f"tx_{day}_{session_id[:8]}_{seq:03d}"


def build_record(
    *,
    tx_id: str,
    session_id: str,
    app_type: CaptureAppType,
    chat_id: str,
    chat_name: str,
    message_id: str,
    source_type: SourceType,
    amount: str,
    parent_message_id: str = "",
    line_index: int | None = None,
    transaction_date: str = "",
    transaction_time: str = "",
    sender: str = "",
    bank: str = "",
    transaction_code: str = "",
    account_number: str = "",
    beneficiary: str = "",
    content: str = "",
    raw_text: str = "",
    transfer_image_path: str | None = None,
    summary_excerpt: str | None = None,
    screenshot_path: str = "",
) -> TransactionRecord:
    dedupe = make_dedupe_key(bank, amount, transaction_code, transaction_date, chat_id)
    now = datetime.now(timezone.utc).isoformat()
    return TransactionRecord(
        id=tx_id,
        session_id=session_id,
        app_type=app_type,
        chat_id=chat_id,
        chat_name=chat_name,
        message_id=message_id,
        parent_message_id=parent_message_id or message_id,
        line_index=line_index,
        source_type=source_type,
        transaction_date=transaction_date,
        transaction_time=transaction_time,
        sender=sender,
        amount=amount,
        bank=bank,
        transaction_code=transaction_code,
        account_number=account_number,
        beneficiary=beneficiary,
        content=content,
        raw_text=raw_text,
        transfer_image_path=transfer_image_path,
        summary_excerpt=summary_excerpt,
        screenshot_path=screenshot_path,
        dedupe_key=dedupe,
        created_at=now,
    )


def records_from_transaction_results(
    results: list,
    *,
    sender: str,
    msg_date: str,
    msg_time: str,
    state,
    message_id: str,
    source_type: SourceType,
    raw_text: str = "",
    summary_excerpt: str | None = None,
) -> list[TransactionRecord]:
    """Map danh sách TransactionResult → TransactionRecord (nhiều GD / đoạn chat)."""
    records: list[TransactionRecord] = []
    for idx, det in enumerate(results):
        if hasattr(det, "model_dump"):
            tx = det.model_dump()
        elif isinstance(det, dict):
            tx = det
        else:
            continue
        if not tx.get("is_transaction"):
            continue
        seq = state.transaction_count + len(records) + 1
        records.append(
            build_record(
                tx_id=new_tx_id(state.session_id, seq),
                session_id=state.session_id,
                app_type=state.app_type,
                chat_id=state.current_chat_id,
                chat_name=state.current_chat_name,
                message_id=message_id,
                source_type=source_type,
                amount=tx.get("amount", ""),
                parent_message_id=message_id,
                line_index=idx,
                transaction_date=tx.get("date") or msg_date or "",
                transaction_time=tx.get("time") or msg_time or "",
                sender=tx.get("sender") or sender,
                bank=tx.get("bank", ""),
                transaction_code=tx.get("transaction_code", ""),
                account_number=tx.get("account_number", ""),
                beneficiary=tx.get("beneficiary", ""),
                content=tx.get("content", raw_text),
                raw_text=raw_text,
                summary_excerpt=summary_excerpt or (raw_text[:500] if raw_text else None),
                screenshot_path=state.last_screenshot_path,
            )
        )
    return records


def records_from_detect(
    detect_fn: Callable[..., dict],
    *,
    text: str,
    sender: str,
    msg_date: str,
    msg_time: str,
    state,
    message_id: str,
    source_type: SourceType,
    line_index: int | None = None,
    summary_excerpt: str | None = None,
    transfer_image_path: str | None = None,
) -> list[TransactionRecord]:
    try:
        tx = detect_fn(text, sender=sender, time=msg_date or msg_time)
    except Exception:
        return []

    if not tx.get("is_transaction"):
        return []

    seq = state.transaction_count + 1
    return [
        build_record(
            tx_id=new_tx_id(state.session_id, seq),
            session_id=state.session_id,
            app_type=state.app_type,
            chat_id=state.current_chat_id,
            chat_name=state.current_chat_name,
            message_id=message_id,
            source_type=source_type,
            amount=tx.get("amount", ""),
            parent_message_id=message_id,
            line_index=line_index,
            transaction_date=tx.get("date") or msg_date or "",
            transaction_time=tx.get("time") or msg_time or "",
            sender=tx.get("sender") or sender,
            bank=tx.get("bank", ""),
            transaction_code=tx.get("transaction_code", ""),
            account_number=tx.get("account_number", ""),
            beneficiary=tx.get("beneficiary", ""),
            content=tx.get("content", text),
            raw_text=text,
            summary_excerpt=summary_excerpt,
            transfer_image_path=transfer_image_path,
            screenshot_path=state.last_screenshot_path,
        )
    ]


def records_from_split_response(
    split_resp: dict,
    *,
    state,
) -> list[TransactionRecord]:
    """Map SplitTransactionsResponse → TransactionRecord app."""
    out: list[TransactionRecord] = []
    txs = split_resp.get("transactions") or []
    for i, raw in enumerate(txs):
        seq = state.transaction_count + len(out) + 1
        out.append(
            build_record(
                tx_id=raw.get("id") or new_tx_id(state.session_id, seq),
                session_id=state.session_id,
                app_type=state.app_type,
                chat_id=raw.get("chat_id") or state.current_chat_id,
                chat_name=raw.get("chat_name") or state.current_chat_name,
                message_id=raw.get("message_id", ""),
                source_type=raw.get("source_type", "llm_chat_segment"),
                amount=raw.get("amount", ""),
                line_index=raw.get("line_index", i),
                transaction_date=raw.get("transaction_date", ""),
                transaction_time=raw.get("transaction_time", ""),
                sender=raw.get("sender", ""),
                bank=raw.get("bank", ""),
                transaction_code=raw.get("transaction_code", ""),
                account_number=raw.get("account_number", ""),
                beneficiary=raw.get("beneficiary", ""),
                content=raw.get("content", ""),
                raw_text=raw.get("raw_text", ""),
                summary_excerpt=raw.get("summary_excerpt"),
                screenshot_path=state.last_screenshot_path,
            )
        )
    return out


def records_from_llm_split(
    split_fn: Callable[..., dict],
    *,
    segment: dict,
    state,
) -> list[TransactionRecord]:
    """Gọi POST /split-transactions — Ollama tách GD từ đoạn chat_session."""
    try:
        resp = split_fn(segment)
    except Exception:
        return []

    out: list[TransactionRecord] = []
    for i, raw in enumerate(resp.get("transactions") or []):
        seq = state.transaction_count + len(out) + 1
        out.append(
            build_record(
                tx_id=raw.get("id") or new_tx_id(state.session_id, seq),
                session_id=state.session_id,
                app_type=state.app_type,
                chat_id=raw.get("chat_id") or state.current_chat_id,
                chat_name=raw.get("chat_name") or state.current_chat_name,
                message_id=raw.get("message_id") or segment.get("id", ""),
                source_type=raw.get("source_type", "llm_chat_segment"),
                amount=raw.get("amount", ""),
                line_index=raw.get("line_index", i),
                transaction_date=raw.get("transaction_date") or segment.get("date", ""),
                transaction_time=raw.get("transaction_time") or segment.get("time", ""),
                sender=raw.get("sender") or segment.get("sender", ""),
                bank=raw.get("bank", ""),
                transaction_code=raw.get("transaction_code", ""),
                account_number=raw.get("account_number", ""),
                beneficiary=raw.get("beneficiary", ""),
                content=raw.get("content", ""),
                raw_text=raw.get("raw_text", segment.get("text", "")),
                summary_excerpt=raw.get("summary_excerpt") or (segment.get("text") or "")[:500],
                screenshot_path=state.last_screenshot_path,
            )
        )
    return out


def records_from_parse_summary(
    parse_fn: Callable[..., dict],
    *,
    text: str,
    sender: str,
    msg_date: str,
    msg_time: str,
    state,
    message_id: str,
) -> list[TransactionRecord]:
    try:
        resp = parse_fn(
            text,
            sender=sender,
            time=msg_date or msg_time,
            message_id=message_id,
        )
    except Exception:
        return []

    out: list[TransactionRecord] = []
    for i, raw in enumerate(resp.get("records") or []):
        seq = state.transaction_count + len(out) + 1
        out.append(
            build_record(
                tx_id=new_tx_id(state.session_id, seq),
                session_id=state.session_id,
                app_type=state.app_type,
                chat_id=state.current_chat_id,
                chat_name=state.current_chat_name,
                message_id=message_id,
                source_type=raw.get("source_type", "summary_text"),
                amount=raw.get("amount", ""),
                line_index=raw.get("line_index", i),
                transaction_date=msg_date,
                transaction_time=msg_time,
                sender=raw.get("sender") or sender,
                bank=raw.get("bank", ""),
                transaction_code=raw.get("transaction_code", ""),
                account_number=raw.get("account_number", ""),
                beneficiary=raw.get("beneficiary", ""),
                content=raw.get("content", ""),
                raw_text=raw.get("raw_text", text),
                summary_excerpt=raw.get("summary_excerpt") or text[:500],
                screenshot_path=state.last_screenshot_path,
            )
        )
    return out
