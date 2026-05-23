"""
# Engine OCR reconciliation — EasyOCR (vi + en)
EasyOCR cho pipeline reconciliation (/reconciliation/ocr, perceive).
Nhóm dòng text theo trục Y thành bubble tin nhắn / mục sidebar.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

import numpy as np
from PIL import Image

from backend.reconciliation.date_separator import (
    is_date_separator_centered,
    is_date_separator_text,
)
from backend.reconciliation.models import MessageItem, SidebarItem
from backend.transaction_money import find_transaction_money

# --- Ngưỡng gom dòng thành một bubble ---
Y_GAP_RATIO = float(os.getenv("OCR_Y_GAP_RATIO", "0.028"))
X_GAP_RATIO = float(os.getenv("OCR_X_GAP_RATIO", "0.10"))
MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.18"))
OCR_UPSCALE = float(os.getenv("OCR_UPSCALE", "2.0"))
OCR_BUBBLE_REOCR_SCALE = float(os.getenv("OCR_BUBBLE_REOCR_SCALE", "3.0"))
# Ảnh CK: cho phép khoảng cách dọc lớn hơn giữa các dòng trong cùng một khung
TRANSFER_FRAME_MIN_H = int(os.getenv("OCR_TRANSFER_FRAME_MIN_H", "72"))
TRANSFER_FRAME_Y_GAP_RATIO = float(os.getenv("OCR_TRANSFER_FRAME_Y_GAP_RATIO", "0.14"))
TRANSFER_FRAME_X_OVERLAP = float(os.getenv("OCR_TRANSFER_FRAME_X_OVERLAP", "0.32"))
SELF_SIDE_ALIGN = float(os.getenv("OCR_SELF_RIGHT_RATIO", "0.48"))

_DATE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})|(\d{2}/\d{2}/\d{4})|(\d{1,2}/\d{1,2}/\d{4})"
)

# Nhãn chất lượng ảnh trên thumbnail Zalo PC (OCR hay đọc thành "HD", "HD HD", …)
_HD_BADGE_LETTERS_RE = re.compile(r"^(?:hd)+$", re.IGNORECASE)
_HD_LINE_PREFIX_RE = re.compile(r"^(?:hd\s*)+", re.IGNORECASE)
_HD_LINE_SUFFIX_RE = re.compile(
    r"(?:\s*[\(\[]?\s*(?:hd\s*){1,4}[\)\]]?\s*)+$",
    re.IGNORECASE,
)

# Gợi ý ảnh / tin chuyển khoản (OCR hay lỗi chính tả)
_TRANSFER_HINT_RE = re.compile(
    r"chuy[eê]n\s*kho[aả]n|chuy[eê]n\s*t[ií]en|chuyen\s*tien|chuy[eể]n\s*tl[eé]n|"
    r"thanh\s*cong|thành\s*công|gd\s*thanh\s*cong|giao\s*d[iị]ch|"
    r"vietcombank|vietinbank|vetinbank|mb\s*bank|mbbank|mb_ng|techcombank|"
    r"napas|vcb|tcb|acb|bidv|sacombank|tpbank|vpbank|shinhan|agribank|"
    r"so\s*tk|so\s*t[ií]en|s[oô]\s*t[ií]en|n[oô]i\s*dung|n[eệ]l\s*dung|"
    r"ft\d{6,}|izok\w{6,}|izo\w{6,}|ibft\w{6,}|\d{3}[a-z]\d{5,}",
    re.IGNORECASE,
)

_reader = None


@dataclass(frozen=True)
class _Det:
    x1: int
    y1: int
    x2: int
    y2: int
    text: str
    conf: float

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def width(self) -> int:
        return max(1, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(1, self.y2 - self.y1)


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["vi", "en"], gpu=False, verbose=False)
    return _reader


def _is_zalo_hd_badge(text: str) -> bool:
    """True nếu chuỗi chỉ là nhãn HD trên ảnh chat Zalo (không phải nội dung tin)."""
    letters = re.sub(r"[^a-zA-Z]", "", (text or "").strip())
    if not letters:
        return False
    return bool(_HD_BADGE_LETTERS_RE.fullmatch(letters))


def _strip_zalo_hd_noise(text: str) -> str:
    """Loại nhãn HD khỏi text bubble; giữ nội dung thật (vd. dòng CK sau badge)."""
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or _is_zalo_hd_badge(ln):
            continue
        ln = _HD_LINE_PREFIX_RE.sub("", ln).strip()
        ln = _HD_LINE_SUFFIX_RE.sub("", ln).strip()
        if ln:
            lines.append(ln)
    return "\n".join(lines).strip()


def _quad_to_det(quad: list, text: str, conf: float) -> _Det | None:
    t = (text or "").strip()
    if not t or conf < MIN_CONFIDENCE or _is_zalo_hd_badge(t):
        return None
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    return _Det(
        x1=int(min(xs)),
        y1=int(min(ys)),
        x2=int(max(xs)),
        y2=int(max(ys)),
        text=t,
        conf=float(conf),
    )


def _upscale_for_ocr(img: Image.Image, scale: float) -> tuple[Image.Image, float]:
    if scale <= 1.0:
        return img, 1.0
    w, h = img.size
    if w < 1 or h < 1:
        return img, 1.0
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    return img.resize((nw, nh), Image.Resampling.LANCZOS), scale


def _scale_det_back(det: _Det, factor: float) -> _Det:
    if factor <= 1.0:
        return det
    inv = 1.0 / factor
    return _Det(
        x1=int(det.x1 * inv),
        y1=int(det.y1 * inv),
        x2=max(int(det.x1 * inv) + 1, int(det.x2 * inv)),
        y2=max(int(det.y1 * inv) + 1, int(det.y2 * inv)),
        text=det.text,
        conf=det.conf,
    )


def _run_ocr_on_image(img: Image.Image, *, upscale: float | None = None) -> list[_Det]:
    factor = upscale if upscale is not None else OCR_UPSCALE
    work, applied = _upscale_for_ocr(img, factor)
    reader = _get_reader()
    arr = np.array(work.convert("RGB"))
    raw = reader.readtext(arr)
    out: list[_Det] = []
    for quad, text, conf in raw:
        det = _quad_to_det(quad, text, conf)
        if det:
            out.append(_scale_det_back(det, applied))
    return out


def _cluster_dets(dets: list[_Det], img_h: int, img_w: int = 0) -> list[_Det]:
    """Gom các dòng OCR gần nhau theo trục dọc; tách cột/block xa nhau theo trục ngang."""
    if not dets:
        return []
    w_ref = max(img_w, max(d.x2 for d in dets), 1)
    y_gap = max(14, int(img_h * Y_GAP_RATIO))
    x_gap = max(48, int(w_ref * X_GAP_RATIO))
    sorted_d = sorted(dets, key=lambda d: (d.y1, d.x1))
    clusters: list[list[_Det]] = [[sorted_d[0]]]

    for det in sorted_d[1:]:
        cluster_max_y = max(d.y2 for d in clusters[-1])
        cluster_min_x = min(d.x1 for d in clusters[-1])
        cluster_max_x = max(d.x2 for d in clusters[-1])
        if det.y1 - cluster_max_y > y_gap:
            clusters.append([det])
            continue
        # Không gộp text hai cột UI (sidebar lẫn / panel phải) vào một bubble
        if det.x1 > cluster_max_x + x_gap or det.x2 < cluster_min_x - x_gap:
            clusters.append([det])
            continue
        clusters[-1].append(det)

    merged: list[_Det] = []
    for group in clusters:
        merged.append(_merge_det_group(group))
    return _merge_transfer_frame_bubbles(merged, img_h, w_ref)


def _merge_det_group(group: list[_Det]) -> _Det:
    x1 = min(d.x1 for d in group)
    y1 = min(d.y1 for d in group)
    x2 = max(d.x2 for d in group)
    y2 = max(d.y2 for d in group)
    lines = [d.text for d in sorted(group, key=lambda d: (d.y1, d.x1))]
    text = "\n".join(lines)
    conf = sum(d.conf for d in group) / len(group)
    return _Det(x1, y1, x2, y2, text, conf)


def _overlap_ratio_x(a: _Det, b: _Det) -> float:
    """Tỉ lệ chồng lấn theo trục X (cùng khung ảnh CK thường > 0.3)."""
    left = max(a.x1, b.x1)
    right = min(a.x2, b.x2)
    if right <= left:
        return 0.0
    overlap = right - left
    min_w = min(a.width, b.width)
    return overlap / min_w if min_w > 0 else 0.0


def _transfer_frame_line_count(text: str) -> int:
    clean = _strip_zalo_hd_noise(text)
    return len([ln for ln in clean.splitlines() if ln.strip()])


def _is_transfer_frame_candidate(group: list[_Det], img_h: int, img_w: int) -> bool:
    """
    Ngoại lệ ảnh chụp CK: khổ dài, nhiều dòng trong một khung UI.
    """
    if not group:
        return False
    total_h = group[-1].y2 - group[0].y1
    combined = "\n".join(d.text for d in sorted(group, key=lambda d: (d.y1, d.x1)))
    clean = _strip_zalo_hd_noise(combined)
    if not clean:
        return False
    line_count = _transfer_frame_line_count(combined)
    if _TRANSFER_HINT_RE.search(clean) or find_transaction_money(clean):
        return True
    # Khung cao + nhiều dòng OCR (bill ngân hàng)
    if total_h >= max(TRANSFER_FRAME_MIN_H, int(img_h * 0.07)) and line_count >= 2:
        return True
    if line_count >= 3 and total_h >= int(TRANSFER_FRAME_MIN_H * 0.85):
        return True
    # Một bubble đã cao — các dòng sau có thể cách xa (OCR tách block)
    if len(group) == 1 and group[0].height >= max(100, int(img_h * 0.09)):
        return True
    # Các dòng xếp chồng cùng cột (chiều rộng tương đương khung chat)
    if len(group) >= 2 and img_w > 0:
        avg_w = sum(d.width for d in group) / len(group)
        if total_h >= TRANSFER_FRAME_MIN_H and avg_w >= img_w * 0.28:
            return True
    return False


def _can_extend_transfer_stack(
    stack: list[_Det],
    nxt: _Det,
    gap: int,
    img_h: int,
    img_w: int,
) -> bool:
    """Cho phép gộp thêm dòng vào stack nếu vẫn trong cùng khung ảnh CK."""
    y_gap = max(100, int(img_h * TRANSFER_FRAME_Y_GAP_RATIO))
    if gap > y_gap:
        return False
    if _overlap_ratio_x(stack[-1], nxt) < TRANSFER_FRAME_X_OVERLAP:
        return False
    trial = stack + [nxt]
    if _is_transfer_frame_candidate(trial, img_h, img_w):
        return True
    if _is_transfer_frame_candidate(stack, img_h, img_w):
        return True
    return False


def _merge_transfer_frame_bubbles(
    bubbles: list[_Det],
    img_h: int,
    img_w: int,
) -> list[_Det]:
    """
    Gộp các bubble OCR liền kề theo chiều dọc thành một tin nếu thuộc ảnh chuyển khoản.

    Ảnh bill trong Zalo: một khung, nhiều dòng xuống dòng — OCR dễ tách thành nhiều cluster;
    bước này khôi phục thành một đoạn chat duy nhất.
    """
    if len(bubbles) < 2:
        return bubbles

    ordered = sorted(bubbles, key=lambda b: (b.y1, b.x1))
    out: list[_Det] = []
    stack: list[_Det] = []

    for b in ordered:
        if not stack:
            stack = [b]
            continue
        gap = b.y1 - stack[-1].y2
        if _can_extend_transfer_stack(stack, b, gap, img_h, img_w):
            stack.append(b)
            continue
        out.append(_merge_det_group(stack) if len(stack) > 1 else stack[0])
        stack = [b]

    if stack:
        out.append(_merge_det_group(stack) if len(stack) > 1 else stack[0])

    return sorted(out, key=lambda b: b.y1)


def _extract_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    return m.group(0) if m else None


def _message_id(text: str, x: int, y: int) -> str:
    h = hashlib.md5(f"{text}|{x}|{y}".encode("utf-8")).hexdigest()[:10]
    return f"msg_{h}"


def _infer_role_from_position(cx: float, chat_x: int, chat_w: int) -> str:
    """Tin mình thường canh phải; đối phương / hệ thống trái hoặc giữa."""
    if chat_w <= 0:
        return "other"
    rel = (cx - float(chat_x)) / float(chat_w)
    return "self" if rel >= SELF_SIDE_ALIGN else "other"


def _offset_dets(dets: list[_Det], dx: int, dy: int) -> list[_Det]:
    return [
        _Det(d.x1 + dx, d.y1 + dy, d.x2 + dx, d.y2 + dy, d.text, d.conf)
        for d in dets
    ]


def _looks_like_transfer_bubble(text: str, bubble: _Det) -> bool:
    clean = _strip_zalo_hd_noise(text)
    if not clean:
        return False
    if _TRANSFER_HINT_RE.search(clean) or find_transaction_money(clean):
        return True
    line_count = _transfer_frame_line_count(clean)
    # Ảnh bill: khung cao, nhiều dòng (đã gộp) hoặc cao nhưng OCR đọc ít chữ
    if bubble.height >= max(TRANSFER_FRAME_MIN_H, 90) and (
        line_count >= 2 or len(clean) < 120
    ):
        return True
    return False


def _reocr_bubble_text(img: Image.Image, bubble: _Det) -> str:
    """OCR lại crop bubble ở độ phân giải cao — cải thiện ảnh chuyển khoản."""
    pad = 6
    x1 = max(0, bubble.x1 - pad)
    y1 = max(0, bubble.y1 - pad)
    x2 = min(img.width, bubble.x2 + pad)
    y2 = min(img.height, bubble.y2 + pad)
    if x2 - x1 < 24 or y2 - y1 < 24:
        return bubble.text
    crop = img.crop((x1, y1, x2, y2))
    dets = _run_ocr_on_image(crop, upscale=OCR_BUBBLE_REOCR_SCALE)
    if not dets:
        return bubble.text
    lines = [d.text for d in sorted(dets, key=lambda d: (d.y1, d.x1))]
    merged = "\n".join(lines).strip()
    return merged or bubble.text


def _finalize_bubble_text(img: Image.Image, bubble: _Det) -> str:
    text = _strip_zalo_hd_noise(bubble.text)
    if _looks_like_transfer_bubble(text, bubble):
        refined = _strip_zalo_hd_noise(_reocr_bubble_text(img, bubble))
        if refined and len(refined) >= len(text) * 0.6:
            return refined
    return text


def _infer_message_type(text: str, bubble: _Det) -> str:
    clean = text.strip()
    if not clean:
        return "text"
    if _looks_like_transfer_bubble(clean, bubble):
        # Một khung ảnh CK — toàn bộ text trong khung = một tin
        if (
            find_transaction_money(clean)
            or _TRANSFER_HINT_RE.search(clean)
            or _transfer_frame_line_count(clean) >= 2
            or bubble.height >= TRANSFER_FRAME_MIN_H
        ):
            return "transaction_image"
    return "text"


def ocr_messages(
    img: Image.Image,
    chat_x: int,
    chat_y: int,
    chat_w: int,
    chat_h: int,
) -> list[MessageItem]:
    """OCR vùng chat và map thành danh sách MessageItem."""
    crop = img.crop((chat_x, chat_y, chat_x + chat_w, chat_y + chat_h))
    dets = _run_ocr_on_image(crop)
    dets = _offset_dets(dets, chat_x, chat_y)
    h_ref = max(chat_h, 1)
    w_ref = max(chat_w, 1)
    bubbles = _cluster_dets(dets, h_ref, w_ref)

    messages: list[MessageItem] = []
    for b in bubbles:
        text = _finalize_bubble_text(img, b)
        if not text:
            continue
        w = max(1, b.x2 - b.x1)
        h = max(1, b.y2 - b.y1)
        cx = (b.x1 + b.x2) / 2.0
        if is_date_separator_text(text) and is_date_separator_centered(cx, chat_x, chat_w):
            role = "system"
            msg_type = "date_separator"
        else:
            role = _infer_role_from_position(cx, chat_x, chat_w)
            msg_type = _infer_message_type(text, b)
        messages.append(
            MessageItem(
                id=_message_id(text, b.x1, b.y1),
                x=b.x1,
                y=b.y1,
                width=w,
                height=h,
                type=msg_type,
                date=_extract_date(text),
                text=text,
                role=role,
            )
        )
    messages.sort(key=lambda m: m.y)
    return messages


def ocr_sidebar(
    img: Image.Image,
    sidebar_w: int,
) -> list[SidebarItem]:
    """OCR cột sidebar trái (danh sách hội thoại)."""
    if sidebar_w < 40:
        return []
    crop = img.crop((0, 0, sidebar_w, img.height))
    dets = _run_ocr_on_image(crop)
    rows = _cluster_dets(dets, img.height, sidebar_w)

    items: list[SidebarItem] = []
    for row in rows:
        if len(row.text) < 2:
            continue
        w = max(1, row.x2 - row.x1)
        h = max(1, row.y2 - row.y1)
        items.append(
            SidebarItem(
                name=row.text[:120],
                x=row.x1,
                y=row.y1,
                width=w,
                height=h,
            )
        )
    items.sort(key=lambda s: s.y)
    return items
