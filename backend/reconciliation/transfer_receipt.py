"""
Nhận diện & trích xuất ảnh chụp chuyển khoản (OCR nhiều dòng trong một khung).

Ví dụ OCR VietinBank:
  VetinBank / Chuyển tiền thành công / 138,000 VND / 02/05/2026 16-00 / IZOK... / tên TK / nội dung
"""

from __future__ import annotations

import re

from backend.reconciliation.models import TransactionResult
from backend.transaction_money import find_transaction_money, strict_money_line_match
from backend.transaction_ref import TRANSACTION_REF_RE, find_transaction_ref

# SMS / lịch sử GD ngân hàng trong chat: "6- 18/05/2026 14.24.46 +1,050,000 FT..."
_BANK_SMS_LINE_RE = re.compile(
    r"^\s*\d+\s*[-–.]\s*\d{1,2}/\d{1,2}/\d{4}",
    re.IGNORECASE,
)
_BANK_SMS_AMOUNT_RE = re.compile(r"\+\s*([\d,]+(?:,\d{3})*)")

# Gợi ý bill CK (chấp nhận lỗi OCR: tlén, VetinBank, Nệl dung, MB_Ngán...)
_RECEIPT_HINT = re.compile(
    r"thanh\s*cong|thành\s*công|tl[eéế]n|chuy[eê]n\s*tl[eéế]n|chuy[eê]n\s*t[ií]en|chuyen\s*tien|"
    r"gd\s*thanh\s*cong|so\s*t[ií]en|s[oô]\s*t[ií]en|"
    r"vietinbank|vetinbank|vietcombank|mbbank|mb_ng|techcombank|bidv|napas|"
    r"n[oô]i\s*dung|n[eệ]l\s*dung|ngu[oơ]i\s*nh[aậ]n|t[aá]i\s*kho[aả]n",
    re.IGNORECASE,
)

_DATE_TIME_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2})[-:.](\d{2})",
    re.IGNORECASE,
)

_REF_CODE_RE = TRANSACTION_REF_RE

_ACCOUNT_RE = re.compile(r"\b\d{8,16}\b")

_CONTENT_LABEL_RE = re.compile(r"n[oô]i\s*dung|n[eệ]l\s*dung", re.IGNORECASE)
_GENERIC_CONTENT_RE = re.compile(
    r"^(?:chuy[eê]n\s*t[ií]en|chuyen\s*tien|chuy[eê]n\s*kho[aả]n|ck|giao\s*d[iị]ch)$",
    re.IGNORECASE,
)

_BANK_MAP = {
    "vietcombank": "VCB",
    "vcb": "VCB",
    "vietinbank": "VIETINBANK",
    "vetinbank": "VIETINBANK",
    "mbbank": "MB",
    "mb_ng": "MB",
    "mb bank": "MB",
    "techcombank": "TCB",
    "tcb": "TCB",
    "bidv": "BIDV",
    "acb": "ACB",
    "napas": "NAPAS",
}


def _detect_bank(text_lower: str) -> str:
    for key, code in _BANK_MAP.items():
        if key in text_lower:
            return code
    return ""


def _normalize_time(hour: str, minute: str) -> str:
    try:
        h, m = int(hour), int(minute)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except ValueError:
        pass
    return f"{hour}:{minute}"


def _is_noise_line(line: str) -> bool:
    s = line.strip().lower()
    if not s or len(s) <= 2:
        return True
    if s in ("hang", "quan", "ngan"):
        return True
    if re.fullmatch(r"hd+", s):
        return True
    return False


def _strip_content_label_value(line: str) -> str:
    return re.sub(
        r"^.*?(?:n[oô]i\s*dung|n[eệ]l\s*dung)\s*:?\s*",
        "",
        line,
        flags=re.IGNORECASE,
    ).strip()


def _is_content_label_only(line: str) -> bool:
    val = _strip_content_label_value(line)
    if val and len(val) > 4:
        return False
    letters = re.sub(r"[^a-zà-ỹ]", "", line.lower())
    return letters in ("noidung", "neldung") or bool(
        _CONTENT_LABEL_RE.fullmatch(line.strip())
    )


def _is_generic_transfer_content(text: str) -> bool:
    return bool(_GENERIC_CONTENT_RE.match((text or "").strip()))


