# Cấu trúc dự án Ami-AI-Automation

> **Quy tắc:** Luôn đọc file này trước khi sửa code. Cập nhật file này khi thêm/xóa module hoặc thay đổi kiến trúc.

## Tổng quan

Ứng dụng Windows (Python) + Backend API (FastAPI), tách biệt hoàn toàn.

Cấu trúc dự án
│
├── README.md                       # Hướng dẫn cài đặt, chạy, release
├── structure.md                    # File này — cấu trúc thư mục
├── flow.md                         # Luồng hệ thống end-to-end
├── markdown.md                     # Spec đối soát (đồng bộ với code)
├── requirements.txt                # Dependency gộp (dev)
├── message.json                    # Mẫu cache tin nhắn (tham chiếu)
├── yolo.json                       # Mẫu layout YOLO (tham chiếu)
├── transactions.json               # Mẫu giao dịch AI (tham chiếu)
│
├── app/                            # ─── Win App ───
│   ├── main.py                     # Entry: QApplication + MainWindow
│   ├── config.py                   # AMI_BACKEND_URL, đường dẫn styles (frozen/source)
│   ├── requirements.txt            # PySide6, httpx, Pillow, ...
│   ├── requirements-build.txt      # PyInstaller (build exe)
│   │
│   ├── styles/                     # Stylesheet QSS
│   │   ├── style.qss               # Theme chung (đỏ tươi)
│   │   ├── chat.qss                # Module Chat
│   │   └── reconciliation.qss      # Module Đối soát
│   │
│   ├── ui/                         # Chỉ giao diện (widget, layout, signal)
│   │   ├── main_window.py          # Sidebar | Stack module | SystemLog
│   │   ├── sidebar.py              # Chuyển tab Chat / Đối soát
│   │   ├── system_log.py           # Log có màu theo [OK][WARN][ERROR][INFO]
│   │   ├── chat/
│   │   │   └── chat_widget.py      # UI messenger, gửi tin
│   │   └── reconciliation/
│   │       ├── reconciliation_widget.py  # Date picker, chế độ quét, nút Chạy/Dừng
│   │       └── dialogs.py              # Preview ảnh / JSON / danh sách tin
│   │
│   └── logic/                      # Logic nghiệp vụ (không Qt UI)
│       ├── api_client.py           # HTTP → Backend, prefix log
│       ├── chat_service.py         # Gọi POST /chat/completions
│       └── reconciliation/
│           ├── orchestrator.py     # Điều phối loop-1 / loop-2 toàn phiên
│           ├── screenshot.py       # Chụp full màn / vùng chat
│           ├── mouse_control.py    # Click sidebar, cuộn, focus giữa hội thoại
│           ├── window_checker.py   # Tìm cửa sổ Zalo / Messenger (Win32)
│           ├── bbox.py               # Bbox normalized ↔ pixel ↔ màn hình
│           ├── planner.py            # Rule planner fallback
│           ├── models.py             # ReconciliationState, FsmState, AgentAction
│           ├── message_store.py        # Catalog tin → messages.json
│           ├── chat_sessions.py      # Gom bubble → chat_session
│           ├── csv_export.py           # transactions.csv + transactions.json
│           ├── transaction_extract.py  # Tin tổng hợp / ảnh CK → TransactionRecord
│           ├── paths.py                # exports/reconciliation/sessions/
│           └── date_filter.py        # Chuẩn hóa & so sánh ngày YYYY-MM-DD
│
├── backend/                        # ─── Backend API ───
│   ├── main.py                     # FastAPI app, CORS, lifespan (plan worker)
│   ├── __main__.py                 # python -m backend
│   ├── run_server.py               # Script chạy uvicorn
│   ├── config.py                   # Settings: Ollama, cache_dir, data_dir, port
│   ├── requirements.txt            # fastapi, uvicorn, opencv, httpx, ...
│   ├── nodemon.json                # Reload dev (tùy chọn)
│   │
│   ├── api/                        # Route HTTP (mỏng, gọi services)
│   │   ├── chat.py                 # POST /chat/completions
│   │   └── reconciliation.py       # POST /yolo, /ocr · GET /plan
│   │
│   ├── services/                   # Xử lý nghiệp vụ
│   │   ├── yolo_service.py         # Phân tích bố cục màn hình (layout)
│   │   ├── ocr_service.py          # Upscale, OCR, parse ngày, đẩy cache
│   │   ├── cache_store.py          # Session UUID, yolo_layout, chat_session, CSV
│   │   ├── ollama_service.py       # Chat + extract_transactions (JSON)
│   │   └── plan_worker.py          # Worker nền: quét cache → Ollama → CSV
│   │
│   ├── cache/                      # Runtime — không commit
│   │   └── sessions/{session_id}/
│   │       ├── yolo_layout.json
│   │       ├── chat_session.json
│   │       └── plan_done.flag
│   │
│   └── data/                       # Runtime — không commit
│       ├── messages_{session_id}.csv
│       ├── transactions_{session_id}.json
│       └── transactions.csv        # Gộp giao dịch mọi phiên
│
├── build/                          # ─── Đóng gói & cài đặt ───
│   ├── app.spec                    # PyInstaller Win App
│   ├── backend.spec                # PyInstaller Backend exe
│   ├── Start-App.bat               # Khởi chạy app (release)
│   ├── Start-Backend.bat           # Khởi chạy backend (release)
│   ├── INSTALL.txt                 # Hướng dẫn máy không có Python
│   ├── app/                        # Artifact build app (gitignore một phần)
│   └── backend/                    # Artifact build backend
│
└── scripts/
    ├── build_release.ps1           # Build app + backend → release/ + ZIP
    └── build_app.ps1               # Chỉ build giao diện exe
