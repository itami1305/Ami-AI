"""
Chụp màn hình — full cửa sổ hoặc vùng chat (Windows + pywin32).
"""

from __future__ import annotations

import io
import sys
import time
from dataclasses import dataclass
from typing import Callable, Literal

from app.config import CHAT_TOP_SKIP_PX
from app.logic.reconciliation.window_checker import (
    CAPTURE_TARGETS,
    CaptureError,
    CaptureTargetId,
    find_window,
    list_open_targets,
)

try:
    from PIL import Image, ImageGrab
except ImportError:
    Image = None  # type: ignore
    ImageGrab = None  # type: ignore

_PW_RENDERFULLCONTENT = 2
_dx_camera = None


@dataclass(frozen=True)
class CaptureInfo:
    target: CaptureTargetId
    title: str
    left: int
    top: int
    width: int
    height: int
    top_skip: int
    window_top: int
    method: str = ""


_dpi_awareness_set = False


def _ensure_windows_dpi_awareness() -> None:
    global _dpi_awareness_set
    if _dpi_awareness_set or sys.platform != "win32":
        return
    _dpi_awareness_set = True
    import ctypes

    try:
        if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            raise OSError(ctypes.get_last_error())
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _require_pil() -> None:
    if ImageGrab is None or Image is None:
        raise CaptureError("Thiếu Pillow. Chạy: pip install -r requirements.txt")


def _require_win32():
    try:
        import win32con  # noqa: F401
        import win32gui

        return win32gui, win32con
    except ImportError as exc:
        raise CaptureError(
            "Thiếu pywin32 (chỉ Windows). Chạy: pip install -r requirements-automation.txt"
        ) from exc


def _focus_window(hwnd: int) -> None:
    win32gui, win32con = _require_win32()
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
    except Exception:
        pass


def _is_image_black(img: Image.Image, max_channel: int = 20) -> bool:
    sample = img.resize((48, 48))
    extrema = sample.getextrema()
    if extrema and isinstance(extrema[0], tuple):
        peak = max(ch[1] for ch in extrema)
    else:
        peak = extrema[1] if extrema else 0
    return peak < max_channel


def _get_dxcam():
    global _dx_camera
    if _dx_camera is not None:
        return _dx_camera
    try:
        import dxcam
    except ImportError as exc:
        raise CaptureError(
            "Thiếu dxcam. Chạy: pip install -r requirements-automation.txt"
        ) from exc
    _dx_camera = dxcam.create()
    return _dx_camera


def _grab_dxcam(left: int, top: int, right: int, bottom: int) -> Image.Image:
    _require_pil()
    cam = _get_dxcam()
    frame = cam.grab(region=(left, top, right, bottom))
    if frame is None:
        raise CaptureError("dxcam không lấy được khung hình (region rỗng?).")
    rgb = frame[:, :, ::-1]
    return Image.fromarray(rgb)


def _grab_imagegrab(left: int, top: int, right: int, bottom: int) -> Image.Image:
    _require_pil()
    return ImageGrab.grab(bbox=(left, top, right, bottom))


def _grab_printwindow(hwnd: int, top_skip: int) -> Image.Image:
    _require_pil()
    from ctypes import windll

    import win32gui
    import win32ui

    win32gui_mod, _ = _require_win32()
    left, top, right, bottom = win32gui_mod.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise CaptureError("Kích thước cửa sổ không hợp lệ.")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        ok = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), _PW_RENDERFULLCONTENT)
        if not ok:
            ok = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
        if not ok:
            raise CaptureError("PrintWindow thất bại.")

        bmpinfo = bitmap.GetInfo()
        bmpstr = bitmap.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
        )

        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
    finally:
        win32gui.ReleaseDC(hwnd, hwnd_dc)

    skip = min(top_skip, max(0, img.height - 80))
    if skip > 0:
        img = img.crop((0, skip, img.width, img.height))
    return img


