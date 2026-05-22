"""
# UI Module Chat — trang chat (PySide6)
- Bong bóng chat dạng QFrame có border-radius.
- Stream response qua QThread + Signal/Slot.
- "Thinking..." nhấp nháy bằng QTimer cho tới khi có chunk đầu tiên.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.chat.logic import ChatLogic
from app.shared.widgets import MessageBubble, make_hline


LogCallback = Callable[[str, str], None]


# ============================================================================ #
# Stream worker (chạy trong QThread phụ)
# ============================================================================ #
class ChatStreamWorker(QObject):
    """Worker emit signal cho từng chunk + done + error."""

    chunkReceived = Signal(str)
    streamDone = Signal(str)
    streamError = Signal(str)
    finished = Signal()

    def __init__(self, logic: ChatLogic, message: str) -> None:
        super().__init__()
        self._logic = logic
        self._message = message

    @Slot()
    def run(self) -> None:
        try:
            self._logic.send_message_stream(
                self._message,
                on_chunk=lambda c: self.chunkReceived.emit(c),
                on_done=lambda full: self.streamDone.emit(full),
                on_error=lambda err: self.streamError.emit(err),
            )
        finally:
            self.finished.emit()


# ============================================================================ #
# Chat page
# ============================================================================ #
class ChatPage(QWidget):
    """Trang chat với AI local qua backend (streaming)."""

    THINKING_INTERVAL_MS = 400

    def __init__(self, log: LogCallback | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._logic = ChatLogic()
        self._log: LogCallback = log or (lambda _l, _m: None)

        # Stream state
        self._streaming = False
        self._first_chunk = True
        self._current_bubble: MessageBubble | None = None
        self._worker: ChatStreamWorker | None = None
        self._thread: QThread | None = None

        # Thinking animation
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(self.THINKING_INTERVAL_MS)
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._thinking_step = 0

        self._build_ui()
        self._add_bubble("system", "Hệ thống", "Chào bạn! Hãy nhập câu hỏi — AI sẽ trả lời bằng tiếng Việt.")

    # ============================================================== Build UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # --- Card chứa toàn bộ chat ---
        card = QFrame()
        card.setObjectName("chat_card")
        outer.addWidget(card, 1)

        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ----- Header card -----
        head = QHBoxLayout()
        head.setContentsMargins(18, 14, 18, 12)
        head.setSpacing(10)

        head_title = QLabel("Hội thoại")
        head_title.setObjectName("chat_head_title")
        head.addWidget(head_title)

        badge = QLabel("gemma4:e2b")
        badge.setObjectName("chat_badge_model")
        head.addWidget(badge)

        meta = QLabel("Ngôn ngữ: Tiếng Việt · Streaming")
        meta.setObjectName("chat_head_meta")
        head.addWidget(meta)
        head.addStretch()

        self._clear_btn = QPushButton("Xóa lịch sử")
        self._clear_btn.setProperty("class", "ghost")
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self._on_clear)
        head.addWidget(self._clear_btn)

        v.addLayout(head)
        v.addWidget(make_hline())

        # ----- Scroll area chứa các bubble -----
        self._scroll = QScrollArea()
        self._scroll.setObjectName("chat_scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content.setObjectName("chat_content")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(18, 14, 18, 14)
        self._content_layout.setSpacing(8)
        self._content_layout.addStretch(1)
        self._scroll.setWidget(self._content)

        v.addWidget(self._scroll, 1)

        v.addWidget(make_hline())

        # ----- Input bar -----
        input_row = QHBoxLayout()
        input_row.setContentsMargins(14, 12, 14, 14)
        input_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setObjectName("chat_input")
        self._input.setPlaceholderText("Nhập câu hỏi rồi nhấn Enter để gửi…")
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, 1)

        self._send_btn = QPushButton("Gửi tin nhắn")
        self._send_btn.setProperty("class", "primary")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)

        v.addLayout(input_row)

        # ----- Hint dưới card -----
        hint = QLabel("Mẹo: Enter để gửi. AI luôn trả lời tiếng Việt — câu trả lời sẽ stream từng phần.")
        hint.setObjectName("chat_hint")
        outer.addWidget(hint)

    # ============================================================== Helpers
    def _add_bubble(self, role: str, sender: str, text: str = "") -> MessageBubble:
        """Thêm 1 bubble vào danh sách, scroll xuống đáy."""
        bubble = MessageBubble(role, sender, text)
        # Align bubble theo role: user → phải, còn lại → trái
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        bubble.setMaximumWidth(720)
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

        if role == "user":
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()

        # Insert TRƯỚC stretch cuối cùng
        insert_at = self._content_layout.count() - 1
        self._content_layout.insertLayout(insert_at, row)

        QTimer.singleShot(0, self._scroll_to_bottom)
        return bubble

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_locked(self, locked: bool) -> None:
        self._send_btn.setDisabled(locked)
        self._clear_btn.setDisabled(locked)
        self._input.setDisabled(locked)
        self.setCursor(Qt.WaitCursor if locked else Qt.ArrowCursor)

    # ================================================================= Send
    def _on_send(self) -> None:
        if self._streaming:
            return
        msg = self._input.text().strip()
        if not msg:
            return

        self._input.clear()
        self._add_bubble("user", "Bạn", msg)
        self._log("info", f"Gửi tin nhắn ({len(msg)} ký tự).")

        # --- Bắt đầu stream ---
        self._streaming = True
        self._first_chunk = True

        # Tạo bubble AI ở trạng thái "thinking" — placeholder sẽ bị tick_thinking cập nhật
        self._current_bubble = self._add_bubble("thinking", "AI", "Thinking")
        self._thinking_step = 0
        self._thinking_timer.start()

        self._set_locked(True)

        # --- Spawn worker thread ---
        self._thread = QThread(self)
        self._worker = ChatStreamWorker(self._logic, msg)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.chunkReceived.connect(self._on_chunk)
        self._worker.streamDone.connect(self._on_done)
        self._worker.streamError.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_worker)

        self._thread.start()

    # ----------------------------------------------------------- Slots (main thread)
    @Slot(str)
    def _on_chunk(self, text: str) -> None:
        if self._current_bubble is None:
            return
        if self._first_chunk:
            # Đổi bubble từ "thinking" → "ai", xóa placeholder
            self._thinking_timer.stop()
            self._current_bubble.set_role("ai")
            self._current_bubble.set_text("")
            self._first_chunk = False
        self._current_bubble.append_text(text)
        QTimer.singleShot(0, self._scroll_to_bottom)

    @Slot(str)
    def _on_done(self, full: str) -> None:
        if self._current_bubble is not None and self._first_chunk:
            # Stream xong mà không có chunk → thay thinking bằng dấu trống
            self._thinking_timer.stop()
            self._current_bubble.set_role("system")
            self._current_bubble.set_text("(không có nội dung)")
        self._streaming = False
        self._set_locked(False)
        self._input.setFocus()
        self._log("ok", f"AI phản hồi xong ({len(full)} ký tự).")

    @Slot(str)
    def _on_error(self, err: str) -> None:
        self._thinking_timer.stop()
        if self._current_bubble is not None and self._first_chunk:
            # Đổi luôn bubble thành error
            self._current_bubble.set_role("error")
            self._current_bubble.set_text(err)
        else:
            self._add_bubble("error", "Lỗi", err)
        self._streaming = False
        self._set_locked(False)
        self._log("error", f"Chat stream lỗi: {err}")

    def _cleanup_worker(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    # ----------------------------------------------------------- Thinking animation
    @Slot()
    def _tick_thinking(self) -> None:
        if not self._streaming or not self._first_chunk or self._current_bubble is None:
            return
        self._thinking_step = (self._thinking_step + 1) % 4
        dots = "." * self._thinking_step
        self._current_bubble.set_text(f"Thinking{dots}")

    # ================================================================== Clear
    def _on_clear(self) -> None:
        if self._streaming:
            return
        self._logic.clear_history()

        # Xóa tất cả bubble (giữ lại stretch cuối cùng)
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                layout = item.layout()
                if layout is not None:
                    while layout.count():
                        sub = layout.takeAt(0)
                        if sub.widget() is not None:
                            sub.widget().deleteLater()

        self._add_bubble("system", "Hệ thống", "Đã xóa lịch sử hội thoại.")
        self._log("info", "Đã xóa lịch sử hội thoại chat.")
