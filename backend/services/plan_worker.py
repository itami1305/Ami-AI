"""
Worker nền — xử lý hàng đợi đoạn chat (Ollama tách giao dịch) không chặn loop OCR.
Dùng segment_queue hiện có.
"""

from __future__ import annotations

import logging

from backend.reconciliation.models import SegmentQueueActivateRequest
from backend.reconciliation.segment_queue import activate_queue, deactivate_queue, get_queue_status

logger = logging.getLogger(__name__)

_active_sessions: set[str] = set()


async def ensure_session_worker(
    session_id: str,
    *,
    app_type: str = "zalo_pc",
    csv_path: str | None = None,
) -> dict:
    """Bật worker nền cho phiên nếu chưa active."""
    if session_id in _active_sessions:
        return await get_queue_status(session_id)
    req = SegmentQueueActivateRequest(
        session_id=session_id,
        app_type=app_type,
        csv_path=csv_path,
        save_csv=bool(csv_path),
    )
    status = await activate_queue(req)
    _active_sessions.add(session_id)
    logger.info("Plan worker active session=%s", session_id)
    return status


async def stop_session_worker(session_id: str) -> dict:
    """Tắt worker khi phiên kết thúc."""
    _active_sessions.discard(session_id)
    return await deactivate_queue(session_id)
