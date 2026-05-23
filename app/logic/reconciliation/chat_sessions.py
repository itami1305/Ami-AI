"""
Gom bubble OCR thành lượt chat (session) giữa các mốc ngày/giờ.

Mỗi session = một dòng trong messages.json (type=chat_session), chứa toàn bộ tin trong khoảng.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from backend.reconciliation.date_separator import (
    extract_date_label,
    is_date_separator_text,
    resolve_chat_date_display,
)
from backend.reconciliation.models import DetectTransactionRequest
from backend.reconciliation.transaction_detector import detect_transaction, is_summary_message
from backend.reconciliation.transfer_receipt import (
    is_multi_transaction_segment,
    is_transfer_receipt_text,
)



def _bubble_y(msg: dict) -> float:
    bbox = msg.get("bbox") or {}
    if isinstance(bbox, dict) and bbox.get("y") is not None:
        return float(bbox["y"])
    if msg.get("y") is not None:
        return float(msg["y"])
    return 0.0


def _marker_id(text: str, y: float) -> str:
    raw = f"{(text or '').strip()}|{y:.4f}"
    return f"mark_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:10]}"


def _session_id(chat_id: str, before_id: str | None, after_id: str | None) -> str:
    key = f"{chat_id}|{before_id or 'start'}|{after_id or 'end'}"
    return "sess_" + hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def _dominant_role(members: list[dict]) -> str:
    roles = [m.get("role") for m in members if m.get("role") not in ("system", None, "")]
    if not roles:
        return "other"
    self_n = sum(1 for r in roles if r == "self")
    other_n = len(roles) - self_n
    if self_n > other_n:
        return "self"
    if other_n > self_n:
        return "other"
    return "mixed"


def _session_date(marker_before: dict | None, marker_after: dict | None, members: list[dict]) -> str:
    for src in (marker_after, marker_before):
        if not src:
            continue
        text = (src.get("text") or "").strip()
        d = resolve_chat_date_display(text) or resolve_chat_date_display(src.get("date") or "")
        if d:
            return d
        abs_d = extract_date_label(text)
        if abs_d:
            return abs_d
    for m in members:
        text = (m.get("text") or "").strip()
        d = resolve_chat_date_display(m.get("date") or "") or resolve_chat_date_display(text)
        if d:
            return d
        abs_d = extract_date_label(text)
        if abs_d:
            return abs_d
    return resolve_chat_date_display("", default_today=True) or ""


def _session_time(marker_before: dict | None) -> str:
    if not marker_before:
        return ""
    text = (marker_before.get("text") or "").strip()
    m = re.search(r"(\d{1,2}[.:]\d{2})", text)
    return m.group(1).replace(".", ":") if m else ""


def build_chat_sessions(
    bubbles: list[dict],
    *,
    chat_id: str,
    chat_name: str,
    reconciliation_session_id: str,
    existing_catalog: dict[str, dict] | None = None,
) -> tuple[dict[str, dict], int]:
    """
    Từ danh sách bubble (đã sort theo Y), tạo dict session_id → entry chat_session.

    Returns:
        (sessions_dict, số session mới so với existing_catalog)
    """
    existing = existing_catalog or {}
    ordered = sorted(bubbles, key=lambda m: (_bubble_y(m), str(m.get("id", ""))))

    groups: list[tuple[dict | None, dict | None, list[dict]]] = []
    current: list[dict] = []
    marker_before: dict | None = None

    for b in ordered:
        btype = b.get("type") or "text"
        text = (b.get("text") or "").strip()
        if btype == "date_separator" or is_date_separator_text(text):
            if current:
                groups.append((marker_before, b, list(current)))
                current = []
            marker_before = b
            continue
        if text:
            current.append(b)

    if current:
        groups.append((marker_before, None, list(current)))

    sessions: dict[str, dict] = {}
    new_count = 0

    for marker_before, marker_after, members in groups:
        if not members:
            continue
        before_id = _marker_id(
            marker_before.get("text", "") if marker_before else "",
            _bubble_y(marker_before) if marker_before else 0.0,
        ) if marker_before else None
        after_id = _marker_id(
            marker_after.get("text", "") if marker_after else "",
            _bubble_y(marker_after) if marker_after else 0.0,
        ) if marker_after else None
        sid = _session_id(chat_id, before_id, after_id)

        texts = [(m.get("text") or "").strip() for m in members if (m.get("text") or "").strip()]
        combined = "\n".join(texts)
        member_ids = [str(m.get("id", "")) for m in members if m.get("id")]

        prev = existing.get(sid) or {}
        is_new = sid not in existing
        if is_new:
            new_count += 1

        was_tx = bool(prev.get("is_transaction", False))
        tx_flag = was_tx
        if combined and not tx_flag:
            tx_flag = (
                is_multi_transaction_segment(combined)
                or is_transfer_receipt_text(combined)
                or is_summary_message(combined)
                or detect_transaction(DetectTransactionRequest(text=combined)).is_transaction
            )
        if tx_flag and not was_tx:
            logger.info(
                "Phát hiện đoạn chat có giao dịch: chat=%s session=%s date=%s members=%d",
                chat_name or chat_id,
                sid,
                _session_date(marker_before, marker_after, members),
                len(member_ids),
            )

        entry: dict[str, Any] = {
            "id": sid,
            "session_id": sid,
            "reconciliation_session_id": reconciliation_session_id,
            "chat_id": chat_id or chat_name,
            "chat_name": chat_name or chat_id or "—",
            "type": "chat_session",
            "role": _dominant_role(members),
            "text": combined,
            "date": _session_date(marker_before, marker_after, members),
            "time": _session_time(marker_before),
            "member_ids": member_ids,
            "member_count": len(member_ids),
            "marker_before": (marker_before or {}).get("text", "") if marker_before else "",
            "marker_after": (marker_after or {}).get("text", "") if marker_after else "",
            "is_transaction": tx_flag,
        }
        if prev.get("first_seen_at"):
            entry["first_seen_at"] = prev["first_seen_at"]
        if prev.get("updated_at"):
            entry["updated_at"] = prev["updated_at"]

        sessions[sid] = entry

    return sessions, new_count
