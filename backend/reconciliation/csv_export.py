"""
Ghi giao dịch ra CSV (UTF-8 BOM) — backend reconciliation.
"""

from __future__ import annotations

import csv
from pathlib import Path

from backend.reconciliation.models import TransactionRecord

CSV_HEADERS = [
    "id",
    "session_id",
    "app_type",
    "chat_name",
    "message_id",
    "source_type",
    "transaction_date",
    "transaction_time",
    "sender",
    "direction",
    "amount",
    "currency",
    "bank",
    "transaction_code",
    "account_number",
    "beneficiary",
    "content",
    "transfer_image_path",
    "summary_excerpt",
    "dedupe_key",
    "status",
]


def _record_to_row(record: TransactionRecord) -> dict[str, str]:
    return {
        "id": record.id,
        "session_id": record.session_id,
        "app_type": record.app_type,
        "chat_name": record.chat_name,
        "message_id": record.message_id,
        "source_type": record.source_type,
        "transaction_date": record.transaction_date,
        "transaction_time": record.transaction_time,
        "sender": record.sender,
        "direction": record.direction,
        "amount": record.amount,
        "currency": record.currency,
        "bank": record.bank,
        "transaction_code": record.transaction_code,
        "account_number": record.account_number,
        "beneficiary": record.beneficiary,
        "content": record.content,
        "transfer_image_path": record.transfer_image_path or "",
        "summary_excerpt": record.summary_excerpt or "",
        "dedupe_key": record.dedupe_key,
        "status": record.status,
    }


def append_transactions_csv(csv_path: Path, records: list[TransactionRecord]) -> None:
    """Append danh sách giao dịch vào CSV (tạo header nếu file mới)."""
    if not records:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        for record in records:
            writer.writerow(_record_to_row(record))
