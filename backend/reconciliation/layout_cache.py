"""
Cache tỉ lệ layout (sidebar / panel phải / header / ô nhập) theo phiên đối soát.
Nguồn: YOLO hoặc suy luận từ ảnh — OCR đọc cache, không dùng preset cố định.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.reconciliation.layout_models import LayoutRatios

logger = logging.getLogger(__name__)


@dataclass
class CachedLayoutEntry:
    ratios: LayoutRatios
    source: str  # yolo | cv
    width: int = 0
    height: int = 0


_layout_ratio_cache: dict[str, CachedLayoutEntry] = {}


def layout_cache_key(session_id: str, app_type: str) -> str:
    sid = (session_id or "").strip() or "_default"
    app = (app_type or "zalo_pc").strip().lower()
    return f"{sid}:{app}"


def get_cached_layout(session_id: str, app_type: str) -> CachedLayoutEntry | None:
    return _layout_ratio_cache.get(layout_cache_key(session_id, app_type))


def set_cached_layout(
    session_id: str,
    app_type: str,
    ratios: LayoutRatios,
    *,
    source: str,
    width: int = 0,
    height: int = 0,
) -> None:
    key = layout_cache_key(session_id, app_type)
    _layout_ratio_cache[key] = CachedLayoutEntry(
        ratios=ratios,
        source=source,
        width=width,
        height=height,
    )
    logger.info(
        "Layout cache set %s (%s): sidebar=%.3f right=%.3f top=%.3f bottom=%.3f",
        key,
        source,
        ratios.sidebar,
        ratios.right,
        ratios.inner_top,
        ratios.bottom,
    )


def clear_layout_cache(session_id: str | None = None) -> None:
    if not session_id:
        _layout_ratio_cache.clear()
        return
    prefix = f"{session_id.strip()}:"
    for key in list(_layout_ratio_cache.keys()):
        if key.startswith(prefix):
            del _layout_ratio_cache[key]


def layout_cache_stats() -> dict[str, Any]:
    return {
        "entries": len(_layout_ratio_cache),
        "keys": list(_layout_ratio_cache.keys()),
    }
