"""
Planner dựa luật (offline) — dùng khi POST /reconciliation/plan lỗi hoặc confidence < ngưỡng.

Ưu tiên:
    1) Đủ số vòng không tin mới → stop_inner (bỏ qua khi segment_mode).
    2) Có stop_date và tin trong snapshot đã đạt ngưỡng (ISO date/datetime vs dd/mm/yyyy).
    3) Sidebar còn chat chưa trong processed_chat_ids → open_chat (bỏ qua khi segment_mode).
    4) Không còn sidebar nhưng đã xử lý chat → stop_outer (bỏ qua khi segment_mode).
    5) Mặc định: scroll lên để đọc thêm lịch sử.

Tham khảo markdown.md §8.4.
"""

from __future__ import annotations

from backend.reconciliation.date_separator import is_date_separator_text, resolve_chat_date_display
from backend.reconciliation.stop_datetime import message_reached_stop_threshold

from app.logic.reconciliation.models import AgentAction, ReconciliationState


def _sidebar_chat_id(item: dict, index: int) -> str:
    """Ổn định id chat từ OCR (id/name) hoặc fallback theo index."""
    return str(item.get("id") or item.get("name") or f"chat_{index}")


def rule_planner(snapshot: dict, state: ReconciliationState) -> AgentAction:
    """Chọn AgentAction đơn giản từ snapshot + state hiện tại (không gọi LLM)."""
    if not state.segment_mode and state.no_new_count >= 2:
        return AgentAction(action="stop_inner", confidence=1.0, reason="Không còn tin mới sau 2 scroll")

    stop_date = state.stop_date or snapshot.get("stop_date") or ""
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
                return AgentAction(
                    action="stop_inner",
                    confidence=1.0,
                    reason=f"Tin ngày {msg_date} <= stop_date {stop_date}",
                )

    if not state.segment_mode:
        sidebar = snapshot.get("sidebar") or []
        for i, item in enumerate(sidebar):
            cid = _sidebar_chat_id(item, i)
            if cid not in state.processed_chat_ids:
                return AgentAction(
                    action="open_chat",
                    params={"sidebar_index": i, "chat_id": cid},
                    confidence=0.95,
                    reason=f"Mở sidebar[{i}]",
                )

    sidebar = snapshot.get("sidebar") or []
    if not state.segment_mode and not sidebar and state.processed_chat_ids:
        return AgentAction(action="stop_outer", confidence=0.9, reason="Hết sidebar")

    return AgentAction(
        action="scroll",
        params={"direction": "up"},
        confidence=0.85,
        reason="Cuộn lên đọc lịch sử (theo chiều cao khung chat)",
    )
