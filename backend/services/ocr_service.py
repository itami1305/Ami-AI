"""
OCR service — wrapper pipeline OCR (upscale, detect text, cache tin nhắn).
"""

from __future__ import annotations

from backend.reconciliation.models import OcrPixelResponse
from backend.reconciliation.ocr_service import process_screenshot as _process_screenshot


def process_ocr(
    image_bytes: bytes,
    session_id: str,
    app_type: str | None = None,
    *,
    cropped: bool = False,
) -> OcrPixelResponse:
    """OCR ảnh — cropped=True khi app đã gửi vùng chat (loop-2)."""
    return _process_screenshot(
        image_bytes,
        session_id,
        app_type=app_type,
        cropped=cropped,
    )
