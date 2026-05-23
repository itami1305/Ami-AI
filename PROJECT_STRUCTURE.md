# Cấu trúc dự án Ami-AI

> **Quy tắc:** Luôn đọc file này trước khi sửa code. Cập nhật file này khi thêm/xóa module hoặc thay đổi kiến trúc.

## Tổng quan

Ứng dụng Windows (Python) + Backend API (FastAPI), tách biệt hoàn toàn.

| Thành phần | Mô tả |
|-----------|--------|
| `app/` | Win App — UI + logic client |
| `backend/` | FastAPI — OCR, prompt, AI local |
| `markdown.md` | Spec đối soát chat automation (đồng bộ reconciliation) |

## Cây thư mục

```text
Ami-AI/
├── PROJECT_STRUCTURE.md      # File này — cấu trúc dự án
├── README.md
├── requirements.txt              # App bắt buộc (requests, Pillow)
├── requirements-automation.txt   # App tùy chọn (pynput, dxcam)
├── requirements-backend.txt      # Backend dependencies
├── run_app.ps1                   # Script chạy Win App
├── run_backend.ps1               # Script chạy Backend
├── .env.example
├── markdown.md               # Spec đối soát chat
├── yolo.json                 # Mẫu JSON OCR
│
├── backend/
│   ├── main.py               # FastAPI entry
│   ├── config.py             # Cấu hình backend
│   ├── transaction_money.py # Regex nhận diện số tiền (detect-transaction)
│   ├── chat/
│   │   ├── router.py         # API /chat/*
│   │   ├── prompt_builder.py # Ghép prompt trước khi gọi AI
│   │   └── ollama_client.py  # Gọi Ollama gemma4:e2b
│   └── reconciliation/
│       ├── router.py         # API /reconciliation/*
│       ├── models.py         # Perception JSON, TransactionRecord §10.4
│       ├── layout_regions.py
│       ├── ocr_engine.py     # EasyOCR bubble/sidebar
│       ├── cache.py
│       ├── ocr_service.py
│       ├── perceive_service.py
│       ├── planner_service.py
│       ├── transaction_detector.py
│       ├── dedupe_service.py
│       └── analyze_service.py
│
└── app/
    ├── main.py               # Entry Win App
    ├── config.py             # URL backend, cấu hình client
    ├── shared/
    │   └── api_client.py     # HTTP client dùng chung
    ├── chat/
    │   ├── ui.py             # Giao diện tab Chat
    │   └── logic.py          # Logic gọi backend chat
    ├── ui/
    │   ├── main_window.py
    │   ├── chat/chat_widget.py
    │   └── reconciliation/
    │       ├── reconciliation_widget.py  # Tab Đối soát + worker QThread
    │       └── dialogs.py              # Preview ảnh / JSON / tin
    └── logic/
        ├── api_client.py
        └── reconciliation/
            ├── orchestrator.py       # FSM INNER/OUTER → /reconciliation/*
            ├── screenshot.py         # Chụp cửa sổ / vùng chat
            ├── mouse_control.py      # Scroll, click (pynput)
            ├── window_checker.py
            ├── bbox.py
            ├── planner.py
            ├── models.py
            ├── paths.py              # exports/reconciliation/sessions/
            ├── message_store.py
            ├── chat_sessions.py
            ├── csv_export.py
            ├── transaction_extract.py
            └── date_filter.py
```

## Module Chat

- **Luồng:** App UI → `POST /chat/completions` → Backend ghép prompt (luôn yêu cầu tiếng Việt) → Ollama `gemma4:e2b` → trả reply.
- **File chính:** `backend/chat/prompt_builder.py`, `backend/chat/ollama_client.py`, `app/chat/*`

## Module Reconciliation (Đối soát chat)

- **Spec:** `markdown.md` — capture, OCR, inner/outer loop, CSV/JSON export.
- **Luồng:** App capture → `POST /reconciliation/perceive` (hoặc `/ocr`) → plan → act → `transactions.json` → `POST /reconciliation/analyze`.
- **Export:** `exports/reconciliation/sessions/{session_id}/`
- **File chính:** `backend/reconciliation/*`, `app/logic/reconciliation/*`, `app/ui/reconciliation/*`

## API Backend

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/health` | Health check |
| POST | `/chat/completions` | Chat với prompt có cấu trúc |
| POST | `/reconciliation/perceive` | OCR + layout → Perception JSON (normalized) |
| POST | `/reconciliation/ocr` | OCR pixel bbox (tương thích) |
| POST | `/reconciliation/plan` | Rule planner → AgentAction |
| POST | `/reconciliation/detect-transaction` | Phát hiện GD từ text |
| POST | `/reconciliation/parse-summary` | Tách tin tổng hợp → nhiều GD |
| POST | `/reconciliation/analyze` | Gộp trùng + cảnh báo + tóm tắt |
| DELETE | `/reconciliation/cache/{session_id}` | Reset cache reconciliation |

## Chạy dự án

```bash
# Terminal 1 — Backend
cd backend
pip install -r ../requirements-backend.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — App
pip install -r requirements.txt
python -m app.main
```

## Biến môi trường (.env)

- `OLLAMA_BASE_URL` — mặc định `http://127.0.0.1:11434`
- `OLLAMA_MODEL` — mặc định `gemma4:e2b`
- `BACKEND_URL` — mặc định `http://127.0.0.1:8000`
- `CHAT_TOP_SKIP_PX` — cắt header/phần đầu cửa sổ khi chụp (**Win app**)
- `CHAT_RIGHT_RATIO`, `CHAT_SIDEBAR_RATIO`, `CHAT_INNER_TOP_RATIO` — tách khung OCR: bỏ panel phải, cột danh sách chat, và dải header tên hội thoại; **tin nhắn chỉ OCR trong vùng giữa** (**backend** API, không crop trùng ở app)

## Lịch sử thay đổi

| Ngày | Thay đổi |
|------|----------|
| 2026-05-19 | Khởi tạo cấu trúc dự án, module chat + đối soát kế toán |
| 2026-05-19 | Tách requirements.txt / requirements-automation.txt; thêm run_*.ps1 |
| 2026-05-20 | Cập nhật `markdown.md`: YOLO, layout, FSM, AI planner, API planned, lộ trình UPDATE |
| 2026-05-20 | Thêm module `reconciliation/` (backend + app), API `/reconciliation/*`, tab UI mới |
| 2026-05-20 | Gỡ hoàn toàn module `accounting`; chỉ còn `reconciliation` + chat |
