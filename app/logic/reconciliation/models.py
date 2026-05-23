"""
Dataclass cho module Reconciliation — markdown.md §8–10.

- FsmState: trạng thái máy trạng thái hữu hạn (logging / hiển thị).
- AgentAction: một bước hành động do planner trả về (scroll, click, open_chat, stop_*).
- TransactionRecord: một dòng đối soát đã trích xuất (xuất CSV/JSON + phân tích cuối phiên).
- ReconciliationState: toàn bộ bộ nhớ phiên (đã xử lý tin/chat, dedupe, đường dẫn export).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from app.logic.reconciliation.window_checker import CaptureTargetId
from app.logic.reconciliation.paths import default_csv_path, session_export_dir

CaptureAppType = Literal["zalo_pc", "zalo_web", "messenger_web", "messenger_desktop"]
SourceType = Literal[
    "summary_text",
    "transfer_image",
    "transfer_receipt_ocr",
    "bank_sms_lines",
    "single_text",
    "llm_chat_segment",
    "rule_chat_segment",
]


class FsmState(str, Enum):
    """Các phase chính của vòng đối soát (inner/outer)."""

    IDLE = "idle"
    CAPTURE = "capture"
    PERCEIVE = "perceive"
    PLAN = "plan"
    ACT = "act"
    NEXT_CHAT = "next_chat"
    DONE = "done"


@dataclass
class AgentAction:
    """Hành động tiếp theo: tên action + tham số (hướng scroll, index sidebar, bbox_ref...)."""

    action: str
    params: dict = field(default_factory=dict)
    confidence: float = 1.0
    reason: str = ""


@dataclass
class TransactionRecord:
    """Một giao dịch đã parse: nguồn summary / ảnh CK / tin đơn; có dedupe_key để gộp trùng."""

    id: str
    session_id: str
    app_type: CaptureAppType
    chat_id: str
    chat_name: str
    message_id: str
    source_type: SourceType
    amount: str
    parent_message_id: str = ""
    line_index: int | None = None
    transaction_date: str = ""
    transaction_time: str = ""
    sender: str = ""
    direction: str = "unknown"
    currency: str = "VND"
    bank: str = ""
    transaction_code: str = ""
    account_number: str = ""
    beneficiary: str = ""
    content: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    screenshot_path: str = ""
    transfer_image_path: str | None = None
    summary_excerpt: str | None = None
    dedupe_key: str = ""
    linked_record_ids: list[str] = field(default_factory=list)
    is_duplicate: bool = False
    status: str = "extracted"
    created_at: str = ""

    def to_csv_row(self) -> dict[str, str]:
        """Bản rút gọn các cột cho CSV (không đủ field JSON đầy đủ)."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "app_type": self.app_type,
            "chat_name": self.chat_name,
            "message_id": self.message_id,
            "source_type": self.source_type,
            "transaction_date": self.transaction_date,
            "transaction_time": self.transaction_time,
            "sender": self.sender,
            "direction": self.direction,
            "amount": self.amount,
            "currency": self.currency,
            "bank": self.bank,
            "transaction_code": self.transaction_code,
            "account_number": self.account_number,
            "beneficiary": self.beneficiary,
            "content": self.content,
            "transfer_image_path": self.transfer_image_path or "",
            "summary_excerpt": self.summary_excerpt or "",
            "dedupe_key": self.dedupe_key,
            "status": self.status,
        }

    def to_json_dict(self) -> dict:
        """Payload gửi POST /reconciliation/analyze và ghi transactions.json."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "app_type": self.app_type,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "message_id": self.message_id,
            "parent_message_id": self.parent_message_id or self.message_id,
            "line_index": self.line_index,
            "source_type": self.source_type,
            "transaction_date": self.transaction_date,
            "transaction_time": self.transaction_time,
            "sender": self.sender,
            "direction": self.direction,
            "amount": self.amount,
            "currency": self.currency,
            "bank": self.bank,
            "transaction_code": self.transaction_code,
            "account_number": self.account_number,
            "beneficiary": self.beneficiary,
            "content": self.content,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "screenshot_path": self.screenshot_path,
            "transfer_image_path": self.transfer_image_path,
            "summary_excerpt": self.summary_excerpt,
            "dedupe_key": self.dedupe_key,
            "linked_record_ids": self.linked_record_ids,
            "is_duplicate": self.is_duplicate,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class ReconciliationState:
    """
    Trạng thái chạy một phiên: UUID session, chat hiện tại, offset/size ảnh capture,
    sets để không xử lý trùng tin/chat, đếm vòng lặp 'không có tin mới', đường dẫn export.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stop_date: str = ""
    processed_messages: set[str] = field(default_factory=set)
    processed_chat_ids: set[str] = field(default_factory=set)
    dedupe_keys: set[str] = field(default_factory=set)
    transaction_codes: set[str] = field(default_factory=set)
    records_by_id: dict[str, TransactionRecord] = field(default_factory=dict)
    messages_catalog: dict[str, dict] = field(default_factory=dict)
    # Bubble OCR thô (theo id); dùng rebuild session giữa các mốc ngày/giờ.
    bubble_catalog: dict[str, dict] = field(default_factory=dict)
    csv_path: Path | None = None
    json_path: Path | None = None
    session_dir: Path | None = None
    transaction_count: int = 0
    current_chat_id: str = ""
    current_chat_name: str = ""
    sidebar_x: int = 150
    next_chat_y: int = 200
    capture_target: CaptureTargetId = "zalo"
    capture_offset_x: int = 0
    capture_offset_y: int = 0
    capture_width: int = 0
    capture_height: int = 0
    running: bool = False
    # True khi user bấm Dừng — vẫn chờ AI xử lý hàng đợi đoạn chat.
    stop_requested: bool = False
    no_new_count: int = 0
    fsm_state: FsmState = FsmState.IDLE
    last_screenshot_path: str = ""
    # True: chỉ INNER một chat, không mở hội thoại khác từ sidebar (quét một đoạn).
    segment_mode: bool = False
    # Preset layout OCR — cập nhật sau mỗi lần chụp (infer từ tiêu đề cửa sổ).
    layout_app_type: CaptureAppType = "zalo_pc"
    # Layout YOLO từ POST /reconciliation/yolo (cache phiên).
    yolo_layout: dict | None = None

    @property
    def app_type(self) -> CaptureAppType:
        """app_type gửi backend (perceive / split) — theo layout đã nhận diện."""
        return self.layout_app_type

    def ensure_session_paths(self) -> None:
        """Khởi tạo session_dir, transactions.json path, CSV path mặc định nếu None."""
        if self.session_dir is None:
            self.session_dir = session_export_dir(self.session_id)
        if self.json_path is None:
            self.json_path = self.session_dir / "transactions.json"
        if self.csv_path is None:
            self.csv_path = default_csv_path(self.session_id)
