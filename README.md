# Ami-AI

Ứng dụng Windows (Python) + Backend FastAPI cho **Chat AI** (Ollama `gemma4:e2b`, luôn tiếng Việt) và **Đối soát kế toán** (automation chat theo `markdown.md`).

## Cấu trúc

Xem chi tiết tại [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Yêu cầu

- Python 3.11+
- [Ollama](https://ollama.com/) đã cài và pull model: `ollama pull gemma4:e2b`
- Windows 10/11 (module đối soát dùng capture/automation)

## Cài đặt

> **Quan trọng:** Luôn chạy lệnh từ thư mục gốc `Ami-AI\`, không chạy từ `Ami-AI\app\`.

```powershell
cd D:\ChuongNV\Source\Ami-AI

# Backend
pip install -r requirements-backend.txt

# Win App — tối thiểu (đủ cho tab Chat + test OCR)
pip install -r requirements.txt

# Tùy chọn — automation đối soát (scroll/click)
pip install -r requirements-automation.txt

# Sao chép cấu hình (tùy chọn)
copy .env.example .env
```

## Chạy

**Terminal 1 — Backend:**

```powershell
cd D:\ChuongNV\Source\Ami-AI
.\run_backend.ps1
# hoặc: uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Win App:**

```powershell
cd D:\ChuongNV\Source\Ami-AI
.\run_app.ps1
# hoặc: python -m app.main
```

## Xử lý lỗi cài đặt

### Không cài được `pyautogui`?

Dự án đã **không còn dùng `pyautogui`** — thay bằng `pynput` (pure Python, có wheel sẵn, không yêu cầu build từ source). Bạn chỉ cần:

```powershell
pip install -r requirements-automation.txt
```

Nếu vẫn lỗi do `dxcam` (capture nhanh), có thể bỏ dòng đó — code tự fallback sang `PIL.ImageGrab`.

### Tách hẳn môi trường

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-backend.txt
pip install -r requirements.txt
pip install -r requirements-automation.txt
```

## Module

| Module | Mô tả |
|--------|--------|
| **Chat** | UI chat → Backend ghép prompt (tiếng Việt) → Ollama `gemma4:e2b` |
| **Đối soát** | Chụp màn hình → OCR API → detect giao dịch → CSV trong `exports/` |

## API docs

Sau khi chạy backend: http://127.0.0.1:8000/docs

## Ghi chú OCR

Backend dùng **EasyOCR** (`vi` + `en`) trong `backend/reconciliation/ocr_engine.py`. Lần OCR đầu có thể chậm (~vài giây) khi tải model.
