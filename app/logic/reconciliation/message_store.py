"""Lưu tin nhắn OCR — exports/reconciliation/sessions/.../messages.json

Mỗi dòng tin (type=chat_session): session_id = một lượt chat giữa hai mốc ngày/giờ,
reconciliation_session_id = phiên đối soát (UUID thư mục export).
Bubble OCR thô được gom trong bubble_catalog rồi rebuild thành chat_session.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.config import EXPORT_DIR
from app.logic.reconciliation.chat_sessions import build_chat_sessions

MessageScope = Literal["current", "session", "all_sessions"]


def messages_file(session_dir: Path) -> Path:
    return session_dir / "messages.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bubble_sort_y(msg: dict) -> float:
    bbox = msg.get("bbox") or {}
    if isinstance(bbox, dict) and bbox.get("y") is not None:
        return float(bbox["y"])
    if msg.get("y") is not None:
        return float(msg["y"])
    return 0.0


def _upsert_bubble(
    bubble_catalog: dict[str, dict],
    msg: dict,
    *,
    chat_id: str,
    chat_name: str,
) -> bool:
    mid = str(msg.get("id") or "").strip()
    if not mid:
        return False
    is_new = mid not in bubble_catalog
    entry = {
        "id": mid,
        "chat_id": chat_id or chat_name,
        "chat_name": chat_name or chat_id or "—",
        "type": msg.get("type") or "text",
        "role": msg.get("role") or "other",
        "text": (msg.get("text") or "").strip(),
        "date": msg.get("date") or "",
        "time": msg.get("time") or "",
        "bbox": msg.get("bbox") or {},
        "y": _bubble_sort_y(msg),
    }
    bubble_catalog[mid] = entry
    return is_new


def _bubbles_for_chat(
    bubble_catalog: dict[str, dict],
    chat_id: str,
    chat_name: str,
) -> list[dict]:
    if not bubble_catalog:
        return []
    cid = chat_id or chat_name
    if not cid:
        return list(bubble_catalog.values())
    matched = [
        b
        for b in bubble_catalog.values()
        if b.get("chat_id") == cid
        or b.get("chat_name") == chat_name
        or (chat_id and b.get("chat_id") == chat_id)
    ]
    return matched if matched else list(bubble_catalog.values())


def _rebuild_messages_catalog(
    bubble_catalog: dict[str, dict],
    messages_catalog: dict[str, dict],
    *,
    chat_id: str,
    chat_name: str,
    reconciliation_session_id: str,
) -> int:
    """Gom bubble của chat hiện tại → các dòng chat_session; trả số session mới."""
    chat_key = chat_id or chat_name
    bubbles = _bubbles_for_chat(bubble_catalog, chat_id, chat_name)

    sessions, new_sessions = build_chat_sessions(
        bubbles,
        chat_id=chat_id,
        chat_name=chat_name,
        reconciliation_session_id=reconciliation_session_id,
        existing_catalog=messages_catalog,
    )

    now = _now_iso()
    for sid, entry in sessions.items():
        entry["updated_at"] = now
        if sid not in messages_catalog:
            entry["first_seen_at"] = now
        elif messages_catalog[sid].get("first_seen_at"):
            entry["first_seen_at"] = messages_catalog[sid]["first_seen_at"]
        messages_catalog[sid] = entry

    stale = [
        k
        for k, v in messages_catalog.items()
        if v.get("type") == "chat_session"
        and (v.get("chat_id") or v.get("chat_name")) in (chat_key, chat_id, chat_name)
        and k not in sessions
    ]
    for k in stale:
        messages_catalog.pop(k, None)

    return new_sessions


def ingest_snapshot(
    catalog: dict[str, dict],
    snapshot: dict,
    *,
    chat_id: str,
    chat_name: str,
    reconciliation_session_id: str,
    bubble_catalog: dict[str, dict] | None = None,
) -> int:
    """
    Cập nhật bubble từ snapshot, rebuild lượt chat (session) giữa các mốc ngày/giờ.

    Returns:
        Số session mới (không tính bubble đơn lẻ).
    """
    bubbles = bubble_catalog if bubble_catalog is not None else catalog
    added_bubbles = 0
    for msg in snapshot.get("messages") or []:
        if _upsert_bubble(
            bubbles,
            msg,
            chat_id=chat_id,
            chat_name=chat_name,
        ):
            added_bubbles += 1

    if bubble_catalog is not None:
        return _rebuild_messages_catalog(
            bubble_catalog,
            catalog,
            chat_id=chat_id,
            chat_name=chat_name,
            reconciliation_session_id=reconciliation_session_id,
        )
    return added_bubbles


def mark_transaction_messages(catalog: dict[str, dict], message_ids: list[str]) -> None:
    for mid in message_ids:
        if mid in catalog:
            catalog[mid]["is_transaction"] = True


def persist_messages(session_dir: Path | None, catalog: dict[str, dict]) -> None:
    if session_dir is None or not catalog:
        return
    path = messages_file(session_dir)
    rows = sorted(
        catalog.values(),
        key=lambda m: (
            m.get("chat_name", ""),
            m.get("date", ""),
            m.get("time", ""),
            m.get("marker_before", ""),
            m.get("id", ""),
        ),
    )
    path.write_text(json.dumps({"messages": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def _reconciliation_sessions_root() -> Path:
    return EXPORT_DIR / "reconciliation" / "sessions"


def load_session_messages(session_id: str) -> list[dict]:
    path = _reconciliation_sessions_root() / session_id / "messages.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("messages") or [])
    except (json.JSONDecodeError, OSError):
        return []


def list_session_ids() -> list[str]:
    root = _reconciliation_sessions_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def load_all_sessions_messages() -> list[dict]:
    rows: list[dict] = []
    for sid in list_session_ids():
        rows.extend(load_session_messages(sid))
    return rows


def catalog_to_list(catalog: dict[str, dict]) -> list[dict]:
    return sorted(
        catalog.values(),
        key=lambda m: (
            m.get("chat_name", ""),
            m.get("date", ""),
            m.get("time", ""),
            m.get("marker_before", ""),
            m.get("id", ""),
        ),
    )
