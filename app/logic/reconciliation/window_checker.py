"""
Tìm cửa sổ Zalo / Chrome (Win32) — dùng trước khi chụp màn hình.
"""

from __future__ import annotations

import sys
from typing import Literal

CaptureTargetId = Literal["zalo", "chrome"]

CAPTURE_TARGETS: dict[CaptureTargetId, dict] = {
    "zalo": {
        "label": "Zalo PC",
        "keywords": ["zalo"],
        "exclude": ["zalo api", "installer"],
    },
    "chrome": {
        "label": "Google Chrome",
        "keywords": ["google chrome", "chrome"],
        "exclude": [],
    },
}


class CaptureError(RuntimeError):
    """Không tìm thấy hoặc không chụp được cửa sổ."""


def _require_win32():
    try:
        import win32con  # noqa: F401
        import win32gui

        return win32gui, win32con
    except ImportError as exc:
        raise CaptureError(
            "Thiếu pywin32 (chỉ Windows). Chạy: pip install -r requirements-automation.txt"
        ) from exc


def _title_matches(title: str, keywords: list[str], exclude: list[str]) -> bool:
    tl = title.lower().strip()
    if not tl:
        return False
    if any(ex in tl for ex in exclude):
        return False
    return any(kw in tl for kw in keywords)


def find_window(target: CaptureTargetId) -> tuple[int, str, tuple[int, int, int, int]]:
    """Tìm cửa sổ lớn nhất khớp target. Trả (hwnd, title, rect)."""
    if target not in CAPTURE_TARGETS:
        raise CaptureError(f"Target không hợp lệ: {target}")

    cfg = CAPTURE_TARGETS[target]
    win32gui, _ = _require_win32()

    candidates: list[tuple[int, str, tuple[int, int, int, int], int]] = []

    def _callback(hwnd: int, _: None) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not _title_matches(title, cfg["keywords"], cfg.get("exclude", [])):
            return
        try:
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return
        left, top, right, bottom = rect
        w, h = right - left, bottom - top
        if w < 200 or h < 200:
            return
        candidates.append((hwnd, title, rect, w * h))

    win32gui.EnumWindows(_callback, None)

    if not candidates:
        label = cfg["label"]
        raise CaptureError(f"Không tìm thấy cửa sổ {label}. Hãy mở app và thử lại.")

    candidates.sort(key=lambda c: c[3], reverse=True)
    hwnd, title, rect, _ = candidates[0]
    return hwnd, title, rect


def list_open_targets() -> dict[CaptureTargetId, str | None]:
    """Liệt kê cửa sổ đang mở cho từng target."""
    out: dict[CaptureTargetId, str | None] = {}
    for tid in CAPTURE_TARGETS:
        try:
            _, title, _ = find_window(tid)  # type: ignore[arg-type]
            out[tid] = title
        except CaptureError:
            out[tid] = None
    return out


__all__ = [
    "CAPTURE_TARGETS",
    "CaptureError",
    "CaptureTargetId",
    "find_window",
    "list_open_targets",
]
