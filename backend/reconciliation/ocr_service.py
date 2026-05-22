"""
OCR pixel pipeline — EasyOCR (backend.reconciliation.ocr_engine).
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO

from PIL import Image

from backend.reconciliation.layout_regions import compute_layout, resolve_layout_ratios
from backend.reconciliation.ocr_engine import ocr_messages, ocr_sidebar
from backend.reconciliation.cache import get_session
from backend.reconciliation.models import ChatRegion, MessageItem, OcrPixelResponse, SidebarItem

logger = logging.getLogger(__name__)

_ocr_hash_cache: dict[str, OcrPixelResponse] = {}


def _image_hash(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()


def process_screenshot(
    image_bytes: bytes,
    session_id: str,
    app_type: str | None = None,
    *,
    cropped: bool = False,
) -> OcrPixelResponse:
    img_hash = _image_hash(image_bytes)
    cache_key = f"{img_hash}:{'crop' if cropped else 'full'}"
    if cache_key in _ocr_hash_cache:
        return _ocr_hash_cache[cache_key].model_copy(update={"session_id": session_id})

    try:
        img = Image.open(BytesIO(image_bytes))
        w, h = img.size
    except Exception as exc:
        raise ValueError("Không đọc được file ảnh.") from exc

    if cropped:
        layout_source = "cropped"
        cx, cy, cw, ch = 0, 0, w, h
        sidebar_width = 0
        sidebar: list = []
    else:
        ratios, layout_source = resolve_layout_ratios(
            session_id,
            app_type,
            image_bytes,
            width=w,
            height=h,
        )
        sidebar_width, cx, cy, cw, ch = compute_layout(w, h, ratios)
        sidebar = []

    chat_region = ChatRegion(x=cx, y=cy, width=cw, height=ch)

    try:
        messages = ocr_messages(img, cx, cy, cw, ch)
        if not cropped:
            sidebar = ocr_sidebar(img, sidebar_width)
    except Exception as exc:
        logger.exception("OCR thất bại")
        raise RuntimeError(f"OCR lỗi: {exc}. Cài: pip install easyocr") from exc

    session = get_session(session_id)
    session.image_hashes.append(img_hash)

    def _as_message(m) -> MessageItem:
        if isinstance(m, MessageItem):
            return m
        if hasattr(m, "model_dump"):
            return MessageItem.model_validate(m.model_dump())
        return MessageItem.model_validate(m)

    def _as_sidebar(s) -> SidebarItem:
        if isinstance(s, SidebarItem):
            return s
        if hasattr(s, "model_dump"):
            return SidebarItem.model_validate(s.model_dump())
        return SidebarItem.model_validate(s)

    result = OcrPixelResponse(
        session_id=session_id,
        image_width=w,
        image_height=h,
        chat_region=chat_region,
        messages=[_as_message(m) for m in messages],
        sidebar=[_as_sidebar(s) for s in sidebar],
    )
    _ocr_hash_cache[cache_key] = result
    logger.info(
        "Reconciliation OCR (%s, layout=%s, cropped=%s): %dx%d chat@%d,%d %dx%d, %d msg, %d sidebar",
        app_type or "zalo_pc",
        layout_source,
        cropped,
        w,
        h,
        cx,
        cy,
        cw,
        ch,
        len(messages),
        len(sidebar),
    )
    return result
