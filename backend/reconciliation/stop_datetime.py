"""
So sánh ngày tin nhắn (OCR: dd/mm/yyyy) với ngưỡng dừng stop_date (ISO date hoặc datetime).
"""

from __future__ import annotations

from datetime import datetime

from backend.reconciliation.date_separator import resolve_chat_date_display


def parse_stop_threshold(value: str) -> datetime | None:
    """Chấp nhận YYYY-MM-DD hoặc ISO datetime (khoảng trắng hoặc T làm phân cách)."""
    value = (value or "").strip()
    if not value:
        return None
    norm = value.replace(" ", "T", 1) if " " in value and "T" not in value else value
    try:
        return datetime.fromisoformat(norm)
    except ValueError:
        return None


def parse_message_date_ddmmyyyy(value: str) -> datetime | None:
    """Ngày hiển thị trên UI chat (OCR)."""
    value = (value or "").strip()
    if not value:
        return None
    resolved = resolve_chat_date_display(value, default_today=False)
    if resolved and resolved != value:
        value = resolved
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            continue
    return None


def message_reached_stop_threshold(msg_date_display: str, stop_threshold: str) -> bool:
    """True nếu tin (đầu ngày) đã tới hoặc vượt qua ngưỡng dừng."""
    stop_dt = parse_stop_threshold(stop_threshold)
    if stop_dt is None:
        return False
    msg_dt = parse_message_date_ddmmyyyy(msg_date_display)
    if msg_dt is None:
        return False
    return msg_dt <= stop_dt
