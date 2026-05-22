"""
Hàng đợi đoạn chat (RAM) — worker asyncio xử lý tuần tự qua Ollama.

Luồng:
  - App/backend enqueue đoạn chat_session → RAM (asyncio.Queue).
  - Worker (khi active) lấy từng đoạn → split_chat_transactions → xóa khỏi hàng đợi.
  - Kết quả đưa vào finished để app drain và ghi CSV/JSON local.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.reconciliation.models import (
    ChatSegmentInfo,
    SegmentQueueActivateRequest,
    SplitTransactionsRequest,
    SplitTransactionsResponse,
)
from backend.reconciliation.transaction_split_service import split_chat_transactions

logger = logging.getLogger(__name__)

_MAX_FINISHED = 100


@dataclass
class QueuedSegment:
    segment: ChatSegmentInfo
    app_type: str = "zalo_pc"
    enqueued_at: str = ""


@dataclass
class SessionSegmentQueue:
    session_id: str
    queue: asyncio.Queue[QueuedSegment] = field(default_factory=asyncio.Queue)
    seen_ids: set[str] = field(default_factory=set)
    active: bool = False
    processing_id: str | None = None
    worker_task: asyncio.Task | None = None
    app_type: str = "zalo_pc"
    csv_path: str | None = None
    save_csv: bool = True
    finished: list[SplitTransactionsResponse] = field(default_factory=list)
    total_enqueued: int = 0
    total_processed: int = 0
    last_error: str | None = None


_queues: dict[str, SessionSegmentQueue] = {}
_global_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_queue(session_id: str) -> SessionSegmentQueue:
    async with _global_lock:
        if session_id not in _queues:
            _queues[session_id] = SessionSegmentQueue(session_id=session_id)
        return _queues[session_id]


async def activate_queue(req: SegmentQueueActivateRequest) -> dict:
    """Bật worker xử lý hàng đợi cho phiên (gọi khi vào tab Reconciliation)."""
    state = await _get_queue(req.session_id)
    async with _global_lock:
        state.active = True
        state.app_type = req.app_type
        state.csv_path = req.csv_path
        state.save_csv = req.save_csv
    await _ensure_worker(req.session_id)
    return await get_queue_status(req.session_id)


async def deactivate_queue(session_id: str) -> dict:
    """Tắt worker khi rời tab (không xóa hàng đợi đang chờ)."""
    state = await _get_queue(session_id)
    async with _global_lock:
        state.active = False
        task = state.worker_task
        state.worker_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return await get_queue_status(session_id)


async def clear_queue(session_id: str) -> None:
    """Xóa hàng đợi RAM (khi reset cache phiên)."""
    async with _global_lock:
        state = _queues.pop(session_id, None)
    if not state:
        return
    if state.worker_task and not state.worker_task.done():
        state.worker_task.cancel()
        try:
            await state.worker_task
        except asyncio.CancelledError:
            pass
    while not state.queue.empty():
        try:
            state.queue.get_nowait()
        except asyncio.QueueEmpty:
            break


async def enqueue_segment(
    session_id: str,
    segment: ChatSegmentInfo,
    *,
    app_type: str = "zalo_pc",
) -> dict:
    """Thêm đoạn chat vào RAM; worker xử lý lần lượt nếu đang active."""
    if not (segment.text or "").strip():
        return {"accepted": False, "reason": "empty_text"}

    state = await _get_queue(session_id)
    seg_id = segment.id or ""

    async with _global_lock:
        if seg_id and seg_id in state.seen_ids:
            return {"accepted": False, "reason": "duplicate", "segment_id": seg_id}
        if seg_id:
            state.seen_ids.add(seg_id)
        state.total_enqueued += 1
        item = QueuedSegment(segment=segment, app_type=app_type, enqueued_at=_now_iso())
        await state.queue.put(item)

    if state.active:
        await _ensure_worker(session_id)

    status = await get_queue_status(session_id)
    return {
        "accepted": True,
        "segment_id": seg_id,
        **status,
    }


async def get_queue_status(session_id: str) -> dict:
    state = await _get_queue(session_id)
    return {
        "session_id": session_id,
        "active": state.active,
        "pending": state.queue.qsize(),
        "processing_id": state.processing_id,
        "total_enqueued": state.total_enqueued,
        "total_processed": state.total_processed,
        "finished_pending": len(state.finished),
        "last_error": state.last_error,
    }


async def drain_finished(session_id: str) -> dict:
    """App lấy kết quả đã xử lý xong (pop khỏi RAM finished)."""
    state = await _get_queue(session_id)
    async with _global_lock:
        batch = [r.model_dump() for r in state.finished]
        state.finished.clear()
    return {"session_id": session_id, "results": batch, "count": len(batch)}


async def _ensure_worker(session_id: str) -> None:
    state = await _get_queue(session_id)
    async with _global_lock:
        if not state.active:
            return
        if state.worker_task and not state.worker_task.done():
            return
        state.worker_task = asyncio.create_task(
            _worker_loop(session_id),
            name=f"segment_queue_{session_id[:8]}",
        )


async def _worker_loop(session_id: str) -> None:
    """Lấy từng đoạn từ hàng đợi → AI → pop khỏi RAM → lưu finished."""
    state = await _get_queue(session_id)
    logger.info("Segment queue worker started: %s", session_id)

    try:
        while True:
            async with _global_lock:
                if not state.active:
                    break

            try:
                item = await asyncio.wait_for(state.queue.get(), timeout=1.5)
            except asyncio.TimeoutError:
                async with _global_lock:
                    if not state.active and state.queue.empty():
                        break
                continue

            seg_id = item.segment.id or "?"
            async with _global_lock:
                state.processing_id = seg_id
                state.last_error = None

            try:
                req = SplitTransactionsRequest(
                    session_id=session_id,
                    segment=item.segment,
                    app_type=item.app_type or state.app_type,
                    save_csv=state.save_csv,
                    csv_path=state.csv_path,
                    append_csv=True,
                    use_llm=True,
                )
                result = await split_chat_transactions(req)
            except Exception as exc:
                logger.exception("Segment queue split failed: %s", seg_id)
                async with _global_lock:
                    state.last_error = str(exc)
                    result = SplitTransactionsResponse(
                        success=False,
                        transaction_count=0,
                        error=str(exc),
                    )
            else:
                async with _global_lock:
                    state.total_processed += 1
                    state.finished.append(result)
                    while len(state.finished) > _MAX_FINISHED:
                        state.finished.pop(0)

            async with _global_lock:
                state.processing_id = None

            state.queue.task_done()
            logger.info(
                "Segment queue done %s: %d GD (pending=%d)",
                seg_id,
                result.transaction_count,
                state.queue.qsize(),
            )

            async with _global_lock:
                if not state.active and state.queue.empty():
                    break
    except asyncio.CancelledError:
        logger.info("Segment queue worker cancelled: %s", session_id)
        raise
    finally:
        async with _global_lock:
            state.processing_id = None
            state.worker_task = None
        logger.info("Segment queue worker stopped: %s", session_id)
