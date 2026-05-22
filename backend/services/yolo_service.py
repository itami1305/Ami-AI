"""
YOLO / CV — nhận diện bố cục màn hình, cache layout theo session.
Trả schema tham chiếu yolo.json (chat_region, sidebar normalized).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from typing import Any

from PIL import Image

from backend.reconciliation.layout_regions import (
    compute_layout,
    refine_chat_rect,
    resolve_layout_ratios,
)
from backend.reconciliation.ocr_engine import ocr_sidebar


def detect_layout(
    image_bytes: bytes,
    session_id: str | None = None,
    app_type: str | None = None,
    *,
    force_refresh: bool = True,
) -> dict[str, Any]:
    """Phân tích layout từ ảnh full cửa sổ → JSON normalized + cache."""
    sid = session_id or str(uuid.uuid4())
    app = (app_type or "zalo_pc").strip().lower()

    img = Image.open(BytesIO(image_bytes))
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("Ảnh không hợp lệ.")

    ratios, source = resolve_layout_ratios(
        sid,
        app,
        image_bytes,
        width=w,
        height=h,
        force_refresh=force_refresh,
    )
    sidebar_w, cx, cy, cw, ch = compute_layout(w, h, ratios)

    sidebar_items: list[dict[str, Any]] = []
    try:
        raw_sidebar = ocr_sidebar(img, sidebar_w)
        for i, item in enumerate(raw_sidebar):
            if hasattr(item, "model_dump"):
                d = item.model_dump()
            elif isinstance(item, dict):
                d = item
            else:
                d = {
                    "x": getattr(item, "x", 0),
                    "y": getattr(item, "y", 0),
                    "width": getattr(item, "width", 0),
                    "height": getattr(item, "height", 0),
                    "name": getattr(item, "name", ""),
                }
            ix = int(d.get("x", 0))
            iy = int(d.get("y", 0))
            iw = int(d.get("width", 0))
            ih = int(d.get("height", 0))
            name = str(d.get("name", ""))
            sidebar_items.append(
                {
                    "id": f"chat_{i}",
                    "name": name,
                    "bbox": {
                        "x": round(ix / w, 4),
                        "y": round(iy / h, 4),
                        "w": round(iw / w, 4),
                        "h": round(ih / h, 4),
                    },
                    "_px": {"x": ix, "y": iy, "width": iw, "height": ih},
                }
            )
    except Exception:
        sidebar_items = []

    px_items = [it["_px"] for it in sidebar_items if it.get("_px")]
    sidebar_w, cx, cy, cw, ch = refine_chat_rect(
        w, h, sidebar_w, cx, cy, cw, ch, px_items or None
    )
    for it in sidebar_items:
        it.pop("_px", None)

    chat_region = {
        "x": round(cx / w, 4),
        "y": round(cy / h, 4),
        "w": round(cw / w, 4),
        "h": round(ch / h, 4),
    }
    sidebar_region = {
        "x": 0.0,
        "y": round(cy / h, 4),
        "w": round(sidebar_w / w, 4),
        "h": round(ch / h, 4),
    }

    return {
        "session_id": sid,
        "app_type": app,
        "chat_detected": cw > 0 and ch > 0,
        "image_width": w,
        "image_height": h,
        "layout_source": source,
        "chat_region": chat_region,
        "sidebar_region": sidebar_region,
        "sidebar": sidebar_items,
    }
