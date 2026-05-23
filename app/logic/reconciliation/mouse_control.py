"""
Điều khiển chuột — click sidebar, cuộn, đưa chuột vào hội thoại (pynput).
"""

from __future__ import annotations

import sys
import time

from app.config import CHAT_LOAD_WAIT, SCROLL_AMOUNT, SCROLL_PAUSE
from app.logic.reconciliation.bbox import (
    bbox_center_screen,
    chat_scroll_clicks,
    chat_scroll_focus_screen,
    resolve_click_point,
)
from app.logic.reconciliation.models import AgentAction
from app.logic.reconciliation.window_checker import CaptureTargetId

_mouse = None  # type: ignore[var-annotated]
_Button = None  # type: ignore[var-annotated]
_HAS_PYNPUT = False

try:
    from pynput.mouse import Button as _Button  # type: ignore
    from pynput.mouse import Controller as _MouseController  # type: ignore

    _mouse = _MouseController()
    _HAS_PYNPUT = True
except ImportError:
    pass

# Chờ ngắn sau click focus — đủ để Zalo nhận focus, không chặn loop-2 như CHAT_LOAD_WAIT.
_FOCUS_CLICK_PAUSE = 0.15


def _require_mouse() -> None:
    if not _HAS_PYNPUT:
        raise RuntimeError(
            "Chưa cài 'pynput'. Hãy chạy:\n"
            "    pip install -r requirements-automation.txt"
        )


def _ensure_automation_ready() -> None:
    _require_mouse()
    if sys.platform == "win32":
        from app.logic.reconciliation.screenshot import _ensure_windows_dpi_awareness

        _ensure_windows_dpi_awareness()


def scroll_chat_up(amount: int | None = None) -> None:
    _ensure_automation_ready()
    clicks = amount if amount is not None else SCROLL_AMOUNT
    _mouse.scroll(0, clicks)  # type: ignore[union-attr]
    time.sleep(SCROLL_PAUSE)


def move_to_point(x: int, y: int) -> None:
    _ensure_automation_ready()
    _mouse.position = (x, y)  # type: ignore[union-attr]
    time.sleep(0.05)


def click_at(x: int, y: int) -> None:
    move_to_point(x, y)
    _mouse.click(_Button.left, 1)  # type: ignore[union-attr]
    time.sleep(CHAT_LOAD_WAIT)


def click_focus_at(x: int, y: int) -> None:
    """Click nhẹ vào vùng chat để nhận focus trước khi cuộn (không chờ load chat)."""
    _ensure_automation_ready()
    _mouse.position = (x, y)  # type: ignore[union-attr]
    time.sleep(0.05)
    _mouse.click(_Button.left, 1)  # type: ignore[union-attr]
    time.sleep(_FOCUS_CLICK_PAUSE)


def click_next_chat(sidebar_x: int, next_chat_y: int, row_height: int = 80) -> int:
    click_at(sidebar_x, next_chat_y)
    return next_chat_y + row_height


def wait_ms(ms: int) -> None:
    time.sleep(max(ms, 0) / 1000.0)


def _snapshot_for_focus(
    snapshot: dict,
    yolo_layout: dict | None,
) -> dict:
    """Bổ sung chat_region từ layout YOLO nếu snapshot OCR crop thiếu."""
    if (snapshot or {}).get("chat_region"):
        return snapshot
    cr = (yolo_layout or {}).get("chat_region")
    if not cr:
        return snapshot
    return {**snapshot, "chat_region": cr}


def focus_chat_center(
    snapshot: dict,
    offset_x: int,
    offset_y: int,
    screen_w: int,
    screen_h: int,
    *,
    capture_target: CaptureTargetId | None = None,
    yolo_layout: dict | None = None,
) -> tuple[int, int]:
    """
    Đưa cửa sổ chat lên foreground và click vào giữa khung hội thoại.

    Chỉ move_to_point không đủ — Zalo/Chrome cần click để vùng tin nhắn nhận wheel scroll.
    """
    _ensure_automation_ready()
    if capture_target:
        from app.logic.reconciliation.screenshot import focus_capture_target

        focus_capture_target(capture_target)

    snap = _snapshot_for_focus(snapshot, yolo_layout)
    cx, cy = chat_scroll_focus_screen(
        offset_x, offset_y, screen_w, screen_h, snapshot=snap
    )
    click_focus_at(cx, cy)
    return cx, cy


def execute_action(
    action: AgentAction,
    snapshot: dict,
    offset_x: int,
    offset_y: int,
    screen_w: int,
    screen_h: int,
    *,
    sidebar_x: int,
    next_chat_y: int,
) -> int:
    name = action.action
    params = action.params or {}

    if name == "scroll":
        direction = params.get("direction", "up")
        if "amount" in params:
            amount = int(params["amount"])
        else:
            amount = chat_scroll_clicks(snapshot, screen_w, screen_h)
        scroll_chat_up(amount if direction == "up" else -amount)
        return next_chat_y

    if name == "click":
        pt = resolve_click_point(params, snapshot, offset_x, offset_y, screen_w, screen_h)
        if pt:
            click_at(*pt)
        return next_chat_y

    if name == "open_chat":
        idx = int(params.get("sidebar_index", 0))
        sidebar = snapshot.get("sidebar") or []
        if sidebar and 0 <= idx < len(sidebar):
            sx, sy = bbox_center_screen(sidebar[idx], offset_x, offset_y, screen_w, screen_h)
            click_at(sx, sy)
            return next_chat_y
        return click_next_chat(sidebar_x, next_chat_y)

    if name == "wait":
        wait_ms(int(params.get("ms", 500)))
        return next_chat_y

    return next_chat_y


__all__ = [
    "click_at",
    "click_focus_at",
    "click_next_chat",
    "execute_action",
    "focus_chat_center",
    "move_to_point",
    "scroll_chat_up",
    "wait_ms",
]
