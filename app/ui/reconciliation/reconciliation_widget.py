"""
UI Reconciliation — date picker, chế độ quét, nút Chạy/Dừng.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.logic.api_client import health_check
from app.logic.reconciliation.orchestrator import ReconciliationOrchestrator
from app.logic.reconciliation.window_checker import CAPTURE_TARGETS
from app.ui.reconciliation.dialogs import ImageViewerDialog, JsonViewerDialog, MessagesListDialog
from app.ui.widgets import Card, StatusDot, add_labeled_stop_date, stop_date_iso

LogCallback = Callable[[str, str], None]


class ReconciliationWorker(QObject):
    logEmitted = Signal(str)
    perceiveResult = Signal(dict)
    screenshotCaptured = Signal(bytes)
    finished = Signal()

    def __init__(self, logic: ReconciliationOrchestrator, kind: str, **kwargs) -> None:
        super().__init__()
        self._logic = logic
        self._kind = kind
        self._kwargs = kwargs
        self._logic._on_log = self.logEmitted.emit  # type: ignore[attr-defined]

    @Slot()
    def run(self) -> None:
        try:
            if self._kind == "full":
                self._logic.run_full(
                    stop_date=self._kwargs.get("stop_date", ""),
                    max_chats=self._kwargs.get("max_chats", 3),
                )
            elif self._kind == "segment":
                self._logic.run_chat_segment(
                    stop_date=self._kwargs.get("stop_date", ""),
                )
            elif self._kind == "perceive_once":
                self._run_perceive_once()
        except Exception as exc:  # noqa: BLE001
            self.logEmitted.emit(f"Lỗi worker: {exc}")
        finally:
            self.finished.emit()

    def _run_perceive_once(self) -> None:
        img = self._logic.capture_screenshot()
        self.screenshotCaptured.emit(img)
        result = self._logic.upload_perceive(img)
        n = len(result.get("messages", []))
        self.logEmitted.emit(
            f"YOLO/Perceive OK — {n} message(s), session={result.get('session_id')}"
        )
        self.perceiveResult.emit(result)


class ReconciliationWidget(QWidget):
    """Tab Đối soát — loop-1/loop-2 + export."""

    def __init__(self, log: LogCallback | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log = log or (lambda _l, _m: None)
        self._logic = ReconciliationOrchestrator(on_log=self._proxy_log)
        self._worker: ReconciliationWorker | None = None
        self._thread: QThread | None = None
        self._autofilled = False
        self._last_screenshot: bytes | None = None
        self._last_perceive: dict | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._build_config_card())
        root.addWidget(self._build_action_card())
        root.addWidget(self._build_hints_card(), 1)

    def _build_config_card(self) -> Card:
        card = Card("Cấu hình Reconciliation")
        row = QHBoxLayout()
        self._stop_date_edit = add_labeled_stop_date(
            row,
            "Ngày giờ dừng (stop_date)",
            default_iso="2026-05-01T00:00:00",
            date_object_name="rec_date_edit",
            label_object_name="rec_field_label",
            width=200,
        )
        row.addStretch()
        card.add_layout(row)

        app_row = QHBoxLayout()
        app_lbl = QLabel("Ứng dụng chụp")
        app_lbl.setObjectName("rec_field_label")
        app_col = QVBoxLayout()
        app_col.addWidget(app_lbl)
        self._capture_combo = QComboBox()
        self._capture_combo.setObjectName("rec_combo")
        for tid, cfg in CAPTURE_TARGETS.items():
            self._capture_combo.addItem(cfg["label"], tid)
        self._capture_combo.setFixedWidth(200)
        self._capture_combo.setMinimumHeight(36)
        app_col.addWidget(self._capture_combo)
        wrap = QWidget()
        wrap.setLayout(app_col)
        app_row.addWidget(wrap)
        app_row.addStretch()
        card.add_layout(app_row)
        return card

    def _build_action_card(self) -> Card:
        card = Card("Trạng thái & hành động", "Luồng: YOLO → loop-1 → loop-2 (OCR vùng chat)")

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Trạng thái:"))
        self._status_dot = StatusDot(False)
        status_row.addWidget(self._status_dot)
        self._status_pill = QLabel("Sẵn sàng")
        self._status_pill.setObjectName("rec_status_idle")
        status_row.addWidget(self._status_pill)
        status_row.addStretch()
        card.add_layout(status_row)

        btn_row = QHBoxLayout()
        for text, slot in [
            ("Chụp + YOLO", self._on_perceive_once),
            ("Quét đoạn chat", self._on_segment),
            ("Bắt đầu đối soát", self._on_start),
            ("Dừng", self._on_stop),
        ]:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            if text == "Bắt đầu đối soát":
                btn.setProperty("class", "primary")
            if text == "Dừng":
                btn.setProperty("class", "danger")
            btn_row.addWidget(btn)
        btn_row.addStretch()
        card.add_layout(btn_row)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel("Kết quả:"))
        self._btn_image = QPushButton("Xem ảnh")
        self._btn_image.setEnabled(False)
        self._btn_image.clicked.connect(self._on_view_image)
        view_row.addWidget(self._btn_image)
        self._btn_json = QPushButton("Xem JSON")
        self._btn_json.setEnabled(False)
        self._btn_json.clicked.connect(self._on_view_json)
        view_row.addWidget(self._btn_json)
        btn_msg = QPushButton("Danh sách tin")
        btn_msg.clicked.connect(self._on_messages)
        view_row.addWidget(btn_msg)
        view_row.addStretch()
        card.add_layout(view_row)
        return card

    def _build_hints_card(self) -> Card:
        card = Card("Hướng dẫn", "Đối soát chat — structure.md")
        for h in [
            "Bước 0: chụp full → POST /yolo → cache layout (YOLO nhận diện khung chat).",
            "loop-2: chỉ chụp vùng chat → POST /ocr (cropped) — phản hồi nhanh hơn.",
            "Plan worker nền tách giao dịch qua segment-queue (Ollama).",
            "Export: transactions.json + CSV trong exports/reconciliation/sessions/.",
        ]:
            row = QHBoxLayout()
            b = QLabel("●")
            b.setObjectName("rec_bullet")
            b.setFixedWidth(14)
            row.addWidget(b)
            t = QLabel(h)
            t.setObjectName("rec_hint")
            t.setWordWrap(True)
            row.addWidget(t, 1)
            card.add_layout(row)
        return card

    def _set_status(self, running: bool, label: str) -> None:
        self._status_dot.set_ok(running)
        self._status_pill.setText(label)
        self._status_pill.setObjectName("rec_status_running" if running else "rec_status_idle")
        self._status_pill.style().unpolish(self._status_pill)
        self._status_pill.style().polish(self._status_pill)

    def _proxy_log(self, message: str) -> None:
        low = message.lower()
        if "lỗi" in low or "error" in low:
            level = "error"
        elif "đã lưu" in low or "yolo ok" in low or "perceive ok" in low:
            level = "ok"
        elif "hoàn tất" in low or "phân tích" in low:
            level = "ok"
        elif "dừng" in low:
            level = "warn"
        else:
            level = "info"
        self._log(level, message)

    def _sync_capture(self) -> None:
        tid = self._capture_combo.currentData()
        if tid in CAPTURE_TARGETS:
            self._logic.state.capture_target = tid  # type: ignore[assignment]

    def _on_perceive_once(self) -> None:
        if self._thread:
            self._log("warn", "Đang chạy tác vụ khác.")
            return
        self._sync_capture()
        self._start_worker("perceive_once")

    def _on_start(self) -> None:
        if self._thread:
            self._log("warn", "Đang chạy — bấm Dừng trước.")
            return
        self._sync_capture()
        self._set_status(True, "Đang chạy")
        self._start_worker("full", stop_date=stop_date_iso(self._stop_date_edit), max_chats=3)

    def _on_segment(self) -> None:
        if self._thread:
            self._log("warn", "Đang chạy — bấm Dừng trước.")
            return
        self._sync_capture()
        self._set_status(True, "Quét đoạn")
        self._start_worker("segment", stop_date=stop_date_iso(self._stop_date_edit))

    def _on_stop(self) -> None:
        self._logic.stop()
        self._set_status(True, "Chờ AI phân tích đoạn chat...")

    def _start_worker(self, kind: str, **kwargs) -> None:
        self._thread = QThread(self)
        self._worker = ReconciliationWorker(self._logic, kind, **kwargs)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.logEmitted.connect(self._proxy_log)
        self._worker.perceiveResult.connect(self._on_perceive)
        self._worker.screenshotCaptured.connect(self._on_screenshot)
        self._worker.finished.connect(self._on_worker_done)
        self._thread.start()

    @Slot()
    def _on_worker_done(self) -> None:
        self._set_status(False, "Sẵn sàng")
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    @Slot(bytes)
    def _on_screenshot(self, data: bytes) -> None:
        self._last_screenshot = data
        self._btn_image.setEnabled(True)

    @Slot(dict)
    def _on_perceive(self, result: dict) -> None:
        self._last_perceive = result
        self._btn_json.setEnabled(True)
        try:
            n = self._logic.ingest_perceive_raw(result)
            if n:
                self._log("info", f"Gộp {n} tin vào catalog.")
        except Exception as exc:  # noqa: BLE001
            self._log("warn", str(exc))
        if self._autofilled:
            return
        ox = self._logic.state.capture_offset_x
        oy = self._logic.state.capture_offset_y
        sx, cy = self._coords_from_result(result, ox, oy)
        if sx is not None:
            self._logic.state.sidebar_x = sx
        if cy is not None:
            self._logic.state.next_chat_y = cy
        if sx is not None or cy is not None:
            self._autofilled = True
            self._log("ok", f"Tọa độ tự động: Sidebar X={sx}, Chat Y={cy}")

    def _on_view_image(self) -> None:
        if self._last_screenshot:
            ImageViewerDialog(self._last_screenshot, self).exec()

    def _on_view_json(self) -> None:
        if self._last_perceive:
            JsonViewerDialog(self._last_perceive, parent=self).exec()

    def _on_messages(self) -> None:
        MessagesListDialog(
            get_messages=self._logic.get_messages,
            current_session_id=self._logic.state.session_id,
            parent=self,
        ).exec()

    @staticmethod
    def _coords_from_result(result: dict, ox: int, oy: int) -> tuple[int | None, int | None]:
        sidebar = result.get("sidebar") or []
        messages = result.get("messages") or []
        screen = result.get("screen") or {}
        sw = int(screen.get("width") or 0)
        sh = int(screen.get("height") or 0)

        sidebar_x: int | None = None
        if sidebar:
            item = sidebar[0]
            bbox = item.get("bbox") or item
            if sw and sh and bbox.get("w", 1) <= 1:
                sidebar_x = int((bbox.get("x", 0) + bbox.get("w", 0) / 2) * sw) + ox
            else:
                sidebar_x = int(item.get("x", 0) + item.get("width", 0) // 2) + ox

        chat_y: int | None = None
        if messages:
            item = messages[0]
            bbox = item.get("bbox") or item
            if sw and sh and bbox.get("h", 1) <= 1:
                chat_y = int(bbox.get("y", 0) * sh) + oy
            else:
                chat_y = int(item.get("y", 0)) + oy

        return sidebar_x, chat_y


ReconciliationPage = ReconciliationWidget

__all__ = ["ReconciliationPage", "ReconciliationWidget"]
