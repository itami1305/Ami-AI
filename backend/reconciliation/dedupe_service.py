"""
Gộp trùng giao dịch theo dedupe_key — §10.1, §10.8 (rule-based).
"""

from __future__ import annotations

from backend.reconciliation.models import AnalyzeWarning, TransactionRecord
from backend.reconciliation.transaction_detector import make_dedupe_key


def ensure_dedupe_keys(records: list[TransactionRecord]) -> None:
    for rec in records:
        if rec.dedupe_key:
            continue
        rec.dedupe_key = make_dedupe_key(
            rec.bank,
            rec.amount,
            rec.transaction_code,
            rec.transaction_date or rec.transaction_time,
            rec.chat_id,
        )


def merge_by_dedupe(records: list[TransactionRecord]) -> list[TransactionRecord]:
    """Ưu tiên transfer_image khi trùng dedupe_key."""
    ensure_dedupe_keys(records)
    by_key: dict[str, TransactionRecord] = {}
    order: list[str] = []

    priority = {"transfer_image": 3, "summary_text": 2, "single_text": 1}

    for rec in records:
        key = rec.dedupe_key or rec.id
        if key not in by_key:
            by_key[key] = rec.model_copy(deep=True)
            order.append(key)
            continue
        existing = by_key[key]
        if priority.get(rec.source_type, 0) > priority.get(existing.source_type, 0):
            linked = list(existing.linked_record_ids)
            if existing.id and existing.id not in linked:
                linked.append(existing.id)
            by_key[key] = rec.model_copy(deep=True)
            by_key[key].linked_record_ids = linked
            rec.is_duplicate = True
            rec.linked_record_ids = [by_key[key].id] if by_key[key].id else []
        else:
            rec.is_duplicate = True
            if by_key[key].id:
                rec.linked_record_ids = list(set(rec.linked_record_ids + [by_key[key].id]))

    return [by_key[k] for k in order]


def build_warnings(records: list[TransactionRecord]) -> list[AnalyzeWarning]:
    warnings: list[AnalyzeWarning] = []
    by_key: dict[str, list[TransactionRecord]] = {}
    for rec in records:
        if not rec.dedupe_key:
            continue
        by_key.setdefault(rec.dedupe_key, []).append(rec)

    for key, group in by_key.items():
        types = {r.source_type for r in group}
        if "summary_text" in types and "transfer_image" not in types:
            warnings.append(
                AnalyzeWarning(
                    code="summary_only",
                    message=f"Có tin tổng hợp nhưng chưa có ảnh CK khớp ({key})",
                    record_ids=[r.id for r in group if r.id],
                )
            )
        elif "transfer_image" in types and "summary_text" not in types:
            warnings.append(
                AnalyzeWarning(
                    code="image_only",
                    message=f"Có ảnh CK nhưng chưa có dòng tổng hợp khớp ({key})",
                    record_ids=[r.id for r in group if r.id],
                )
            )
    return warnings
