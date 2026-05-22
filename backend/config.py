"""
# Cấu hình Backend
Đọc biến môi trường cho Ollama và các tham số dịch vụ.
"""

import os
from pathlib import Path

# --- Đường dẫn gốc dự án ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Ollama (AI local) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

# --- Thời gian chờ HTTP (giây) ---
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "120"))

# --- Export CSV mặc định ---
DEFAULT_EXPORT_DIR = BASE_DIR / "exports"

# --- Layout OCR: YOLO + cache (layout_regions / vision/yolo_layout) ---
# Model .pt (class: sidebar, chat_region, right_panel). Không có model → suy luận CV từ ảnh.
YOLO_LAYOUT_MODEL = os.getenv("YOLO_LAYOUT_MODEL", "models/reconciliation_layout.pt")
YOLO_LAYOUT_CONF = os.getenv("YOLO_LAYOUT_CONF", "0.35")

# Override thủ công từng tỉ lệ sau khi YOLO/cache (tùy chọn).
CHAT_SIDEBAR_RATIO = os.getenv("CHAT_SIDEBAR_RATIO")
CHAT_RIGHT_RATIO = os.getenv("CHAT_RIGHT_RATIO")
CHAT_INNER_TOP_RATIO = os.getenv("CHAT_INNER_TOP_RATIO")
CHAT_BOTTOM_RATIO = os.getenv("CHAT_BOTTOM_RATIO")
