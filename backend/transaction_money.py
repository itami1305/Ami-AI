"""
Nhận diện số tiền giao dịch hợp lệ (VN) — tránh báo sai cảnh hội thoại thường.

Chấp nhận (thiên về SMS / Zalo báo có):
- \"138,000 VND\", \"1,380,500 vnđ\", \"đồng\", \"₫\"
- Kiểu chấm nghìn: \"1.500.000 đ\"
- Viết gọn: \"500k\", \"138,000 k\", \"5,5 tr\"

Ngoại lệ ngân hàng: có mã FT... kèm số có nhóm nghìn (phẩy/chấm) dù không ghi VND.

Không coi chỉ có từ khóa hay số ngẫu nhiên (năm, mã không liên quan) là giao dịch.
"""

from __future__ import annotations

import re

# 138,000 VND / không bắt buộc khoảng trắng trước đơn vị (OCR hay dính: 138,000VND)
COMMA_THOUSANDS_VND = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:,\d{3})*(?:\.\d{1,4})?\s*(?:vnđ|vnd|đồng|₫)(?=\W|$)",
    re.IGNORECASE,
)

# 1.500.000 đ / VND (đ phải tách rời — tránh dính chữ \"đã\")
DOT_THOUSANDS_VND = re.compile(
    r"\d{1,3}(?:\.\d{3})+(?:\.\d{3})*(?:,\d{1,2})?\s*(?:vnđ|vnd|đồng|₫)(?=\W|$)|"
    r"\d{1,3}(?:\.\d{3})+(?:\.\d{3})*(?:,\d{1,2})?\s+đ(?:\s|$)",
    re.IGNORECASE,
)

# 500k, 100k, 138,000 k (k = nghìn)
ABBREV_K = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+\s*k\b|\b(?:[1-9]\d{2,6})\s*k\b)",
    re.IGNORECASE,
)

# 5 tr, 5,5 tr
ABBREV_TR = re.compile(
    r"\b\d{1,3}(?:[.,]\d+)?\s*tr\b",
    re.IGNORECASE,
)

# Số có phân tách nghìn (dùng kèm mã FT khi không có chữ VND/đ)
GROUPED_AMOUNT = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+(?:,\d{3})*|\d{1,3}(?:\.\d{3})+(?:\.\d{3})*)"
)

_MONEY_ORDER: tuple[re.Pattern[str], ...] = (
    COMMA_THOUSANDS_VND,
    DOT_THOUSANDS_VND,
    ABBREV_K,
    ABBREV_TR,
)


# OCR hay thiếu "VND" — nhận qua ngữ cảnh chuyển khoản + số nhóm nghìn
_TRANSFER_CONTEXT = re.compile(
    r"chuy[eê]n\s*kho[aả]n|chuy[eê]n\s*t[ií]en|chuyen\s*tien|gd\s*thanh\s*cong|"
    r"giao\s*d[iị]ch\s*thanh\s*cong|napas|ft\d{6,}",
    re.IGNORECASE,
)


def find_transaction_money(text: str) -> re.Match[str] | None:
    """Trả match đầu tiên theo độ ưu tiên; None nếu không có mẫu tiền hợp lệ."""
    if not (text or "").strip():
        return None
    for rx in _MONEY_ORDER:
        m = rx.search(text)
        if m:
            return m
    if _TRANSFER_CONTEXT.search(text):
        gm = GROUPED_AMOUNT.search(text)
        if gm:
            return gm
        # Số tiền đơn (OCR): 33788, 1 380 000
        loose = re.search(
            r"\b(\d{1,3}(?:\s\d{3}){1,4}|\d{4,9})\b",
            text,
        )
        if loose:
            return loose
    return None


def strict_money_line_match(line: str) -> bool:
    """Dùng cho tin tổng hợp nhiều dòng: dòng có mẫu tiền rõ ràng."""
    if find_transaction_money(line):
        return True
    return bool(GROUPED_AMOUNT.search(line))
