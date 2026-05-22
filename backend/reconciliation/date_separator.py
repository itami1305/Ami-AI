"""
Nhận diện nhãn ngày/giờ giữa đoạn chat (Zalo: "Hôm nay", "15.41 Hôm nay", "21/05/2026").
Dùng OCR + perceive để gán type=date_separator và tách lượt chat (session).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_DATE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})|(\d{2}/\d{2}/\d{4})|(\d{1,2}/\d{1,2}/\d{4})"
)
_REL_DAY_RE = re.compile(r"\b(hôm nay|hôm qua|ngày mai)\b", re.IGNORECASE)
_TIME_TODAY_RE = re.compile(
    r"^\s*\d{1,2}[.:]\d{2}\s+hôm\s+nay\b", re.IGNORECASE
)
_TIME_ONLY_RE = re.compile(r"^\s*\d{1,2}[.:]\d{2}\s*$")

_REL_DAY_ONLY = frozenset({"hôm nay", "hôm qua", "ngày mai"})


def extract_date_label(text: str) -> str | None:
    """Trích chuỗi ngày từ nhãn (nếu có)."""
    m = _DATE_RE.search(text or "")
    return m.group(0) if m else None


def _normalize_absolute_date(value: str) -> str | None:
    """Chuẩn hóa ngày tuyệt đối OCR → dd/mm/yyyy."""
    from datetime import datetime

    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            d = datetime.strptime(value, fmt).date()
            return d.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def resolve_chat_date_display(
    text: str,
    *,
    default_today: bool = False,
    ref: date | None = None,
) -> str | None:
    """
    Đổi nhãn ngày/giờ chat (OCR) sang dd/mm/yyyy để so sánh stop_date / lưu session.

    - Có ngày tuyệt đối (21/05/2026, …) → ngày đó.
    - Có «hôm qua» → ref − 1 ngày (mặc định ref = hôm nay).
    - Có «hôm nay», «15.41 Hôm nay», hoặc chỉ giờ (15:41) → ref.
    - Chuỗi rỗng: nếu default_today → ref; ngược lại None.
    """
    t = (text or "").strip()
    today = ref or date.today()

    if not t:
        return today.strftime("%d/%m/%Y") if default_today else None

    low = t.lower()
    abs_raw = extract_date_label(t)
    if abs_raw:
        norm = _normalize_absolute_date(abs_raw)
        if norm:
            return norm

    if re.search(r"\bhôm\s+qua\b", low):
        return (today - timedelta(days=1)).strftime("%d/%m/%Y")
    if re.search(r"\bhôm\s+nay\b", low) or _TIME_TODAY_RE.match(t):
        return today.strftime("%d/%m/%Y")
    if re.search(r"\bngày\s+mai\b", low):
        return (today + timedelta(days=1)).strftime("%d/%m/%Y")
    if _TIME_ONLY_RE.match(t):
        return today.strftime("%d/%m/%Y")
    if low in _REL_DAY_ONLY:
        if low == "hôm qua":
            return (today - timedelta(days=1)).strftime("%d/%m/%Y")
        if low == "ngày mai":
            return (today + timedelta(days=1)).strftime("%d/%m/%Y")
        return today.strftime("%d/%m/%Y")

    if default_today:
        return today.strftime("%d/%m/%Y")
    return None


def is_date_separator_text(text: str) -> bool:
    """
    True nếu bubble là mốc ngày/giờ giữa khung chat (không phải nội dung hội thoại).
    """
    t = (text or "").strip()
    if not t or len(t) > 96:
        return False
    low = t.lower()
    if low in _REL_DAY_ONLY:
        return True
    if _TIME_TODAY_RE.match(t):
        return True
    if _TIME_ONLY_RE.match(t) and len(t) <= 8:
        return True
    if _REL_DAY_RE.search(t) and len(t) <= 48:
        return True
    if _DATE_RE.fullmatch(t):
        return True
    # Chỉ ngày + vài ký tự phụ (giờ rời)
    if _DATE_RE.search(t) and len(t) <= 28:
        rest = _DATE_RE.sub("", t).strip(" .:-")
        if len(rest) <= 12:
            return True
    return False


def is_date_separator_centered(cx: float, chat_x: int, chat_w: int) -> bool:
    """Mốc ngày thường canh giữa khung chat."""
    if chat_w <= 0:
        return True
    rel = (cx - float(chat_x)) / float(chat_w)
    return 0.30 <= rel <= 0.70
