"""
API Reconciliation — /yolo, /ocr, /plan + endpoints tương thích.
"""

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.reconciliation.analyze_service import analyze_session
from backend.reconciliation.cache import get_session, reset_session
from backend.reconciliation.models import (
    AgentActionResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    DetectTransactionRequest,
    OcrPixelResponse,
    ParseSummaryRequest,
    ParseSummaryResponse,
    PerceptionResponse,
    PlanRequest,
    SegmentQueueActivateRequest,
    SegmentQueueDrainResponse,
    SegmentQueueEnqueueRequest,
    SegmentQueueStatusResponse,
    SplitTransactionsRequest,
    SplitTransactionsResponse,
    TransactionResult,
)
from backend.reconciliation.perceive_service import process_perception
from backend.reconciliation.planner_service import plan
from backend.reconciliation.segment_queue import (
    activate_queue,
    clear_queue,
    deactivate_queue,
    drain_finished,
    enqueue_segment,
    get_queue_status,
)
from backend.reconciliation.transaction_detector import detect_transaction, parse_summary_lines
from backend.reconciliation.transaction_split_service import split_chat_transactions
from backend.services.ocr_service import process_ocr
from backend.services.yolo_service import detect_layout

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


async def _read_upload(
    file: UploadFile,
    session_id: str | None,
) -> tuple[str, bytes]:
    sid = session_id or str(uuid.uuid4())
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="File ảnh rỗng.")
    return sid, image_bytes


@router.post("/yolo")
async def yolo_layout(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    app_type: str | None = Form(default=None),
) -> dict:
    """YOLO/CV phân tích bố cục màn hình — cache layout, trả chat_region + sidebar."""
    sid, image_bytes = await _read_upload(file, session_id)
    try:
        return detect_layout(image_bytes, sid, app_type, force_refresh=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ocr", response_model=OcrPixelResponse)
async def ocr_screenshot(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    app_type: str | None = Form(default=None),
    cropped: bool = Form(default=False),
) -> OcrPixelResponse:
    """OCR — cropped=True khi ảnh đã là vùng chat (loop-2)."""
    sid, image_bytes = await _read_upload(file, session_id)
    try:
        return process_ocr(image_bytes, sid, app_type=app_type, cropped=cropped)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/perceive", response_model=PerceptionResponse)
async def perceive_screenshot(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    app_type: str | None = Form(default=None),
    capture_offset_x: int = Form(default=0),
    capture_offset_y: int = Form(default=0),
) -> PerceptionResponse:
    """Tương thích cũ: YOLO layout (cache) + OCR full → Perception JSON."""
    sid, image_bytes = await _read_upload(file, session_id)
    return process_perception(
        image_bytes,
        sid,
        app_type=app_type,
        capture_offset_x=capture_offset_x,
        capture_offset_y=capture_offset_y,
    )


@router.post("/plan", response_model=AgentActionResponse)
async def plan_action(body: PlanRequest) -> AgentActionResponse:
    session = get_session(body.session_id)
    return plan(body, session.processed_chat_ids)


@router.post("/detect-transaction", response_model=TransactionResult)
async def detect_transaction_api(body: DetectTransactionRequest) -> TransactionResult:
    return detect_transaction(body)


@router.post("/parse-summary", response_model=ParseSummaryResponse)
async def parse_summary_api(body: ParseSummaryRequest) -> ParseSummaryResponse:
    return parse_summary_lines(body)


@router.post("/split-transactions", response_model=SplitTransactionsResponse)
async def split_transactions_api(body: SplitTransactionsRequest) -> SplitTransactionsResponse:
    return await split_chat_transactions(body)


@router.post("/segment-queue/activate", response_model=SegmentQueueStatusResponse)
async def segment_queue_activate(body: SegmentQueueActivateRequest) -> SegmentQueueStatusResponse:
    data = await activate_queue(body)
    return SegmentQueueStatusResponse(**data)


@router.post("/segment-queue/deactivate/{session_id}", response_model=SegmentQueueStatusResponse)
async def segment_queue_deactivate(session_id: str) -> SegmentQueueStatusResponse:
    data = await deactivate_queue(session_id)
    return SegmentQueueStatusResponse(**data)


@router.post("/segment-queue/enqueue")
async def segment_queue_enqueue(body: SegmentQueueEnqueueRequest) -> dict:
    return await enqueue_segment(body.session_id, body.segment, app_type=body.app_type)


@router.get("/segment-queue/status/{session_id}", response_model=SegmentQueueStatusResponse)
async def segment_queue_status(session_id: str) -> SegmentQueueStatusResponse:
    data = await get_queue_status(session_id)
    return SegmentQueueStatusResponse(**data)


@router.post("/segment-queue/drain/{session_id}", response_model=SegmentQueueDrainResponse)
async def segment_queue_drain(session_id: str) -> SegmentQueueDrainResponse:
    data = await drain_finished(session_id)
    return SegmentQueueDrainResponse(
        session_id=data["session_id"],
        count=data["count"],
        results=[SplitTransactionsResponse.model_validate(r) for r in data["results"]],
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_api(body: AnalyzeRequest) -> AnalyzeResponse:
    return await analyze_session(body)


@router.delete("/cache/{session_id}")
async def clear_cache(session_id: str) -> dict[str, str]:
    reset_session(session_id)
    await clear_queue(session_id)
    return {"status": "ok", "message": f"Đã reset cache reconciliation {session_id}"}


@router.get("/cache/{session_id}/processed")
async def list_processed(session_id: str) -> dict:
    session = get_session(session_id)
    return {
        "processed_messages": list(session.processed_messages),
        "processed_chat_ids": list(session.processed_chat_ids),
    }
