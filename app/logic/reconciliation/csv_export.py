"""
Ghi dữ liệu giao dịch ra CSV (Excel-friendly, UTF-8 BOM) và transactions.json.

CSV chỉ subset cột; JSON đầy đủ field TransactionRecord để API analyze và truy vết.
"""
# §10.4 markdown.md

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.logic.reconciliation.models import TransactionRecord

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


def init_csv_file(csv_path: Path) -> None:
    """Tạo file CSV với header nếu chưa tồn tại (idempotent khi đã có file)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists():
        return
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()


def init_json_file(json_path: Path) -> None:
    """Khởi tạo JSON rỗng { \"transactions\": [] } nếu chưa có."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    if json_path.exists():
        return
    json_path.write_text('{"transactions": []}\n', encoding="utf-8")


def append_transaction_record(csv_path: Path, json_path: Path | None, record: TransactionRecord) -> None:
    """Append một bản ghi (CSV luôn; JSON nếu json_path khác None)."""
    row = record.to_csv_row()
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    if json_path is not None:
        init_json_file(json_path)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data.setdefault("transactions", []).append(record.to_json_dict())
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