def _looks_like_person_name(line: str) -> bool:
    s = line.strip()
    if len(s) < 6 or len(s) > 80:
        return False
    compact = re.sub(r"\s+", "", s)
    if (
        10 <= len(compact) <= 24
        and re.fullmatch(r"[A-Z0-9]+", compact, re.IGNORECASE)
        and re.search(r"\d", compact)
        and re.search(r"[A-Z]", compact, re.IGNORECASE)
    ):
        return False
    if find_transaction_money(s) or _REF_CODE_RE.search(s) or _DATE_TIME_RE.search(s):
        return False
    if _detect_bank(s.lower()):
        return False
    if _ACCOUNT_RE.fullmatch(s.replace(" ", "")):
        return False
    letters = re.findall(r"[A-Za-zÀ-ỹ]", s)
    if len(letters) < 5:
        return False
    upper = sum(1 for c in s if c.isupper())
    return upper >= len(letters) * 0.45 or s.isupper()


def _bank_sms_line_match(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if _BANK_SMS_LINE_RE.match(s):
        return True
    if re.search(r"FT\d{6,}", s, re.IGNORECASE) and _BANK_SMS_AMOUNT_RE.search(s):
        return True
    return False


def is_multi_transaction_segment(text: str) -> bool:
    """True nếu đoạn chat chứa ≥2 dòng báo có GD (SMS ngân hàng / lịch sử CK)."""
    clean = (text or "").strip()
    if not clean:
        return False
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip() and not _is_noise_line(ln)]
    sms_lines = [ln for ln in lines if _bank_sms_line_match(ln)]
    if len(sms_lines) >= 2:
        return True
    ft_hits = [ln for ln in lines if re.search(r"FT\d{6,}", ln, re.IGNORECASE)]
    money_lines = [
        ln
        for ln in lines
        if strict_money_line_match(ln) or _BANK_SMS_AMOUNT_RE.search(ln)
    ]
    return len(ft_hits) >= 2 and len(money_lines) >= 2


def split_bank_transaction_lines(text: str) -> list[str]:
    """Tách từng dòng SMS GD trong một đoạn chat."""
    lines = [
        ln.strip()
        for ln in (text or "").splitlines()
        if ln.strip() and not _is_noise_line(ln) and _bank_sms_line_match(ln)
    ]
    return lines if len(lines) >= 2 else []


def parse_bank_sms_line(line: str, *, sender: str = "") -> TransactionResult | None:
    """Trích xuất một GD từ một dòng SMS/lịch sử ngân hàng."""
    s = (line or "").strip()
    if not _bank_sms_line_match(s):
        return None

    amount = ""
    m_amt = _BANK_SMS_AMOUNT_RE.search(s)
    if m_amt:
        amount = m_amt.group(1).strip()
    else:
        mm = find_transaction_money(s)
        if mm:
            amount = mm.group(0).strip()

    if not amount and not find_transaction_ref(s):
        return None

    code = find_transaction_ref(s)
    low = s.lower()
    bank = _detect_bank(low)

    tx_date = ""
    tx_time = ""
    m_dt = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", s)
    if m_dt:
        tx_date = m_dt.group(1)
    m_time = re.search(r"(\d{1,2})[.:](\d{2})", s)
    if m_time:
        tx_time = _normalize_time(m_time.group(1), m_time.group(2))

    return TransactionResult(
        is_transaction=True,
        date=tx_date,
        time=tx_time,
        sender=sender,
        amount=amount,
        bank=bank,
        transaction_code=code,
        content=s[:500],
    )


def parse_transfer_receipts(
    text: str, *, sender: str = "", time: str = ""
) -> list[TransactionResult]:
    """Trích xuất một hoặc nhiều GD từ đoạn chat (bill CK đơn hoặc nhiều dòng SMS)."""
    if is_multi_transaction_segment(text):
        out: list[TransactionResult] = []
        for ln in split_bank_transaction_lines(text):
            det = parse_bank_sms_line(ln, sender=sender)
            if det and det.is_transaction:
                out.append(det)
        return out
    single = parse_transfer_receipt(text, sender=sender, time=time)
    return [single] if single and single.is_transaction else []


