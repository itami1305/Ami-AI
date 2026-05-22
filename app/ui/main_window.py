"""
Main window — Sidebar | Stack module | SystemLog
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.logic.api_client import health_check
from app.ui.chat.chat_widget import ChatWidget
from app.ui.reconciliation.reconciliation_widget import ReconciliationWidget
from app.ui.widgets import NavButton, StatusDot, apply_qss, load_qss, make_hline, make_vline

APP_ROOT = Path(__file__).resolve().parent.parent
QSS_FILES = [
    APP_ROOT / "styles" / "style.qss",
    APP_ROOT / "styles" / "chat.qss",
    APP_ROOT / "styles" / "reconciliation.qss",
]

SIDEBAR_WIDTH = 232
LOG_WIDTH = 340

LogLevel = str


class AmiWindow(QMainWindow):
    logMessage = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ami-AI")
        self.resize(1240, 780)
        self.setMinimumSize(1080, 640)

        self._page_titles: dict[str, tuple[str, str]] = {
            "chat": ("Chat AI", "Trò chuyện với mô hình Ollama gemma4:e2b — luôn trả lời tiếng Việt."),
            "reconciliation": (
                "Đối soát kế toán",
                "YOLO layout → loop-1/loop-2 — OCR vùng chat, plan worker nền.",
            ),
        }

        self._nav_buttons: dict[str, NavButton] = {}
        self._pages: dict[str, QWidget] = {}

        self._build_ui()
        self.logMessage.connect(self._append_log)
        self.log("info", "Ứng dụng Ami-AI khởi động xong.")
        self._select_page("chat")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(make_vline())
        root.addWidget(self._build_main(), 1)
        root.addWidget(make_vline())
        root.addWidget(self._build_log_panel())

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)

        v = QVBoxLayout(sidebar)
        v.setContentsMargins(14, 20, 14, 14)
        v.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        logo = QLabel("A")
        logo.setObjectName("sidebar_logo")
        logo.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(logo)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("Ami-AI")
        title.setObjectName("sidebar_title")
        subtitle = QLabel("Trợ lý nội bộ")
        subtitle.setObjectName("sidebar_subtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        v.addLayout(brand_row)

        nav_section = QLabel("ĐIỀU HƯỚNG")
        nav_section.setObjectName("sidebar_section")
        nav_section.setContentsMargins(8, 24, 0, 8)
        v.addWidget(nav_section)

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)

        chat_btn = NavButton("Chat AI", glyph="✱")
        chat_btn.clicked.connect(lambda: self._select_page("chat"))
        nav_group.addButton(chat_btn)
        v.addWidget(chat_btn)
        self._nav_buttons["chat"] = chat_btn

        rec_btn = NavButton("Đối soát kế toán", glyph="◎")
        rec_btn.clicked.connect(lambda: self._select_page("reconciliation"))
        nav_group.addButton(rec_btn)
        v.addWidget(rec_btn)
        self._nav_buttons["reconciliation"] = rec_btn

        v.addStretch(1)
        v.addWidget(make_hline())

        backend_section = QLabel("BACKEND")
        backend_section.setObjectName("sidebar_section")
        backend_section.setContentsMargins(8, 12, 0, 6)
        v.addWidget(backend_section)

        self._status_row = QHBoxLayout()
        self._status_row.setSpacing(8)
        v.addLayout(self._status_row)

        host = QLabel("127.0.0.1:8000")
        host.setObjectName("sidebar_subtitle")
        host.setContentsMargins(8, 6, 0, 0)
        v.addWidget(host)

        self._render_status()
        return sidebar

    def _render_status(self) -> None:
        while self._status_row.count():
            item = self._status_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        ok = health_check()
        dot = StatusDot(ok)
        self._status_row.addWidget(dot)

        lbl = QLabel("Đã kết nối" if ok else "Mất kết nối")
        lbl.setObjectName("status_label_ok" if ok else "status_label_error")
        self._status_row.addWidget(lbl)
        self._status_row.addStretch()

        refresh = QPushButton("↻")
        refresh.setObjectName("status_refresh")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self._on_refresh_status)
        self._status_row.addWidget(refresh)

    def _on_refresh_status(self) -> None:
        self._render_status()
        ok = health_check()
        self.log("ok" if ok else "error", "Backend kết nối" if ok else "Backend không phản hồi.")

    def _build_main(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        self._page_title = QLabel("")
        self._page_title.setObjectName("page_title")
        self._page_subtitle = QLabel("")
        self._page_subtitle.setObjectName("page_subtitle")
        self._page_subtitle.setWordWrap(True)
        v.addWidget(self._page_title)
        v.addWidget(self._page_subtitle)
        v.addWidget(make_hline())

        self._stack = QStackedWidget()
        self._pages["chat"] = ChatWidget(log=self.log)
        self._pages["reconciliation"] = ReconciliationWidget(log=self.log)
        for page in self._pages.values():
            self._stack.addWidget(page)
        v.addWidget(self._stack, 1)
        return wrap

    def _build_log_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("log_panel")
        panel.setFixedWidth(LOG_WIDTH)

        v = QVBoxLayout(panel)
        v.setContentsMargins(18, 20, 18, 14)
        v.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Nhật ký hoạt động")
        title.setObjectName("log_title")
        head.addWidget(title)
        head.addStretch()

        clear_btn = QPushButton("Xóa")
        clear_btn.setProperty("class", "ghost")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._on_clear_log)
        head.addWidget(clear_btn)
        v.addLayout(head)

        sub = QLabel("Sự kiện hệ thống, OCR và đối soát hiển thị theo thời gian thực.")
        sub.setObjectName("log_subtitle")
        sub.setWordWrap(True)
        v.addWidget(sub)
        v.addWidget(make_hline())

        self._log_view = QTextEdit()
        self._log_view.setObjectName("log_view")
        self._log_view.setReadOnly(True)
        v.addWidget(self._log_view, 1)
        return panel

    def _select_page(self, key: str) -> None:
        if key not in self._pages:
            return
        self._stack.setCurrentWidget(self._pages[key])
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)
        title, subtitle = self._page_titles[key]
        self._page_title.setText(title)
        self._page_subtitle.setText(subtitle)

    def log(self, level: LogLevel, message: str) -> None:
        self.logMessage.emit(level, message)

    def _append_log(self, level: str, message: str) -> None:
        color = {
            "info": "#111827",
            "ok": "#16a34a",
            "warn": "#d97706",
            "error": "#dc2626",
        }.get(level, "#111827")

        ts = time.strftime("%H:%M:%S")
        html = (
            f'<div style="margin:0; padding:0;">'
            f'<span style="color:#9ca3af;">[{ts}]</span> '
            f'<span style="color:{color};">{self._escape(message)}</span>'
            f"</div>"
        )
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        cursor.insertBlock()
        self._log_view.setTextCursor(cursor)
        self._log_view.ensureCursorVisible()

    @staticmethod
    def _escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _on_clear_log(self) -> None:
        self._log_view.clear()


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
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


def run_app() -> None:
    _enable_windows_dpi_awareness()
    app = QApplication(sys.argv)
    app.setApplicationName("Ami-AI")
    apply_qss(app, *QSS_FILES)
    window = AmiWindow()
    window.show()
    sys.exit(app.exec())