def _capture_region(
    left: int,
    top: int,
    right: int,
    bottom: int,
    *,
    hwnd: int | None = None,
    top_skip: int = 0,
) -> tuple[Image.Image, str]:
    attempts: list[tuple[str, Callable[[], Image.Image]]] = []

    if hwnd is not None and sys.platform == "win32":
        attempts.append(("printwindow", lambda: _grab_printwindow(hwnd, top_skip)))

    if sys.platform == "win32":
        attempts.append(("dxcam", lambda: _grab_dxcam(left, top, right, bottom)))

    attempts.append(("imagegrab", lambda: _grab_imagegrab(left, top, right, bottom)))

    errors: list[str] = []
    for name, grab in attempts:
        try:
            img = grab()
            if _is_image_black(img):
                errors.append(f"{name}: ảnh đen")
                continue
            return img, name
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    detail = "; ".join(errors) if errors else "không rõ"
    raise CaptureError(
        f"Không chụp được cửa sổ (ảnh đen hoặc lỗi). "
        f"Hãy đưa Zalo/Chrome lên trước, không thu nhỏ. Chi tiết: {detail}"
    )


def _image_to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def infer_layout_app_type(title: str, target: CaptureTargetId) -> str:
    tl = (title or "").lower()
    if target == "chrome":
        return "messenger_web"
    if "chrome" in tl or "edge" in tl or "cốc cốc" in tl:
        if "zalo" in tl:
            return "zalo_web"
    return "zalo_pc"


def capture_window(target: CaptureTargetId = "zalo") -> tuple[bytes, CaptureInfo]:
    _ensure_windows_dpi_awareness()
    hwnd, title, rect = find_window(target)
    _focus_window(hwnd)

    win32gui, _ = _require_win32()
    try:
        rect = win32gui.GetWindowRect(hwnd)
    except Exception:
        pass

    win_left, win_top, right, bottom = rect
    win_w = right - win_left
    win_h = bottom - win_top
    if win_w <= 0 or win_h <= 0:
        raise CaptureError(f"Cửa sổ '{title}' có kích thước không hợp lệ.")

    top_skip = min(CHAT_TOP_SKIP_PX, max(0, win_h - 120))
    content_top = win_top + top_skip
    content_h = win_h - top_skip
    if content_h < 100:
        raise CaptureError(f"Cửa sổ '{title}' quá thấp sau khi bỏ {top_skip}px header.")

    img, method = _capture_region(
        win_left,
        content_top,
        right,
        bottom,
        hwnd=hwnd,
        top_skip=top_skip,
    )

    jpeg = _image_to_jpeg(img)
    info = CaptureInfo(
        target=target,
        title=title,
        left=win_left,
        top=content_top,
        width=img.width,
        height=img.height,
        top_skip=top_skip,
        window_top=win_top,
        method=method,
    )
    return jpeg, info


def capture_full_screen() -> bytes:
    for tid in ("zalo", "chrome"):
        try:
            data, _ = capture_window(tid)  # type: ignore[arg-type]
            return data
        except CaptureError:
            continue
    raise CaptureError("Không tìm thấy cửa sổ Zalo PC hoặc Google Chrome.")


def capture_region(x: int, y: int, width: int, height: int) -> bytes:
    _ensure_windows_dpi_awareness()
    img, _ = _capture_region(x, y, x + width, y + height)
    return _image_to_jpeg(img)


def chat_region_screen_rect(
    yolo_layout: dict,
    offset_x: int,
    offset_y: int,
    capture_w: int,
    capture_h: int,
) -> tuple[int, int, int, int]:
    """Tính vùng chat trên màn hình từ layout YOLO normalized."""
    cr = yolo_layout.get("chat_region") or {}
    x = float(cr.get("x", 0))
    y = float(cr.get("y", 0))
    w = float(cr.get("w", 1))
    h = float(cr.get("h", 1))
    px = int(x * capture_w)
    py = int(y * capture_h)
    pw = max(1, int(w * capture_w))
    ph = max(1, int(h * capture_h))
    return offset_x + px, offset_y + py, pw, ph


def capture_chat_region(
    yolo_layout: dict,
    offset_x: int,
    offset_y: int,
    capture_w: int,
    capture_h: int,
) -> bytes:
    """Chụp chỉ vùng chat (loop-2) — payload nhỏ hơn full window."""
    sx, sy, sw, sh = chat_region_screen_rect(
        yolo_layout, offset_x, offset_y, capture_w, capture_h
    )
    return capture_region(sx, sy, sw, sh)


__all__ = [
    "CAPTURE_TARGETS",
    "CaptureError",
    "CaptureInfo",
    "CaptureTargetId",
    "capture_chat_region",
    "capture_full_screen",
    "capture_region",
    "capture_window",
    "chat_region_screen_rect",
    "infer_layout_app_type",
    "list_open_targets",
]