def is_transfer_receipt_text(text: str) -> bool:
    """
    True nếu OCR giống một ảnh bill chuyển khoản (nhiều dòng, có VND + ngữ cảnh CK).
    Không áp dụng khi đoạn chat có nhiều dòng SMS GD (is_multi_transaction_segment).
    """
    if is_multi_transaction_segment(text):
        return False
    clean = (text or "").strip()
    if len(clean) < 24:
        return False
    if not find_transaction_money(clean):
        return False
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip() and not _is_noise_line(ln)]
    if len(lines) < 3:
        return False
    low = clean.lower()
    if _RECEIPT_HINT.search(clean) or _detect_bank(low):
        return True
    if _REF_CODE_RE.search(clean) and any("vnd" in ln.lower() for ln in lines):
        return True
    return len(lines) >= 5 and bool(_DATE_TIME_RE.search(clean))


def parse_transfer_receipt(text: str, *, sender: str = "", time: str = "") -> TransactionResult | None:
    """
    Trích xuất một giao dịch từ khối OCR ảnh chuyển khoản (rule-based, không cần LLM).
    """
    clean = (text or "").strip()
    if not is_transfer_receipt_text(clean):
        return None

    low = clean.lower()
    amount_match = find_transaction_money(clean)
    amount = amount_match.group(0).strip() if amount_match else ""

    bank = _detect_bank(low)

    tx_date = ""
    tx_time = time or ""
    m_dt = _DATE_TIME_RE.search(clean)
    if m_dt:
        tx_date = m_dt.group(1)
        tx_time = _normalize_time(m_dt.group(2), m_dt.group(3))

    lines = [ln.strip() for ln in clean.splitlines() if ln.strip() and not _is_noise_line(ln)]

    beneficiary = ""
    content = ""
    account = ""
    names: list[str] = []
    pending_content = False

    for ln in lines:
        if _ACCOUNT_RE.search(ln) and not account:
            m_acc = _ACCOUNT_RE.search(ln.replace(" ", ""))
            if m_acc:
                account = m_acc.group(0)
        ll = ln.lower()
        if _CONTENT_LABEL_RE.search(ll):
            val = _strip_content_label_value(ln)
            if val and not _is_content_label_only(ln):
                content = val
                pending_content = False
            else:
                pending_content = True
            continue
        if pending_content and not _is_noise_line(ln):
            content = ln
            pending_content = False
            continue
        if re.search(r"chuy[eê]n\s*t[ií]en|chuyen\s*tien", ll):
            if not content or _is_generic_transfer_content(content):
                if not _is_generic_transfer_content(ln):
                    content = ln
            continue
        if _looks_like_person_name(ln):
            names.append(ln)

    if names:
        # Dòng tên đầu sau ngày/số tiền thường là người nhận; dòng sau nhãn "Nội dung" là nội dung CK
        beneficiary = names[0]
        if len(names) > 1 and (not content or _is_generic_transfer_content(content)):
            for cand in reversed(names):
                if cand == beneficiary:
                    continue
                if not _is_generic_transfer_content(cand):
                    content = cand
                    break
            if not content or _is_generic_transfer_content(content):
                content = names[-1] if names[-1] != beneficiary else content

    if not content or _is_generic_transfer_content(content):
        for ln in lines:
            val = _strip_content_label_value(ln)
            if val and not _is_content_label_only(ln) and not _is_generic_transfer_content(val):
                content = val
                break

    if not content or _is_generic_transfer_content(content):
        content = clean[:500]

    code = find_transaction_ref(clean, account_number=account)
    if not code and bank == "VIETINBANK":
        for ln in lines:
            compact = re.sub(r"\s+", "", ln).upper()
            if not (10 <= len(compact) <= 24):
                continue
            if not re.fullmatch(r"[A-Z0-9]+", compact):
                continue
            if not re.search(r"\d", compact) or not re.search(r"[A-Z]", compact):
                continue
            if compact == account or _ACCOUNT_RE.fullmatch(compact):
                continue
            if find_transaction_money(ln) or _DATE_TIME_RE.search(ln) or _looks_like_person_name(ln):
                continue
            code = compact
            break

    return TransactionResult(
        is_transaction=True,
        date=tx_date,
        time=tx_time,
        sender=sender,
        amount=amount,
        bank=bank,
        transaction_code=code,
        account_number=account,
        beneficiary=beneficiary,
        content=content,
    )
