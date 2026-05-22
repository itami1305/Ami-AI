"""BBox normalized ↔ pixel ↔ màn hình — §7."""

from __future__ import annotations

from typing import Any


def _bbox_dims(bbox: dict) -> tuple[float, float, float, float]:
    x = float(bbox.get("x", 0))
    y = float(bbox.get("y", 0))
    w = float(bbox.get("w", bbox.get("width", 0)))
    h = float(bbox.get("h", bbox.get("height", 0)))
    return x, y, w, h


def is_normalized_bbox(bbox: dict, screen_w: int, screen_h: int) -> bool:
    """Heuristic: toạ độ [0,1] coi là normalized (YOLO-style trên ảnh)."""
    if not bbox:
        return False
    x, y, w, h = _bbox_dims(bbox)
    return max(x, y, w, h) <= 1.0 and w <= 1.0 and h <= 1.0


def bbox_to_pixels(
    bbox: dict,
    screen_w: int,
    screen_h: int,
    *,
    normalized: bool | None = None,
) -> tuple[int, int, int, int]:
    """Đổi bbox → pixel (x,y,w,h). normalized=None thì tự suy từ is_normalized_bbox."""
    x, y, w, h = _bbox_dims(bbox)
    norm = normalized if normalized is not None else is_normalized_bbox(bbox, screen_w, screen_h)
    if norm and screen_w > 0 and screen_h > 0:
        return (int(x * screen_w), int(y * screen_h), int(w * screen_w), int(h * screen_h))
    return int(x), int(y), int(w), int(h)


def item_to_bbox(item: dict, screen_w: int, screen_h: int) -> dict:
    """Chuẩn hóa một message/sidebar item thành bbox {x,y,w,h} kiểu normalized nếu có kích thước ảnh."""
    if "bbox" in item and isinstance(item["bbox"], dict):
        b = item["bbox"]
        if is_normalized_bbox(b, screen_w, screen_h):
            return b
        px, py, pw, ph = bbox_to_pixels(b, screen_w, screen_h, normalized=False)
        if screen_w > 0 and screen_h > 0:
            return {"x": px / screen_w, "y": py / screen_h, "w": pw / screen_w, "h": ph / screen_h}
        return b
    if "width" in item or "w" in item:
        px = int(item.get("x", 0))
        py = int(item.get("y", 0))
        pw = int(item.get("width", item.get("w", 0)))
        ph = int(item.get("height", item.get("h", 0)))
        if screen_w > 0 and screen_h > 0:
            return {"x": px / screen_w, "y": py / screen_h, "w": pw / screen_w, "h": ph / screen_h}
        return {"x": px, "y": py, "w": pw, "h": ph}
    return {"x": 0, "y": 0, "w": 0, "h": 0}


def bbox_center_screen(
    item: dict,
    offset_x: int,
    offset_y: int,
    screen_w: int,
    screen_h: int,
) -> tuple[int, int]:
    """Tọa độ màn hình tuyệt đối của tâm bbox (cộng offset capture)."""
    bbox = item_to_bbox(item, screen_w, screen_h)
    px, py, pw, ph = bbox_to_pixels(bbox, screen_w, screen_h)
    return offset_x + px + pw // 2, offset_y + py + ph // 2


def resolve_capture_dimensions(
    snapshot: dict | None,
    capture_w: int,
    capture_h: int,
) -> tuple[int, int]:
    """
    Kích thước ảnh dùng để đổi bbox normalized → pixel.

    Ưu tiên snapshot.screen (cùng cơ sở normalize của /perceive); fallback capture state.
    """
    screen = (snapshot or {}).get("screen") or {}
    sw = int(screen.get("width") or 0)
    sh = int(screen.get("height") or 0)
    if sw > 0 and sh > 0:
        return sw, sh
    return max(1, capture_w), max(1, capture_h)


