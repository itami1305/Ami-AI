"""
RAM cache phiên đối soát — markdown.md §11.
"""

from dataclasses import dataclass, field
from typing import Any

from backend.reconciliation.layout_cache import clear_layout_cache, layout_cache_stats


@dataclass
class SessionCache:
    processed_messages: set[str] = field(default_factory=set)
    image_hashes: list[str] = field(default_factory=list)
    last_scroll_y: int = 0
    last_message_id: str | None = None
    processed_chat_ids: set[str] = field(default_factory=set)


_reconciliation_cache: dict[str, SessionCache] = {}


def get_session(session_id: str) -> SessionCache:
    if session_id not in _reconciliation_cache:
        _reconciliation_cache[session_id] = SessionCache()
    return _reconciliation_cache[session_id]


def reset_session(session_id: str) -> None:
    _reconciliation_cache[session_id] = SessionCache()
    clear_layout_cache(session_id)


def delete_session(session_id: str) -> None:
    _reconciliation_cache.pop(session_id, None)


def cache_stats() -> dict[str, Any]:
    return {
        "sessions": len(_reconciliation_cache),
        "session_ids": list(_reconciliation_cache.keys()),
        "layout": layout_cache_stats(),
    }
