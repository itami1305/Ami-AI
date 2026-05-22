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

# --- Ngưỡng gom dòng thành một bubble ---
Y_GAP_RATIO = 0.025
MIN_CONFIDENCE = 0.25
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


def _run_ocr_on_image(img: Image.Image) -> list[_Det]:
    reader = _get_reader()
    arr = np.array(img.convert("RGB"))
    raw = reader.readtext(arr)
    out: list[_Det] = []
    for quad, text, conf in raw:
        det = _quad_to_det(quad, text, conf)
        if det:
            out.append(det)
    return out


def _cluster_dets(dets: list[_Det], img_h: int) -> list[_Det]:
    """Gom các dòng OCR gần nhau theo trục dọc."""
    if not dets:
        return []
    y_gap = max(12, int(img_h * Y_GAP_RATIO))
    sorted_d = sorted(dets, key=lambda d: (d.y1, d.x1))
    clusters: list[list[_Det]] = [[sorted_d[0]]]

    for det in sorted_d[1:]:
        prev = clusters[-1][-1]
        cluster_max_y = max(d.y2 for d in clusters[-1])
        if det.y1 - cluster_max_y <= y_gap:
            clusters[-1].append(det)
        else:
            clusters.append([det])

    merged: list[_Det] = []
    for group in clusters:
        x1 = min(d.x1 for d in group)
        y1 = min(d.y1 for d in group)
        x2 = max(d.x2 for d in group)
        y2 = max(d.y2 for d in group)
        text = " ".join(d.text for d in sorted(group, key=lambda d: (d.y1, d.x1)))
        conf = sum(d.conf for d in group) / len(group)
        merged.append(_Det(x1, y1, x2, y2, text, conf))
    return merged


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
    bubbles = _cluster_dets(dets, h_ref)

    messages: list[MessageItem] = []
    for b in bubbles:
        text = _strip_zalo_hd_noise(b.text)
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
            msg_type = "text"
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
    rows = _cluster_dets(dets, img.height)

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
