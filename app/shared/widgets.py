"""
# Widget tiện ích dùng chung cho Win App (PySide6)
- StyleLoader: load các file .qss
- StatusDot: chấm tròn báo trạng thái
- NavButton: nút điều hướng sidebar (có trạng thái active)
- Badge: nhãn nền nhạt (ok / error / warn / info)
- Card: QFrame có viền + border-radius (chung)
- MessageBubble: bong bóng chat (user / ai / system / error)
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QDate, QDateTime, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Hiển thị dd/MM/yyyy HH:mm; logic/API dùng ISO datetime (so sánh với OCR).
STOP_DATETIME_DISPLAY_FORMAT = "dd/MM/yyyy HH:mm"
STOP_DATETIME_STORAGE_FORMAT = "yyyy-MM-ddTHH:mm:ss"
# Giữ tên cũ cho tương thích đọc code.
STOP_DATE_DISPLAY_FORMAT = STOP_DATETIME_DISPLAY_FORMAT
STOP_DATE_STORAGE_FORMAT = STOP_DATETIME_STORAGE_FORMAT


# ============================================================================ #
# Style loader
# ============================================================================ #
def load_qss(*paths: str | Path) -> str:
    """Đọc và nối các file .qss theo thứ tự."""
    parts: list[str] = []
    for p in paths:
        path = Path(p)
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def apply_qss(widget: QWidget, *paths: str | Path) -> None:
    """Áp dụng .qss lên 1 widget (thường dùng cho QApplication hoặc page)."""
    qss = load_qss(*paths)
    if qss:
        widget.setStyleSheet(qss)


# ============================================================================ #
# StatusDot — chấm tròn xanh / đỏ
# ============================================================================ #
class StatusDot(QLabel):
    """Chấm tròn 10x10 màu xanh (ok) hoặc đỏ (lỗi)."""

    def __init__(self, ok: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.set_ok(ok)

    def set_ok(self, ok: bool) -> None:
        self.setObjectName("status_dot_ok" if ok else "status_dot_err")
        # Buộc Qt re-evaluate style với objectName mới
        self.style().unpolish(self)
        self.style().polish(self)


# ============================================================================ #
# Badge — nhãn pill nhỏ
# ============================================================================ #
class Badge(QLabel):
    """Pill label. variant ∈ {ok, error, warn, info, primary, muted}."""

    _OBJECT_NAMES = {
        "ok": "status_label_ok",
        "error": "status_label_error",
        # các variant khác có thể bổ sung trong style.qss của từng module
    }

    def __init__(self, text: str = "", variant: str = "ok", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        name = self._OBJECT_NAMES.get(variant, "status_label_ok")
        self.setObjectName(name)
        self.style().unpolish(self)
        self.style().polish(self)


# ============================================================================ #
# NavButton — mục điều hướng sidebar
# ============================================================================ #
class NavButton(QPushButton):
    """Nút điều hướng sidebar, hỗ trợ trạng thái 'checked' (active)."""

    def __init__(self, label: str, glyph: str = "•", parent: QWidget | None = None) -> None:
        super().__init__(f"  {glyph}    {label}", parent)
        self.setObjectName("nav_item")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(40)


# ============================================================================ #
# Card — QFrame có border + border-radius
# ============================================================================ #
class Card(QFrame):
    """Card với header (title + subtitle) và body."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        # Header
        if title:
            title_lbl = QLabel(title)
            title_lbl.setObjectName("card_title")
            outer.addWidget(title_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("card_subtitle")
            sub_lbl.setWordWrap(True)
            outer.addWidget(sub_lbl)

        # Body — caller addWidget vào layout này
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 4, 0, 0)
        self._body.setSpacing(10)
        outer.addLayout(self._body)

    def body(self) -> QVBoxLayout:
        return self._body

    def add(self, widget: QWidget) -> None:
        self._body.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._body.addLayout(layout)


