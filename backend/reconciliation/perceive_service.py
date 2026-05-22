"""
Perception — OCR pixel → JSON normalized bbox (§7.1).
"""

from __future__ import annotations

import uuid

from backend.reconciliation.models import (
    NormalizedBBox,
    PerceptionMessage,
    PerceptionResponse,
    PerceptionSidebarItem,
    ScreenInfo,
)
from backend.reconciliation.date_separator import is_date_separator_text, resolve_chat_date_display
from backend.reconciliation.ocr_service import process_screenshot


def _to_norm(x: float, y: float, w: float, h: float, sw: int, sh: int) -> NormalizedBBox:
    if sw <= 0 or sh <= 0:
        return NormalizedBBox(x=x, y=y, w=w, h=h)
    return NormalizedBBox(
        x=x / sw,
        y=y / sh,
        w=w / sw,
        h=h / sh,
    )


def _infer_message_type(text: str, *, msg_type: str = "") -> str:
    if msg_type == "date_separator":
        return "date_separator"
    if is_date_separator_text(text):
        return "date_separator"
    low = (text or "").lower()
    if any(k in low for k in ("tổng hợp", "danh sách giao dịch", "báo cáo")):
        return "transaction_summary"
    return "text"


def pixel_to_perception(
    pixel: dict,
    *,
    app_type: str | None = None,
    capture_offset_x: int = 0,
    capture_offset_y: int = 0,
) -> PerceptionResponse:
    cr = pixel.get("chat_region") or {}
    sw = int(pixel.get("image_width") or 0)
    sh = int(pixel.get("image_height") or 0)
    if sw <= 0 or sh <= 0:
        sw = max(int(cr.get("x", 0)) + int(cr.get("width", 0)), 1)
        sh = max(int(cr.get("y", 0)) + int(cr.get("height", 0)), 1)
    if pixel.get("messages"):
        max_y = max(int(m.get("y", 0)) + int(m.get("height", 0)) for m in pixel["messages"])
        sh = max(sh, max_y + 50)
    app = app_type or "zalo_pc"

    chat_region = _to_norm(
        float(cr.get("x", 0)),
        float(cr.get("y", 0)),
        float(cr.get("width", sw)),
        float(cr.get("height", sh)),
        sw,
        sh,
    )

    messages: list[PerceptionMessage] = []
    for msg in pixel.get("messages") or []:
        mid = msg.get("id") or f"msg_{uuid.uuid4().hex[:8]}"
        bbox = _to_norm(
            float(msg.get("x", 0)),
            float(msg.get("y", 0)),
            float(msg.get("width", 0)),
            float(msg.get("height", 0)),
            sw,
            sh,
        )
        text = msg.get("text") or ""
        raw_type = (msg.get("type") or "").strip()
        msg_type = _infer_message_type(text, msg_type=raw_type)
        role = (msg.get("role") or "").strip() or "other"
        if msg_type == "date_separator":
            role = "system"
        msg_date = msg.get("date")
        if msg_type == "date_separator" or is_date_separator_text(text):
            msg_date = resolve_chat_date_display(text) or resolve_chat_date_display(
                str(msg_date or "")
            )
        messages.append(
            PerceptionMessage(
                id=mid,
                role=role,
                type=msg_type,
                text=text,
                date=msg_date,
                bbox=bbox,
            )
        )

    sidebar: list[PerceptionSidebarItem] = []
    for i, item in enumerate(pixel.get("sidebar") or []):
        name = item.get("name") or ""
        bbox = _to_norm(
            float(item.get("x", 0)),
            float(item.get("y", 0)),
            float(item.get("width", 0)),
            float(item.get("height", 0)),
            sw,
            sh,
        )
        sidebar.append(
            PerceptionSidebarItem(
                id=str(item.get("id") or name or f"chat_{i}"),
                name=name,
                bbox=bbox,
            )
        )

    return PerceptionResponse(
        session_id=pixel.get("session_id", ""),
        app_type=app,
        chat_detected=bool(messages or sidebar),
        screen=ScreenInfo(
            width=sw,
            height=sh,
            capture_offset={"x": capture_offset_x, "y": capture_offset_y},
        ),
        chat_region=chat_region,
        messages=messages,
        sidebar=sidebar,
    )


def process_perception(
    image_bytes: bytes,
    session_id: str,
    app_type: str | None = None,
    *,
    capture_offset_x: int = 0,
    capture_offset_y: int = 0,
) -> PerceptionResponse:
    layout_app = app_type or "zalo_pc"
    pixel = process_screenshot(image_bytes, session_id, app_type=layout_app)
    return pixel_to_perception(
        pixel.model_dump(),
        app_type=layout_app,
        capture_offset_x=capture_offset_x,
        capture_offset_y=capture_offset_y,
    )
