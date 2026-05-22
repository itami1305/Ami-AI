"""
Rule planner — §8.4 (module Reconciliation).
"""

from __future__ import annotations

import os

from backend.reconciliation.models import AgentActionResponse, PlanRequest
from backend.reconciliation.date_separator import is_date_separator_text, resolve_chat_date_display
from backend.reconciliation.stop_datetime import message_reached_stop_threshold
PLAN_CONFIDENCE_THRESHOLD = float(os.getenv("PLAN_CONFIDENCE_THRESHOLD", "0.75"))


def _sidebar_chat_id(item: dict, index: int) -> str:
    return str(item.get("id") or item.get("name") or f"chat_{index}")


def _processed_chat_ids(snapshot: dict, extra: set[str] | None = None) -> set[str]:
    processed = snapshot.get("processed") or {}
    ids = {str(x) for x in (processed.get("chat_ids") or [])}
    if extra:
        ids |= extra
    return ids


def rule_plan(req: PlanRequest, processed_chat_ids: set[str]) -> AgentActionResponse:
    snapshot = req.snapshot
    stop_date = (req.stop_date or snapshot.get("stop_date") or "").strip()

    if req.no_new_count >= 2 and not req.segment_only:
        return AgentActionResponse(
            action="stop_inner",
            confidence=1.0,
            reason="Không còn tin mới sau 2 lần scroll liên tiếp",
        )

    if stop_date:
        for msg in snapshot.get("messages") or []:
            text = (msg.get("text") or "").strip()
            msg_date = (msg.get("date") or "").strip()
            if not msg_date and (
                msg.get("type") == "date_separator" or is_date_separator_text(text)
            ):
                msg_date = resolve_chat_date_display(text) or ""
            elif msg_date:
                msg_date = resolve_chat_date_display(msg_date) or msg_date
            if msg_date and message_reached_stop_threshold(msg_date, stop_date):
                return AgentActionResponse(
                    action="stop_inner",
                    confidence=1.0,
                    reason=f"Đã thấy tin ngày {msg_date} <= stop_date {stop_date}",
                )

    if not req.segment_only:
        sidebar = snapshot.get("sidebar") or []
        for i, item in enumerate(sidebar):
            cid = _sidebar_chat_id(item, i)
            if cid not in processed_chat_ids:
                return AgentActionResponse(
                    action="open_chat",
                    params={"sidebar_index": i, "chat_id": cid},
                    confidence=0.95,
                    reason=f"Mở hội thoại sidebar[{i}] chưa xử lý",
                )

    if not snapshot.get("chat_detected", True):
        return AgentActionResponse(
            action="wait",
            params={"ms": 800},
            confidence=0.5,
            reason="Chưa nhận diện vùng chat — đợi UI",
        )

    sidebar = snapshot.get("sidebar") or []
    if not req.segment_only and not sidebar and processed_chat_ids:
        return AgentActionResponse(
            action="stop_outer",
            confidence=0.9,
            reason="Không còn mục sidebar — kết thúc phiên",
        )

    return AgentActionResponse(
        action="scroll",
        params={"direction": "up"},
        confidence=0.85,
        reason="Tiếp tục cuộn lên để đọc lịch sử (theo chiều cao khung chat)",
    )


def plan(req: PlanRequest, session_processed_chat_ids: set[str]) -> AgentActionResponse:
    merged = _processed_chat_ids(req.snapshot, session_processed_chat_ids)
    action = rule_plan(req, merged)
    if action.confidence >= PLAN_CONFIDENCE_THRESHOLD:
        return action
    return action
