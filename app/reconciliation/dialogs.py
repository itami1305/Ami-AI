"""
# Dialog preview — tab reconciliation
- ImageViewerDialog: xem ảnh screenshot (zoom Fit / 100% / 50%, lưu file).
- JsonViewerDialog: xem OCR response (JSON pretty-print, copy/lưu file).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.reconciliation.message_store import list_session_ids
from app.reconciliation.paths import ensure_export_dir

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ============================================================================ #
# IMAGE VIEWER
# ============================================================================ #
class ImageViewerDialog(QDialog):
    """Xem ảnh chụp với zoom Fit / 100% / 50% + lưu file."""

    ZOOM_LEVELS = ("fit", "100", "50")

    def __init__(self, image_bytes: bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("image_viewer")
        self.setWindowTitle("Ảnh chụp màn hình")
        self.resize(1000, 680)

        self._image_bytes = image_bytes
        self._pixmap_original = QPixmap()
        self._pixmap_original.loadFromData(image_bytes)
        self._zoom_mode = "fit"

        self._build_ui()
        self._apply_zoom()

    # ----- UI -----
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header: meta + nút zoom
        head = QHBoxLayout()
        head.setSpacing(8)
        w, h = self._pixmap_original.width(), self._pixmap_original.height()
        size_kb = len(self._image_bytes) / 1024.0
        meta = QLabel(f"Kích thước: {w}×{h} px  ·  {size_kb:,.1f} KB")
        meta.setObjectName("dialog_meta")
        head.addWidget(meta)
        head.addStretch()

        self._zoom_buttons: dict[str, QPushButton] = {}
        for key, label in (("fit", "Fit"), ("100", "100%"), ("50", "50%")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self._set_zoom(k))
            head.addWidget(btn)
            self._zoom_buttons[key] = btn
        self._zoom_buttons["fit"].setChecked(True)

        save_btn = QPushButton("Lưu ảnh…")
        save_btn.setProperty("class", "primary")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        head.addWidget(save_btn)

        root.addLayout(head)

        # Scroll area chứa ảnh
        self._scroll = QScrollArea()
        self._scroll.setObjectName("dialog_scroll")
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._scroll.setWidget(self._image_label)
        root.addWidget(self._scroll, 1)

        # Footer: nút đóng
        foot = QHBoxLayout()
        foot.addStretch()
        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    # ----- Zoom -----
    def _set_zoom(self, mode: str) -> None:
        if mode not in self.ZOOM_LEVELS:
            return
        self._zoom_mode = mode
        for k, btn in self._zoom_buttons.items():
            btn.setChecked(k == mode)
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        if self._pixmap_original.isNull():
            self._image_label.setText("(Không đọc được ảnh)")
            return

        if self._zoom_mode == "fit":
            # Vừa khít chiều rộng viewport, giữ tỉ lệ
            viewport_w = max(200, self._scroll.viewport().width() - 4)
            pm = self._pixmap_original.scaledToWidth(viewport_w, Qt.SmoothTransformation)
        elif self._zoom_mode == "50":
            pm = self._pixmap_original.scaled(
                self._pixmap_original.width() // 2,
                self._pixmap_original.height() // 2,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        else:  # 100
            pm = self._pixmap_original

        self._image_label.setPixmap(pm)
        self._image_label.adjustSize()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._zoom_mode == "fit":
            self._apply_zoom()

    # ----- Save -----
    def _on_save(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = str(ensure_export_dir() / f"screenshot_{stamp}.jpg")
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu ảnh", default_path, "JPEG (*.jpg *.jpeg);;PNG (*.png)"
        )
        if not path:
            return
        try:
            Path(path).write_bytes(self._image_bytes)
            QMessageBox.information(self, "Đã lưu", f"Đã lưu ảnh tại:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", f"Không lưu được:\n{exc}")


# ============================================================================ #
# JSON VIEWER
# ============================================================================ #
class JsonViewerDialog(QDialog):
    """Xem OCR response (dict) ở dạng JSON pretty-print + copy + lưu."""

    def __init__(self, data: Any, title: str = "OCR Response (JSON)", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("json_viewer")
        self.setWindowTitle(title)
        self.resize(820, 640)

        self._data = data
        try:
            self._formatted = json.dumps(data, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            self._formatted = str(data)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header
        head = QHBoxLayout()
        n_lines = self._formatted.count("\n") + 1
        size_kb = len(self._formatted.encode("utf-8")) / 1024.0
        meta = QLabel(f"{n_lines:,} dòng  ·  {size_kb:,.1f} KB")
        meta.setObjectName("dialog_meta")
        head.addWidget(meta)
        head.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._on_copy)
        head.addWidget(copy_btn)

        save_btn = QPushButton("Lưu .json…")
        save_btn.setProperty("class", "primary")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        head.addWidget(save_btn)

        root.addLayout(head)

        # Body: QTextEdit mono
        self._text = QTextEdit()
        self._text.setObjectName("json_text")
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setLineWrapMode(QTextEdit.NoWrap)
        self._text.setPlainText(self._formatted)
        root.addWidget(self._text, 1)

        # Footer
        foot = QHBoxLayout()
        foot.addStretch()
        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    def _on_copy(self) -> None:
        QGuiApplication.clipboard().setText(self._formatted)
        QMessageBox.information(self, "Đã copy", "Đã copy JSON vào clipboard.")

    def _on_save(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = str(ensure_export_dir() / f"ocr_response_{stamp}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu JSON", default_path, "JSON (*.json);;Text (*.txt)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self._formatted, encoding="utf-8")
            QMessageBox.information(self, "Đã lưu", f"Đã lưu JSON tại:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", f"Không lưu được:\n{exc}")


# ============================================================================ #
# MESSAGES LIST — tổng hợp tin nhắn OCR
# ============================================================================ #
class MessagesListDialog(QDialog):
    """Bảng tổng hợp tin nhắn: phiên hiện tại, phiên đã lưu, hoặc tất cả phiên."""

    COLUMNS = [
        ("stt", "#"),
        ("reconciliation_session_id", "Phiên đối soát"),
        ("session_id", "Lượt chat"),
        ("chat_name", "Hội thoại"),
        ("date", "Ngày"),
        ("time", "Giờ"),
        ("type", "Loại"),
        ("role", "Vai trò"),
        ("is_transaction", "GD"),
        ("text", "Nội dung"),
    ]

    @staticmethod
    def _short(text: str, maxlen: int = 10) -> str:
        if not text:
            return ""
        return (text[:maxlen] + "…") if len(text) > maxlen else text

    @classmethod
    def _reconciliation_run_cell(cls, msg: dict) -> str:
        r = msg.get("reconciliation_session_id")
        if r:
            return cls._short(str(r), 8)
        sid = str(msg.get("session_id", ""))
        if len(sid) >= 32 and sid.count("-") >= 4:
            return cls._short(sid, 8)
        return ""

    @classmethod
    def _turn_session_cell(cls, msg: dict) -> str:
        if msg.get("reconciliation_session_id"):
            return cls._short(str(msg.get("session_id", "")), 14)
        return cls._short(str(msg.get("id", "")), 14)

    def __init__(
        self,
        get_messages: Callable[[str, str | None], list[dict]],
        current_session_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("messages_list")
        self.setWindowTitle("Danh sách tin nhắn tổng hợp")
        self.resize(1100, 640)
        self._get_messages = get_messages
        self._current_session_id = current_session_id
        self._all_rows: list[dict] = []
        self._build_ui()
        self._populate_scope_combo()
        self._reload_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)

        scope_lbl = QLabel("Nguồn:")
        scope_lbl.setObjectName("dialog_meta")
        head.addWidget(scope_lbl)

        self._scope_combo = QComboBox()
        self._scope_combo.setMinimumWidth(280)
        self._scope_combo.setCursor(Qt.PointingHandCursor)
        self._scope_combo.currentIndexChanged.connect(self._reload_data)
        head.addWidget(self._scope_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Lọc theo nội dung, hội thoại, loại…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        head.addWidget(self._search, 1)

        self._only_tx = QCheckBox("Chỉ tin giao dịch")
        self._only_tx.stateChanged.connect(self._apply_filter)
        head.addWidget(self._only_tx)

        root.addLayout(head)

        self._meta = QLabel("")
        self._meta.setObjectName("dialog_meta")
        root.addWidget(self._meta)

        self._table = QTableWidget(0, len(self.COLUMNS))
        self._table.setObjectName("messages_table")
        self._table.setHorizontalHeaderLabels([c[1] for c in self.COLUMNS])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_row_double_click)
        root.addWidget(self._table, 1)

        self._detail = QTextEdit()
        self._detail.setObjectName("msg_detail")
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(100)
        self._detail.setPlaceholderText("Chọn một dòng để xem đầy đủ nội dung tin…")
        root.addWidget(self._detail)

        foot = QHBoxLayout()
        export_btn = QPushButton("Lưu .json…")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._on_export)
        foot.addWidget(export_btn)
        foot.addStretch()
        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)

    def _populate_scope_combo(self) -> None:
        self._scope_combo.clear()
        self._scope_combo.addItem("Phiên đang chạy (bộ nhớ)", ("current", None))
        if self._current_session_id:
            short = self._current_session_id[:8] + "…"
            self._scope_combo.addItem(f"Phiên hiện tại ({short})", ("session", self._current_session_id))
        for sid in list_session_ids():
            if sid == self._current_session_id:
                continue
            short = sid[:8] + "…"
            self._scope_combo.addItem(f"Phiên đã lưu ({short})", ("session", sid))
        self._scope_combo.addItem("Tất cả phiên", ("all_sessions", None))

    def _reload_data(self) -> None:
        data = self._scope_combo.currentData()
        if not data:
            self._all_rows = []
        else:
            scope, sid = data
            self._all_rows = self._get_messages(scope, sid)
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self._search.text().strip().lower()
        only_tx = self._only_tx.isChecked()
        rows: list[dict] = []
        for msg in self._all_rows:
            if only_tx and not msg.get("is_transaction"):
                continue
            if q:
                blob = " ".join(
                    str(msg.get(k, ""))
                    for k in (
                        "text",
                        "chat_name",
                        "type",
                        "role",
                        "date",
                        "time",
                        "session_id",
                        "reconciliation_session_id",
                        "id",
                    )
                ).lower()
                if q not in blob:
                    continue
            rows.append(msg)

        self._table.setRowCount(len(rows))
        for i, msg in enumerate(rows):
            values = [
                str(i + 1),
                self._reconciliation_run_cell(msg),
                self._turn_session_cell(msg),
                str(msg.get("chat_name", "")),
                str(msg.get("date", "")),
                str(msg.get("time", "")),
                str(msg.get("type", "text")),
                str(msg.get("role", "")),
                "Có" if msg.get("is_transaction") else "",
                str(msg.get("text", "")),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.UserRole, msg)
                self._table.setItem(i, col, item)

        tx_count = sum(1 for m in rows if m.get("is_transaction"))
        self._meta.setText(
            f"Hiển thị {len(rows):,} / {len(self._all_rows):,} tin"
            f"  ·  {tx_count:,} tin giao dịch"
        )
        if rows:
            self._table.selectRow(0)

    def _selected_message(self) -> dict | None:
        items = self._table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.UserRole)

    def _on_selection_changed(self) -> None:
        msg = self._selected_message()
        if not msg:
            self._detail.clear()
            return
        lines = [
            f"ID: {msg.get('id', '')}",
            f"Phiên đối soát: {msg.get('reconciliation_session_id') or self._reconciliation_run_cell(msg) or '—'}",
            f"Lượt chat (session): {msg.get('session_id', '')}",
            f"Hội thoại: {msg.get('chat_name', '')}",
            f"Loại: {msg.get('type', '')}  ·  Vai trò: {msg.get('role', '')}",
            f"Ngày/giờ: {msg.get('date', '')} {msg.get('time', '')}",
        ]
        if msg.get("type") == "chat_session":
            lines.append(f"Số bubble: {msg.get('member_count', 0)}")
            if msg.get("marker_before") or msg.get("marker_after"):
                lines.append(
                    f"Mốc: «{msg.get('marker_before', '')}» → «{msg.get('marker_after', '')}»"
                )
        lines.extend(
            [
                f"Giao dịch: {'Có' if msg.get('is_transaction') else 'Không'}",
                "",
                msg.get("text", ""),
            ]
        )
        self._detail.setPlainText("\n".join(lines))

    def _on_row_double_click(self) -> None:
        msg = self._selected_message()
        if not msg:
            return
        QMessageBox.information(
            self,
            "Chi tiết tin nhắn",
            msg.get("text", "") or "(Không có nội dung text)",
        )

    def _on_export(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = str(ensure_export_dir() / f"messages_export_{stamp}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu danh sách tin", default_path, "JSON (*.json)"
        )
        if not path:
            return
        visible: list[dict] = []
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item:
                msg = item.data(Qt.UserRole)
                if msg:
                    visible.append(msg)
        try:
            Path(path).write_text(
                json.dumps({"messages": visible}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            QMessageBox.information(self, "Đã lưu", f"Đã lưu {len(visible)} tin tại:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", f"Không lưu được:\n{exc}")


__all__ = ["ImageViewerDialog", "JsonViewerDialog", "MessagesListDialog"]
