"""
Tính vùng sidebar / chat cho pipeline OCR reconciliation.
Tỉ lệ lấy từ cache (YOLO/CV trên ảnh), không dùng preset cố định theo app_type.
"""

from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image

from backend import config as cfg
from backend.reconciliation.layout_cache import get_cached_layout, set_cached_layout
from backend.reconciliation.layout_models import LayoutRatios  # noqa: F401 — re-export

logger = logging.getLogger(__name__)

__all__ = [
    "LayoutRatios",
    "apply_env_overrides",
    "resolve_layout_ratios",
    "compute_layout",
    "refine_chat_rect",
]


def _env_float_optional(name: str) -> float | None:
    raw = getattr(cfg, name, None)
    if raw is None or raw == "":
        return None
    return float(raw)


def apply_env_overrides(ratios: LayoutRatios) -> LayoutRatios:
    """Cho phép override thủ công từng tỉ lệ qua .env (nếu set)."""
    sidebar = _env_float_optional("CHAT_SIDEBAR_RATIO")
    right = _env_float_optional("CHAT_RIGHT_RATIO")
    inner_top = _env_float_optional("CHAT_INNER_TOP_RATIO")
    bottom = _env_float_optional("CHAT_BOTTOM_RATIO")
    return LayoutRatios(
        sidebar=sidebar if sidebar is not None else ratios.sidebar,
        right=right if right is not None else ratios.right,
        inner_top=inner_top if inner_top is not None else ratios.inner_top,
        bottom=bottom if bottom is not None else ratios.bottom,
    )


def resolve_layout_ratios(
    session_id: str,
    app_type: str | None,
    image_bytes: bytes | None = None,
    *,
    width: int = 0,
    height: int = 0,
    force_refresh: bool = False,
) -> tuple[LayoutRatios, str]:
    """
    Lấy tỉ lệ layout cho OCR:
    1) Cache theo session_id + app_type (nếu có và không force_refresh)
    2) YOLO trên ảnh (hoặc CV nếu không có model) → ghi cache
    """
    # Import lazy — tránh circular import lúc load module
    from backend.reconciliation.vision.yolo_layout import detect_layout_ratios_from_image

    app = (app_type or "zalo_pc").strip().lower()

    if not force_refresh:
        cached = get_cached_layout(session_id, app)
        if cached is not None:
            size_changed = False
            if width > 0 and height > 0 and cached.width > 0 and cached.height > 0:
                dw = abs(width - cached.width) / cached.width
                dh = abs(height - cached.height) / cached.height
                size_changed = dw > 0.08 or dh > 0.08
            if not size_changed:
                return apply_env_overrides(cached.ratios), f"cache:{cached.source}"

    if not image_bytes:
        raise ValueError(
            "Chưa có layout trong cache và không có ảnh để chạy YOLO. "
            "Gửi screenshot kèm session_id hoặc gọi /perceive trước."
        )

    img = Image.open(BytesIO(image_bytes))
    w, h = img.size
    ratios, source = detect_layout_ratios_from_image(img)
    ratios = apply_env_overrides(ratios)
    set_cached_layout(
        session_id,
        app,
        ratios,
        source=source,
        width=w,
        height=h,
    )
    logger.info(
        "Layout detected (%s) session=%s app=%s %dx%d",
        source,
        session_id,
        app,
        w,
        h,
    )
    return ratios, source


def compute_layout(
    width: int,
    height: int,
    ratios: LayoutRatios,
) -> tuple[int, int, int, int, int]:
    """Trả (sidebar_width, chat_x, chat_y, chat_width, chat_height) — pixel."""
    w = max(1, width)
    h = max(1, height)

    sidebar_w = max(40, min(int(w * ratios.sidebar), w // 2))
    right_w = max(0, min(int(w * ratios.right), w - sidebar_w - 80))
    inner_top = max(0, min(int(h * ratios.inner_top), h // 3))
    bottom_h = max(0, min(int(h * ratios.bottom), h // 3))

    chat_x = sidebar_w
    chat_y = inner_top
    chat_w = max(1, w - sidebar_w - right_w)
    chat_h = max(1, h - inner_top - bottom_h)
    return sidebar_w, chat_x, chat_y, chat_w, chat_h


def refine_chat_rect(
    width: int,
    height: int,
    sidebar_w: int,
    chat_x: int,
    chat_y: int,
    chat_w: int,
    chat_h: int,
    sidebar_items: list[dict] | None = None,
) -> tuple[int, int, int, int, int]:
    """
    Căn lại khung chat sau OCR sidebar — tránh crop lẫn cột danh sách hội thoại.

    Nếu có item sidebar, đẩy mép trái chat sang phải tới sát cạnh phải sidebar (+padding).
    """
    w = max(1, width)
    h = max(1, height)
    right_w = max(0, w - chat_x - chat_w)
    pad = 10

    if sidebar_items:
        edge = 0
        for item in sidebar_items:
            ix = int(item.get("x", 0))
            iw = int(item.get("width", item.get("w", 0)))
            edge = max(edge, ix + iw)
        if edge > 0:
            sidebar_w = max(sidebar_w, min(edge + pad, int(w * 0.38)))

    chat_x = max(sidebar_w, chat_x)
    chat_w = max(80, w - chat_x - right_w)
    chat_h = max(1, min(chat_h, h - chat_y))
    return sidebar_w, chat_x, chat_y, chat_w, chat_h
