"""
Pydantic models — module Reconciliation (markdown.md §7–10).
Models Pydantic cho API /reconciliation/*.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedBBox(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class CaptureOffset(BaseModel):
    x: int = 0
    y: int = 0


class ScreenInfo(BaseModel):
    width: int = 0
    height: int = 0
    capture_offset: CaptureOffset = Field(default_factory=CaptureOffset)


class PerceptionMessage(BaseModel):
    id: str
    role: str = "other"
    type: str = "text"
    text: str = ""
    time: str = ""
    date: str | None = None
    bbox: NormalizedBBox = Field(default_factory=NormalizedBBox)
    image_path: str | None = None


class PerceptionSidebarItem(BaseModel):
    id: str = ""
    name: str = ""
    selected: bool = False
    bbox: NormalizedBBox = Field(default_factory=NormalizedBBox)


class ProcessedState(BaseModel):
    message_ids: list[str] = Field(default_factory=list)
    chat_ids: list[str] = Field(default_factory=list)


class PerceptionResponse(BaseModel):
    """Perception snapshot — §7.1 (bbox normalized 0–1)."""

    session_id: str
    app_type: str = "zalo_pc"
    chat_detected: bool = False
    screen: ScreenInfo = Field(default_factory=ScreenInfo)
    chat_region: NormalizedBBox = Field(default_factory=NormalizedBBox)
    messages: list[PerceptionMessage] = Field(default_factory=list)
    sidebar: list[PerceptionSidebarItem] = Field(default_factory=list)
    state: str = "reading_history"
    processed: ProcessedState = Field(default_factory=ProcessedState)
    stop_date: str = ""


# --- OCR pixel (internal / tương thích) ---
class ChatRegion(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class MessageItem(BaseModel):
    id: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    type: str = "text"
    date: str | None = None
    text: str = ""
    # Một bubble / một lượt: self = phía phải (tin mình), other = trái / đối phương.
    role: str = "other"


class SidebarItem(BaseModel):
    name: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class OcrPixelResponse(BaseModel):
    session_id: str
    image_width: int = 0
    image_height: int = 0
    chat_region: ChatRegion
    messages: list[MessageItem]
    sidebar: list[SidebarItem] = Field(default_factory=list)


# --- Giao dịch ---
class TransactionResult(BaseModel):
    is_transaction: bool = False
    date: str = ""
    time: str = ""
    sender: str = ""
    amount: str = ""
    bank: str = ""
    transaction_code: str = ""
    account_number: str = ""
    beneficiary: str = ""
    content: str = ""
    direction: str = "unknown"


class DetectTransactionRequest(BaseModel):
    text: str
    sender: str = ""
    time: str = ""


class ParseSummaryRequest(BaseModel):
    text: str
    sender: str = ""
    time: str = ""
    message_id: str = ""


class TransactionRecord(BaseModel):
    """Schema §10.4 — một dòng giao dịch."""

    id: str = ""
    session_id: str = ""
    app_type: str = "zalo_pc"
    chat_id: str = ""
    chat_name: str = ""
    message_id: str = ""
    parent_message_id: str = ""
    line_index: int | None = None
    source_type: str = "single_text"
    transaction_date: str = ""
    transaction_time: str = ""
    sender: str = ""
    direction: str = "unknown"
    amount: str = ""
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
    linked_record_ids: list[str] = Field(default_factory=list)
    is_duplicate: bool = False
    status: str = "extracted"
    created_at: str = ""


class ParseSummaryResponse(BaseModel):
    is_summary: bool = False
    lines: list[str] = Field(default_factory=list)
    records: list[TransactionRecord] = Field(default_factory=list)


# --- Tách giao dịch bằng AI local (đoạn chat / chat_session) ---
class ChatSegmentInfo(BaseModel):
    """Một lượt chat (type=chat_session) — text OCR có thể sai chính tả."""

    id: str = ""
    text: str
    date: str = ""
    time: str = ""
    sender: str = ""
    role: str = "other"
    chat_id: str = ""
    chat_name: str = ""
    marker_before: str = ""
    marker_after: str = ""
    member_count: int = 0
    is_transaction: bool = False


class LlmTransactionItem(BaseModel):
    """Một giao dịch trong JSON trả về từ Ollama."""

    transaction_date: str = ""
    transaction_time: str = ""
    sender: str = ""
    direction: str = "unknown"
    amount: str = ""
    currency: str = "VND"
    bank: str = ""
    transaction_code: str = ""
    account_number: str = ""
    beneficiary: str = ""
    content: str = ""
    raw_text: str = ""
    confidence: float = 0.0


class LlmSplitResult(BaseModel):
    transactions: list[LlmTransactionItem] = Field(default_factory=list)
    notes: str = ""


class SplitTransactionsRequest(BaseModel):
    session_id: str
    segment: ChatSegmentInfo
    app_type: str = "zalo_pc"
    save_csv: bool = True
    csv_path: str | None = None
    append_csv: bool = True
    use_llm: bool = True


class SplitTransactionsResponse(BaseModel):
    success: bool = True
    model: str = ""
    transaction_count: int = 0
    transactions: list[TransactionRecord] = Field(default_factory=list)
    csv_path: str | None = None
    raw_llm_json: dict | None = None
    error: str | None = None


class SegmentQueueEnqueueRequest(BaseModel):
    session_id: str
    segment: ChatSegmentInfo
    app_type: str = "zalo_pc"


class SegmentQueueActivateRequest(BaseModel):
    session_id: str
    app_type: str = "zalo_pc"
    csv_path: str | None = None
    save_csv: bool = True


class SegmentQueueStatusResponse(BaseModel):
    session_id: str
    active: bool = False
    pending: int = 0
    processing_id: str | None = None
    total_enqueued: int = 0
    total_processed: int = 0
    finished_pending: int = 0
    last_error: str | None = None


class SegmentQueueDrainResponse(BaseModel):
    session_id: str
    count: int = 0
    results: list[SplitTransactionsResponse] = Field(default_factory=list)


# --- Planner §8 ---
class PlanRequest(BaseModel):
    session_id: str
    snapshot: dict
    goal: str = "read_until_stop_date"
    stop_date: str = ""
    no_new_count: int = 0
    # Chỉ cuộn trong chat hiện tại — không đề xuất mở chat khác từ sidebar.
    segment_only: bool = False


class AgentActionResponse(BaseModel):
    action: str
    params: dict = Field(default_factory=dict)
    confidence: float = 1.0
    reason: str = ""


# --- Analyze §10.8 ---
class AnalyzeRequest(BaseModel):
    session_id: str
    transactions: list[TransactionRecord] = Field(default_factory=list)


class AnalyzeWarning(BaseModel):
    code: str
    message: str
    record_ids: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    merged_transactions: list[TransactionRecord] = Field(default_factory=list)
    warnings: list[AnalyzeWarning] = Field(default_factory=list)
    summary_vi: str = ""
