"""
Phát hiện giao dịch — mẫu số tiền (VD 138,000 VND) hoặc FT + số nhóm nghìn; parse tin tổng hợp (§10.3–10.5).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from backend.reconciliation.models import (
    DetectTransactionRequest,
    ParseSummaryRequest,
    ParseSummaryResponse,
    TransactionRecord,
    TransactionResult,
)
from backend.transaction_money import GROUPED_AMOUNT, find_transaction_money, strict_money_line_match

SUMMARY_KEYWORDS = (
    "tổng hợp",
    "danh sách giao dịch",
    "báo cáo",
    "giao dịch ngày",
)

CODE_PATTERN = re.compile(r"FT\d+", re.IGNORECASE)
ACCOUNT_PATTERN = re.compile(r"\d{8,16}")
NUMBERED_LINE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)

BANK_MAP = {
    "vietcombank": "VCB",
    "vcb": "VCB",
    "mbbank": "MB",
    "mb bank": "MB",
    "napas": "NAPAS",
    "techcombank": "TCB",
    "tcb": "TCB",
}


def _detect_bank(text_lower: str) -> str:
    for key, code in BANK_MAP.items():
        if key in text_lower:
            return code
    return ""


def _extract_fields(text: str) -> tuple[str, str, str, str]:
    text_lower = text.lower()
    mm = find_transaction_money(text)
    code_match = CODE_PATTERN.search(text)
    account_match = ACCOUNT_PATTERN.search(text)
    if mm:
        amount = mm.group(0).strip()
    elif code_match and (gm := GROUPED_AMOUNT.search(text)):
        amount = gm.group(0).strip()
    else:
        amount = ""
    code = code_match.group(0) if code_match else ""
    bank = _detect_bank(text_lower)
    account = account_match.group(0) if account_match else ""
    return amount, code, bank, account


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


def make_dedupe_key(bank: str, amount: str, code: str, date: str, chat_id: str) -> str:
    parts = [
        (bank or "").lower(),
        re.sub(r"[^\d]", "", amount or ""),
        (code or "").upper(),
        date or "",
        chat_id or "",
    ]
    return "|".join(parts)


def detect_transaction(req: DetectTransactionRequest) -> TransactionResult:
    text = req.text or ""

    explicit_money = find_transaction_money(text)
    code_match = CODE_PATTERN.search(text)
    grouped_match = GROUPED_AMOUNT.search(text)
    # Tiền ghi rõ (VD 138,000 VND) hoặc SMS ngân hàng: FTxxx + số có phân nhóm nghìn
    is_tx = explicit_money is not None or (
        code_match is not None and grouped_match is not None
    )

    if not is_tx:
        return TransactionResult(is_transaction=False)

    amount, code, bank, account = _extract_fields(text)
    return TransactionResult(
        is_transaction=True,
        time=req.time,
        sender=req.sender,
        amount=amount,
        bank=bank,
        transaction_code=code,
        account_number=account,
        content=text.strip(),
    )


def _line_to_record(
    line: str,
    *,
    req: ParseSummaryRequest,
    line_index: int,
    excerpt: str,
) -> TransactionResult | None:
    det = detect_transaction(
        DetectTransactionRequest(text=line, sender=req.sender, time=req.time)
    )
    if not det.is_transaction:
        return None
    det.content = line
    return det


def parse_summary_lines(req: ParseSummaryRequest) -> ParseSummaryResponse:
    text = (req.text or "").strip()
    if not text:
        return ParseSummaryResponse(is_summary=False)

    summary = is_summary_message(text)
    lines = split_summary_lines(text) if summary else [text]
    records: list[TransactionRecord] = []
    now = datetime.now(timezone.utc).isoformat()

    for idx, line in enumerate(lines):
        det = _line_to_record(line, req=req, line_index=idx, excerpt=text[:500])
        if not det:
            continue
        records.append(
            TransactionRecord(
                message_id=req.message_id or f"msg_summary_{idx}",
                parent_message_id=req.message_id or "",
                line_index=idx,
                source_type="summary_text" if summary else "single_text",
                transaction_time=det.time,
                sender=det.sender,
                amount=det.amount,
                bank=det.bank,
                transaction_code=det.transaction_code,
                account_number=det.account_number,
                content=det.content,
                raw_text=line,
                summary_excerpt=text[:500] if summary else None,
                dedupe_key=make_dedupe_key(det.bank, det.amount, det.transaction_code, det.time, ""),
                status="extracted",
                created_at=now,
            )
        )

    return ParseSummaryResponse(
        is_summary=summary,
        lines=lines,
        records=records,
    )
