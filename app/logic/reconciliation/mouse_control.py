"""
Điều khiển chuột — click sidebar, cuộn, đưa chuột vào hội thoại (pynput).
"""

from __future__ import annotations

import time

from app.config import CHAT_LOAD_WAIT, SCROLL_AMOUNT, SCROLL_PAUSE
from app.logic.reconciliation.bbox import (
    bbox_center_screen,
    chat_scroll_clicks,
    chat_scroll_focus_screen,
    resolve_click_point,
)
from app.logic.reconciliation.models import AgentAction

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


def _require_mouse() -> None:
    if not _HAS_PYNPUT:
        raise RuntimeError(
            "Chưa cài 'pynput'. Hãy chạy:\n"
            "    pip install -r requirements-automation.txt"
        )


def scroll_chat_up(amount: int | None = None) -> None:
    _require_mouse()
    clicks = amount if amount is not None else SCROLL_AMOUNT
    _mouse.scroll(0, clicks)  # type: ignore[union-attr]
    time.sleep(SCROLL_PAUSE)


def move_to_point(x: int, y: int) -> None:
    _require_mouse()
    _mouse.position = (x, y)  # type: ignore[union-attr]
    time.sleep(0.05)


def click_at(x: int, y: int) -> None:
    move_to_point(x, y)
    _mouse.click(_Button.left, 1)  # type: ignore[union-attr]
    time.sleep(CHAT_LOAD_WAIT)


def click_next_chat(sidebar_x: int, next_chat_y: int, row_height: int = 80) -> int:
    click_at(sidebar_x, next_chat_y)
    return next_chat_y + row_height


def wait_ms(ms: int) -> None:
    time.sleep(max(ms, 0) / 1000.0)


def focus_chat_center(
    snapshot: dict,
    offset_x: int,
    offset_y: int,
    screen_w: int,
    screen_h: int,
) -> None:
    cx, cy = chat_scroll_focus_screen(
        offset_x, offset_y, screen_w, screen_h, snapshot=snapshot
    )
    move_to_point(cx, cy)


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
        focus_chat_center(snapshot, offset_x, offset_y, screen_w, screen_h)
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
    "click_next_chat",
    "execute_action",
    "focus_chat_center",
    "move_to_point",
    "scroll_chat_up",
    "wait_ms",
]