def _chat_region_pixels(snapshot: dict | None, w: int, h: int) -> tuple[int, int, int, int] | None:
    """Vùng chat từ snapshot (normalized) hoặc None nếu không có."""
    cr = (snapshot or {}).get("chat_region") or {}
    if not cr:
        return None
    item = cr if "bbox" in cr else {"bbox": cr}
    bbox = item_to_bbox(item, w, h)
    px, py, pw, ph = bbox_to_pixels(bbox, w, h)
    if pw > 0 and ph > 0:
        return px, py, pw, ph
    return None


def chat_region_layout(
    snapshot: dict | None,
    capture_w: int,
    capture_h: int,
) -> tuple[int, int, int, int]:
    """Khung chat (cx, cy, cw, ch) theo pixel ảnh capture."""
    w, h = resolve_capture_dimensions(snapshot, capture_w, capture_h)
    region = _chat_region_pixels(snapshot, w, h)
    if region:
        return region
    # Không có chat_region trong snapshot — dùng toàn ảnh (layout do backend OCR đã cache)
    return 0, 0, w, h


def chat_scroll_clicks(
    snapshot: dict | None,
    capture_w: int,
    capture_h: int,
) -> int:
    """Số nấc cuộn ≈ một lần cuộn bằng chiều cao khung chat."""
    from app.config import SCROLL_AMOUNT, SCROLL_PIXELS_PER_CLICK

    _cx, _cy, _cw, ch = chat_region_layout(snapshot, capture_w, capture_h)
    ppc = max(1, SCROLL_PIXELS_PER_CLICK)
    return max(1, ch // ppc) if ch > 0 else SCROLL_AMOUNT


def chat_scroll_focus_screen(
    offset_x: int,
    offset_y: int,
    capture_w: int,
    capture_h: int,
    *,
    snapshot: dict | None = None,
) -> tuple[int, int]:
    """
    Điểm click trước khi scroll — giữa vùng hội thoại (không sát viền trái/sidebar).

    Luôn ưu tiên tâm hình học khung chat; chỉ lệch theo centroid tin khi nằm
    rõ ràng trong lõi chat (tránh bbox OCR crop khiến click sát mép trái).
    """
    w, h = resolve_capture_dimensions(snapshot, capture_w, capture_h)
    cx, cy, cw, ch = chat_region_layout(snapshot, capture_w, capture_h)

    ax = cx + cw // 2
    ay = cy + int(ch * 0.45)

    inset_x = max(32, cw // 6)
    inset_y = max(24, ch // 8)

    messages = (snapshot or {}).get("messages") or []
    if messages and not (snapshot or {}).get("cropped_ocr"):
        xs: list[int] = []
        ys: list[int] = []
        for msg in messages:
            bbox = item_to_bbox(msg, w, h)
            px, py, pw, ph = bbox_to_pixels(bbox, w, h)
            if pw > 2 and ph > 2:
                xs.append(px + pw // 2)
                ys.append(py + ph // 2)
        if xs and ys:
            mx = sum(xs) // len(xs)
            my = sum(ys) // len(ys)
            if (
                cx + inset_x < mx < cx + cw - inset_x
                and cy + inset_y < my < cy + ch - inset_y
            ):
                ax, ay = mx, my

    return offset_x + ax, offset_y + ay


def resolve_click_point(
    action_params: dict,
    snapshot: dict,
    offset_x: int,
    offset_y: int,
    screen_w: int,
    screen_h: int,
) -> tuple[int, int] | None:
    """
    Planner có thể trả điểm click qua:
        - bbox_ref: ví dụ "messages.3" → lấy phần tử thứ 3 trong snapshot["messages"].
        - x, y: tọa độ trực tiếp (đã là màn hình hoặc theo quy ước backend — caller chịu trách nhiệm).
    """
    ref = action_params.get("bbox_ref")
    if ref:
        parts = str(ref).split(".", 1)
        if len(parts) == 2:
            collection, idx_s = parts[0], parts[1]
            try:
                idx = int(idx_s)
            except ValueError:
                return None
            items = snapshot.get(collection) or []
            if 0 <= idx < len(items):
                return bbox_center_screen(items[idx], offset_x, offset_y, screen_w, screen_h)
    if "x" in action_params and "y" in action_params:
        return int(action_params["x"]), int(action_params["y"])
    return None
