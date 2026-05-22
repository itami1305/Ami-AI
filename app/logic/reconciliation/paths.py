"""
Đường dẫn export — exports/reconciliation/sessions/{session_id}/ (§10.7).

Mỗi phiên đối soát có thư mục riêng: ảnh full màn hình, CSV/JSON giao dịch,
messages.json (catalog OCR) — thư mục exports/reconciliation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.config import EXPORT_DIR


def ensure_export_dir() -> Path:
    """Tạo thư mục gốc reconciliation dưới EXPORT_DIR nếu chưa có."""
    base = EXPORT_DIR / "reconciliation"
    base.mkdir(parents=True, exist_ok=True)
    return base


def session_export_dir(session_id: str) -> Path:
    """
    Thư mục một phiên: screenshots (full_*), summaries, messages.json,
    transactions*.csv/json — session_id xác định duy nhất phiên người dùng chạy.
    """
    base = ensure_export_dir() / "sessions" / session_id
    (base / "screenshots").mkdir(parents=True, exist_ok=True)
    (base / "summaries").mkdir(parents=True, exist_ok=True)
    return base


def default_csv_path(session_id: str) -> Path:
    """Tên file CSV có timestamp để không ghi đè nếu chạy nhiều lần cùng session_id."""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return session_export_dir(session_id) / f"transactions_{date_str}.csv"
