"""
YOLO nhận diện vùng UI (sidebar, chat_region, right_panel) → LayoutRatios.
Nếu không có model / không detect được: suy luận từ ảnh (CV), không dùng preset cố định.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from backend import config as cfg
from backend.reconciliation.layout_models import LayoutRatios

logger = logging.getLogger(__name__)

# Class names khớp model train (markdown.md §6.2)
YOLO_CLASS_SIDEBAR = "sidebar"
YOLO_CLASS_CHAT = "chat_region"
YOLO_CLASS_RIGHT = "right_panel"

_yolo_model = None
_yolo_load_failed = False


@dataclass(frozen=True)
class _NormBox:
    x: float
    y: float
    w: float
    h: float
    conf: float = 0.0


def _clamp_ratio(v: float, lo: float = 0.0, hi: float = 0.45) -> float:
    return max(lo, min(hi, float(v)))


def _boxes_to_ratios(
    chat: _NormBox | None,
    sidebar: _NormBox | None,
    right_panel: _NormBox | None,
) -> LayoutRatios:
    """Đổi bbox normalized YOLO → tỉ lệ cắt vùng OCR."""
    sidebar_r = 0.18
    right_r = 0.0
    top_r = 0.06
    bottom_r = 0.08

    if chat and chat.w > 0.05 and chat.h > 0.2:
        sidebar_r = _clamp_ratio(chat.x, 0.12, 0.42)
        right_r = _clamp_ratio(1.0 - chat.x - chat.w, 0.0, 0.40)
        top_r = _clamp_ratio(chat.y, 0.02, 0.22)
        bottom_r = _clamp_ratio(1.0 - chat.y - chat.h, 0.04, 0.25)

    if sidebar and sidebar.w > 0.05:
        if sidebar.x < 0.15:
            sidebar_r = _clamp_ratio(sidebar.x + sidebar.w, 0.12, 0.42)
        else:
            sidebar_r = _clamp_ratio(sidebar.w, 0.12, 0.42)

    if right_panel and right_panel.w > 0.03:
        if right_panel.x > 0.55:
            right_r = _clamp_ratio(right_panel.w, 0.0, 0.40)
        else:
            right_r = _clamp_ratio(1.0 - right_panel.x, 0.0, 0.40)

    return LayoutRatios(
        sidebar=sidebar_r,
        right=right_r,
        inner_top=top_r,
        bottom=bottom_r,
    )


def _resolve_model_path() -> Path | None:
    raw = (cfg.YOLO_LAYOUT_MODEL or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.BASE_DIR / path
    return path if path.is_file() else None


def _get_yolo_model():
    global _yolo_model, _yolo_load_failed
    if _yolo_load_failed:
        return None
    if _yolo_model is not None:
        return _yolo_model
    model_path = _resolve_model_path()
    if model_path is None:
        _yolo_load_failed = True
        logger.warning(
            "YOLO layout: không tìm thấy model tại %s — dùng suy luận CV từ ảnh.",
            cfg.YOLO_LAYOUT_MODEL or "(YOLO_LAYOUT_MODEL chưa set)",
        )
        return None
    try:
        from ultralytics import YOLO

        _yolo_model = YOLO(str(model_path))
        logger.info("YOLO layout model loaded: %s", model_path)
        return _yolo_model
    except Exception as exc:
        _yolo_load_failed = True
        logger.warning("YOLO layout: không load được model (%s) — dùng CV.", exc)
        return None


def _pick_best(boxes: list[_NormBox]) -> _NormBox | None:
    if not boxes:
        return None
    return max(boxes, key=lambda b: b.conf * b.w * b.h)


def _run_yolo(img: Image.Image) -> tuple[LayoutRatios | None, str]:
    model = _get_yolo_model()
    if model is None:
        return None, "cv"

    w, h = img.size
    arr = np.array(img.convert("RGB"))
    try:
        results = model.predict(arr, verbose=False, conf=float(cfg.YOLO_LAYOUT_CONF))
    except Exception as exc:
        logger.warning("YOLO predict lỗi: %s", exc)
        return None, "cv"

    if not results:
        return None, "yolo"

    result = results[0]
    names = result.names or {}
    by_class: dict[str, list[_NormBox]] = {
        YOLO_CLASS_SIDEBAR: [],
        YOLO_CLASS_CHAT: [],
        YOLO_CLASS_RIGHT: [],
    }

    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None, "yolo"

    for box in boxes:
        cls_id = int(box.cls[0])
        label = str(names.get(cls_id, "")).lower().strip()
        if label not in by_class:
            continue
        xyxy = box.xyxy[0].tolist()
        x1, y1, x2, y2 = xyxy
        conf = float(box.conf[0]) if box.conf is not None else 0.0
        by_class[label].append(
            _NormBox(
                x=x1 / w,
                y=y1 / h,
                w=(x2 - x1) / w,
                h=(y2 - y1) / h,
                conf=conf,
            )
        )

    chat = _pick_best(by_class[YOLO_CLASS_CHAT])
    sidebar = _pick_best(by_class[YOLO_CLASS_SIDEBAR])
    right = _pick_best(by_class[YOLO_CLASS_RIGHT])

    if not chat and not sidebar:
        return None, "yolo"

    ratios = _boxes_to_ratios(chat, sidebar, right)
    return ratios, "yolo"


def _infer_layout_cv(img: Image.Image) -> LayoutRatios:
    """
    Suy luận tỉ lệ từ ảnh chụp (cột/ hàng có biên dọc mạnh) — không dùng preset app_type.
    """
    gray = np.array(img.convert("L"), dtype=np.float32)
    h, w = gray.shape
    if w < 80 or h < 80:
        return LayoutRatios(sidebar=0.2, right=0.0, inner_top=0.08, bottom=0.1)

    col_mean = gray.mean(axis=0)
    col_grad = np.abs(np.diff(col_mean))
    if col_grad.size == 0:
        return LayoutRatios(sidebar=0.2, right=0.0, inner_top=0.08, bottom=0.1)

    # Biên phải cột sidebar thường nằm 10–35% chiều rộng (tránh peak sớm trong nền sidebar)
    scan_start = int(w * 0.10)
    scan_end = int(w * 0.35)
    if scan_end > scan_start + 4:
        peak = scan_start + int(np.argmax(col_grad[scan_start:scan_end]))
        sidebar_r = _clamp_ratio((peak + 2) / w, 0.17, 0.32)
    else:
        sidebar_r = 0.20

    right_r = 0.0
    # Biên trái panel phụ thường nằm 65–92% chiều rộng
    right_scan_start = int(w * 0.65)
    if right_scan_start < w - 2:
        right_slice = col_grad[right_scan_start:]
        if right_slice.size > 2:
            right_peak = right_scan_start + int(np.argmax(right_slice))
            right_edge = (right_peak + 1) / w
            if right_edge < 0.92:
                right_r = _clamp_ratio(1.0 - right_edge, 0.0, 0.35)

    mid_x0 = int(w * sidebar_r) + 8
    mid_x1 = int(w * (1.0 - right_r)) - 8
    mid_x0 = max(0, min(mid_x0, w - 20))
    mid_x1 = max(mid_x0 + 20, min(mid_x1, w))

    chat_strip = gray[:, mid_x0:mid_x1]
    row_mean = chat_strip.mean(axis=1)
    row_grad = np.abs(np.diff(row_mean))

    top_scan = int(h * 0.28)
    bottom_scan_start = int(h * 0.72)

    top_r = 0.06
    if top_scan > 2 and row_grad[:top_scan].size > 0:
        top_peak = int(np.argmax(row_grad[:top_scan]))
        top_r = _clamp_ratio((top_peak + 1) / h, 0.03, 0.18)

    bottom_r = 0.08
    if bottom_scan_start < h - 2 and row_grad[bottom_scan_start:].size > 0:
        bottom_peak = bottom_scan_start + int(np.argmax(row_grad[bottom_scan_start:]))
        bottom_edge = (bottom_peak + 1) / h
        if bottom_edge > 0.78:
            bottom_r = _clamp_ratio(1.0 - bottom_edge, 0.05, 0.22)

    return LayoutRatios(
        sidebar=sidebar_r,
        right=right_r,
        inner_top=top_r,
        bottom=bottom_r,
    )


def detect_layout_ratios_from_image(img: Image.Image) -> tuple[LayoutRatios, str]:
    """
    Trả (LayoutRatios, source) với source ∈ yolo | cv.
    Luôn suy ra từ ảnh hiện tại; không đọc preset zalo_pc / zalo_web.
    """
    ratios, source = _run_yolo(img)
    if ratios is not None:
        return ratios, source
    cv_ratios = _infer_layout_cv(img)
    return cv_ratios, "cv"