# ============================================================================ #
# MessageBubble — bong bóng chat
# ============================================================================ #
class MessageBubble(QFrame):
    """1 message trong chat. role ∈ {user, ai, system, error, thinking}."""

    def __init__(
        self,
        role: str,
        sender: str,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._role = role
        self.setObjectName(f"bubble_{role}")
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self._sender = QLabel(sender)
        self._sender.setObjectName(f"bubble_sender_{role}")
        layout.addWidget(self._sender)

        self._content = QLabel(text)
        self._content.setObjectName(f"bubble_content_{role}")
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._content)

    # --- API ---
    def set_text(self, text: str) -> None:
        self._content.setText(text)

    def append_text(self, chunk: str) -> None:
        self._content.setText(self._content.text() + chunk)

    def text(self) -> str:
        return self._content.text()

    def set_role(self, role: str) -> None:
        """Đổi role (vd: thinking → ai khi nhận chunk đầu)."""
        self._role = role
        self.setObjectName(f"bubble_{role}")
        self._sender.setObjectName(f"bubble_sender_{role}")
        self._content.setObjectName(f"bubble_content_{role}")
        # Refresh style
        for w in (self, self._sender, self._content):
            w.style().unpolish(w)
            w.style().polish(w)


# ============================================================================ #
# Separator 1px
# ============================================================================ #
def make_vline(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("vline")
    f.setFrameShape(QFrame.NoFrame)
    return f


def make_hline(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("hline")
    f.setFrameShape(QFrame.NoFrame)
    return f


# ============================================================================ #
# Helper: hàng "label : value" gọn
# ============================================================================ #
class FormField(QWidget):
    """Label nhỏ ở trên + widget ở dưới (vd cho Entry)."""

    def __init__(self, label: str, field: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #6b7280; font-size: 9pt;")
        layout.addWidget(lbl)
        layout.addWidget(field)

        self._field = field

    def field(self) -> QWidget:
        return self._field


def _parse_default_stop_datetime(default_iso: str) -> QDateTime:
    """default_iso: YYYY-MM-DD hoặc YYYY-MM-DDTHH:MM:SS."""
    s = (default_iso or "").strip()
    if "T" in s:
        dt = QDateTime.fromString(s, "yyyy-MM-ddTHH:mm:ss")
        if dt.isValid():
            return dt
    d = QDate.fromString(s[:10], "yyyy-MM-dd")
    if d.isValid():
        return QDateTime(d, QTime(0, 0))
    return QDateTime.currentDateTime()


def make_stop_date_edit(
    default_iso: str = "2026-05-01T00:00:00",
    *,
    object_name: str = "shared_date_edit",
    width: int = 200,
) -> QDateTimeEdit:
    """Datetime picker (lịch popup) — hiển thị dd/MM/yyyy HH:mm, lưu ISO có giờ."""
    edit = QDateTimeEdit()
    edit.setObjectName(object_name)
    edit.setCalendarPopup(True)
    edit.setDisplayFormat(STOP_DATETIME_DISPLAY_FORMAT)
    edit.setDateTime(_parse_default_stop_datetime(default_iso))
    edit.setFixedWidth(width)
    edit.setMinimumHeight(36)
    edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return edit


def stop_date_iso(edit: QDateTimeEdit) -> str:
    """Chuyển QDateTimeEdit → chuỗi ISO datetime cho FSM / API."""
    if not edit.dateTime().isValid():
        return ""
    return edit.dateTime().toString(STOP_DATETIME_STORAGE_FORMAT)


def add_labeled_stop_date(
    parent_row: QHBoxLayout,
    label: str,
    *,
    default_iso: str,
    date_object_name: str,
    label_object_name: str,
    width: int = 200,
) -> QDateTimeEdit:
    """Thêm cột label + QDateTimeEdit vào hàng form."""
    col = QVBoxLayout()
    col.setSpacing(4)
    lbl = QLabel(label)
    lbl.setObjectName(label_object_name)
    col.addWidget(lbl)
    edit = make_stop_date_edit(
        default_iso,
        object_name=date_object_name,
        width=width,
    )
    col.addWidget(edit)
    wrap = QWidget()
    wrap.setLayout(col)
    parent_row.addWidget(wrap)
    return edit


__all__ = [
    "Badge",
    "Card",
    "FormField",
    "MessageBubble",
    "NavButton",
    "StatusDot",
    "apply_qss",
    "load_qss",
    "make_hline",
    "make_vline",
    "make_stop_date_edit",
    "stop_date_iso",
    "add_labeled_stop_date",
    "STOP_DATETIME_DISPLAY_FORMAT",
    "STOP_DATETIME_STORAGE_FORMAT",
    "STOP_DATE_DISPLAY_FORMAT",
    "STOP_DATE_STORAGE_FORMAT",
]
