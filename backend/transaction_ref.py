"""
Mã tham chiếu giao dịch ngân hàng — FT, IZOK, 140K... (VietinBank OCR hay đọc IZOK → 140K).
"""

from __future__ import annotations

import re

# FT..., IZOK..., IBFT..., VietinBank 140K26028X... (OCR: I→1, Z→4, O→0)
TRANSACTION_REF_RE = re.compile(
    r"\b(?:"
    r"FT\d{6,}|"
    r"IBFT[A-Z0-9]{6,}|"
    r"IZOK[A-Z0-9]{8,}|"
    r"IZO[A-Z0-9]{6,}|"
    r"(?:GD|TK|NAPAS)[A-Z0-9]{6,}|"
    r"\d{3}[A-Z]\d{5,}[A-Z0-9]{2,}|"
    r"[A-Z]{2,4}\d{8,}[A-Z0-9]{0,10}"
    r")\b",
    re.IGNORECASE,
)


def find_transaction_ref(text: str, *, account_number: str = "") -> str:
    """Trả mã GD dài nhất; ưu tiên dòng chỉ chứa mã (thường là dòng riêng trên bill CK)."""
    if not text:
        return ""
    exclude = {account_number.replace(" ", "")} if account_number else set()

    best = ""
    best_score = -1

    for ln in (text or "").splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        compact = re.sub(r"\s+", "", stripped)
        for m in TRANSACTION_REF_RE.finditer(stripped):
            cand = m.group(0).upper()
            if cand in exclude or cand.isdigit():
                continue
            solo = bool(TRANSACTION_REF_RE.fullmatch(compact))
            score = len(cand) + (100 if solo else 0)
            if score > best_score:
                best_score = score
                best = cand

    if best:
        return best

    candidates: list[str] = []
    for m in TRANSACTION_REF_RE.finditer(text):
        cand = m.group(0).upper()
        if cand not in exclude and not cand.isdigit():
            candidates.append(cand)
    return max(candidates, key=len) if candidates else ""
