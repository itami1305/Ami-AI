"""
# Cấu hình Win App (client)
"""

import os
from pathlib import Path

# --- URL Backend API ---
BACKEND_URL = os.getenv("AMI_BACKEND_URL", os.getenv("BACKEND_URL", "http://127.0.0.1:8000"))

# --- Thư mục xuất CSV ---
BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = BASE_DIR / "exports"

# --- Timeout HTTP (giây) ---
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "120"))

# --- Automation mặc định ---
SCROLL_AMOUNT = int(os.getenv("SCROLL_AMOUNT", "3"))
SCROLL_PIXELS_PER_CLICK = int(os.getenv("SCROLL_PIXELS_PER_CLICK", "120"))
SCROLL_PAUSE = float(os.getenv("SCROLL_PAUSE", "0.8"))
CHAT_LOAD_WAIT = float(os.getenv("CHAT_LOAD_WAIT", "1.5"))

# --- Crop ảnh chụp (phía Win app, trước khi gửi backend) ---
CHAT_TOP_SKIP_PX = int(os.getenv("CHAT_TOP_SKIP_PX", "200"))
# Khung chat (bỏ sidebar / header tên hội thoại / panel phải khi OCR tin) do backend tính:
# CHAT_SIDEBAR_RATIO, CHAT_RIGHT_RATIO, CHAT_INNER_TOP_RATIO trong backend/config.py (hoặc .env của tiến trình API).