```

## Phát hành (máy khác không cần Python)
- `.\scripts\build_release.ps1` → `release\` + `Ami-AI-Automation-Release.zip`
- Máy đích: `Start-Backend.bat` → `Start-App.bat`
- App trỏ API qua biến môi trường `AMI_BACKEND_URL` (mặc định `http://127.0.0.1:8765`)

## giao diện: side bar | container | systemlog
- giao diện màu chủ đạo đỏ tươi, nền trắng giao diện hiện đại
- giao diện viết theo widget, sử dụng file style.qss giao diện chung và từng file .qss cho từng module
- trình bày code theo từng function dễ hiểu, tách giao diện riêng và logic riêng
## Module Chat
- UI giống với giao diện messager
- **Luồng:** App UI → `POST /chat/completions` → Backend ghép prompt (luôn yêu cầu tiếng Việt) → Ollama `gemma4:e2b` → trả reply.

## Module Reconciliation (Đối soát chat)
- quét đoạn chat hoặc đối soát toàn bộ danh bạ
- **Orchestrator:** `app/logic/reconciliation/orchestrator.py` — loop-1 / loop-2
- **Hàm lõi giữ nguyên:** `screenshot.py`, `window_checker.py`, `mouse_control.py`, `date_filter.py`

Tách ra từng hàm với các chức năng theo luồng
FE
-> Khi
-> bộ lọc ngày kết thúc (date time picker)
-> chọn rà soát đoạn chat/ rà soát toàn bộ
-> chụp màn hình gửi dạng bite cho api `/reconciliation/yolo` để lấy bố cục màn hình, lưu vào cache
-> thực hiện vòng lặp:
loop-1:
+ Chọn đoạn chat: nhấn vào trung tâm đoạn chat(nếu là rà soát đoạn chat thì bỏ qua phần này)
+ nếu chọn đến đoạn chat cuối cùng thì cuộn chuột theo chiều dài khung chat
+ di chuyển chuột đến trung tâm nội dung hội thoại
    loop-2:
    + chụp màn hình (chỉ gửi đoạn chat) dạng bite gửi cho api `/reconciliation/ocr?cropped=true` và chờ phản hồi để lấy response ngày đoạn chat
    + ngày đoạn chat <= ngày kết thúc (format về cùng 1 dạng YYYY-mm-dd) thì dừng loop-2
    + nếu tin nhắn đầu tiên < ngày kết thúc thì dừng loop-1
-> hiển thị log từng bước

BE
-> api `/chat/completions` → Backend ghép prompt (luôn yêu cầu tiếng Việt) → Ollama `gemma4:e2b` → trả reply.
-> api `/reconciliation/yolo` → Yolo phân tích bố cục màn hình, trả về Mẫu tham chiếu: **`yolo.json`**
-> api `/reconciliation/ocr` → Upscale ảnh x2 bằng cv2 -> OCR detext từ ảnh -> push đoạn chat mới vào cache -> lưu CSV -> trả ngày/giờ tin nhắn. `cropped=true` khi ảnh đã là vùng chat.
-> plan worker nền (`segment-queue`) — Ollama tách giao dịch không chặn loop OCR
-> api `/reconciliation/perceive` — tương thích cũ (YOLO + OCR full)

## Ghi chú
- Client đối soát: `app/logic/reconciliation/*` (nghiệp vụ) + `app/ui/reconciliation/*` (giao diện).
- `PROJECT_STRUCTURE.md` — bản tóm tắt; chi tiết cây thư mục dùng file này.
