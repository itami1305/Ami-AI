# CHAT TRANSACTION AUTOMATION SYSTEM

> **Spec đối soát chat** — đồng bộ với `PROJECT_STRUCTURE.md`, `yolo.json`.  
> **Chiến lược:** Nâng cấp (UPDATE) trên codebase hiện có, không làm mới toàn bộ repo.  
> **Cập nhật:** 2026-05-20  
> **Module Accounting đã gỡ:** chỉ còn **reconciliation** — API `/reconciliation/*`, client `app/logic/reconciliation/` + `app/ui/reconciliation/`.

---

## 1. Mục tiêu hệ thống

AI agent tự động trên Windows:

1. Nhận diện cửa sổ chat (Zalo PC, Messenger qua Chrome, …)
2. Chụp màn hình
3. **YOLO** detect vùng UI (chat, sidebar, bubble, ảnh chuyển khoản)
4. **OCR** text trên từng vùng crop
5. **Layout understanding** — gom bubble, sidebar, role tin nhắn
6. **State machine** — điều phối INNER/OUTER loop
7. **AI planner** — quyết định: click đâu, scroll bao nhiêu, mở chat nào, đọc tiếp hay dừng
8. Gửi **JSON snapshot** cho AI phân tích giao dịch
9. Lưu **danh sách giao dịch** trích từ **cả hai nguồn**: tin nhắn tổng hợp (text) và ảnh chụp chuyển khoản (Zalo & Messenger)

### Ứng dụng hỗ trợ

| Ưu tiên | App | Ghi chú |
|---------|-----|---------|
| P0 | Zalo PC | `app/logic/reconciliation/screenshot.py` |
| P1 | Zalo Web / Messenger (Chrome) | Target `chrome` |
| P2 | Messenger Desktop, Telegram Desktop | Mở rộng `CAPTURE_TARGETS` + model YOLO |
| P3 | CRM chat, browser chat khác | Theo nhu cầu |

---

## 2. Kiến trúc tổng thể (mục tiêu)

```text
┌─────────────────────────────────────────────────────────────┐
│                        WIN APP                              │
│  screenshot.py │ mouse_control.py │ orchestrator.py (FSM)   │
└────────────────────────────┬────────────────────────────────┘
                             │ POST screenshot / GET plan
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND API (FastAPI)                   │
│  ┌──────────┐   ┌────────────┐   ┌─────────────────────────┐ │
│  │  YOLO    │ → │ OCR engine │ → │ Layout builder          │ │
│  │  vision  │   │ EasyOCR /  │   │ (messages, sidebar)   │ │
│  │          │   │ PaddleOCR  │   └───────────┬─────────────┘ │
│  └──────────┘   └────────────┘               │               │
│                                              ▼               │
│                    ┌─────────────────────────────────────┐ │
│                    │ Perception JSON (yolo.json schema)   │ │
│                    └──────────────────┬──────────────────┘ │
│                                       ▼                      │
│              ┌────────────────┐  ┌──────────────────────┐  │
│              │ Rule planner   │  │ LLM planner (Ollama) │  │
│              │ (ưu tiên)      │  │ POST /reconciliation/plan│  │
│              └────────┬───────┘  └──────────┬───────────┘  │
│                       └──────────┬───────────┘               │
│                                  ▼ AgentAction               │
│              ┌──────────────────────────────────────────┐  │
│              │ detect-transaction │ analyze (tổng hợp)   │  │
│              └──────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  RAM CACHE (session)  │  exports/ (ảnh + transactions.json) │
└─────────────────────────────────────────────────────────────┘
```

### Nguyên tắc thiết kế

- **Hybrid planner:** Rule-based khi confidence cao; LLM chỉ khi layout ambiguous.
- **Click theo bbox:** Tọa độ màn hình = `capture_offset` + bbox (pixel hoặc normalized) — không để LLM “đoán pixel” trực tiếp.
- **Deterministic FSM:** Trạng thái, điều kiện dừng, retry nằm trong code; LLM chỉ trả `AgentAction` có schema.

---

## 3. Trạng thái triển khai (2026-05-20)

| Thành phần | Trạng thái | File / ghi chú |
|------------|------------|----------------|
| Chụp Zalo PC / Chrome | ✅ Done | `app/logic/reconciliation/screenshot.py` |
| Scroll / click | ✅ Done | `app/logic/reconciliation/mouse_control.py` (pynput) |
| INNER / OUTER loop | ✅ Done | `app/logic/reconciliation/orchestrator.py` |
| OCR EasyOCR + layout cache | ✅ Done | `backend/reconciliation/ocr_*`, `vision/yolo_layout.py` |
| Detect giao dịch keyword/regex | ✅ Done | `transaction_detector.py` |
| CSV text | ✅ Done | `app/logic/reconciliation/csv_export.py` |
| YOLO / CV layout | ✅ Done | `backend/reconciliation/vision/yolo_layout.py` |
| Layout từ ảnh (cache) | ✅ Done | `layout_regions.py` + `layout_cache.py` |
| `transaction_image` + lưu ảnh CK | ⏳ Planned | Nguồn B — §10.6 |
| Tin tổng hợp `summary_text` | ⏳ Planned | Nguồn A — §10.3, parse nhiều dòng / bubble |
| Schema `TransactionRecord` §10.4 | ⏳ Planned | CSV/JSON đầy đủ trường, dedupe A↔B |
| State machine (FSM) | ⏳ Planned | Refactor `logic.py` |
| AI planner `/reconciliation/plan` | ⏳ Planned | Dùng Ollama như module chat |
| `/reconciliation/analyze` tổng hợp | ⏳ Planned | Batch JSON → summary |
| OUTER click theo sidebar OCR | ⏳ Planned | Hiện demo `next_chat_y += 80` |

---

## 4. Luồng xử lý tổng thể

### 4.1 OUTER LOOP — danh sách hội thoại

```text
Chọn / mở hội thoại tiếp theo (sidebar)
    ↓
Reset cache session
    ↓
INNER LOOP
    ↓
Đánh dấu chat đã xử lý (processed_chat_ids)
    ↓
Còn chat? → click sidebar[item] → lặp
    ↓
Hết → kết thúc phiên
```

### 4.2 INNER LOOP — đọc lịch sử một chat

```text
Capture screenshot
    ↓
POST /reconciliation/perceive  (YOLO + OCR + layout)  [hiện: POST /reconciliation/ocr]
    ↓
POST /reconciliation/plan      → AgentAction           [planned]
    ↓
Thực thi action (scroll | click | stop)
    ↓
Với mỗi message mới:
    - detect-transaction (rule / LLM)
    - lưu CSV + ảnh crop nếu transaction_image
    ↓
Điều kiện dừng? → thoát INNER
    ↓
Ngược lại → scroll → lặp
```

### 4.3 Điều kiện dừng INNER LOOP

| Case | Điều kiện |
|------|-----------|
| 1 | Scroll ≥ 2 lần liên tiếp không có message mới |
| 2 | `message.date <= stop_date` (user cấu hình) |
| 3 | Planner trả `action: stop_inner` |
| 4 | `max_iterations` / user bấm Dừng |

### 4.4 Điều kiện chuyển OUTER (chat tiếp theo)

| Case | Điều kiện |
|------|-----------|
| 1 | INNER kết thúc (hết lịch sử hoặc stop_date) |
| 2 | Planner trả `action: open_chat` với `sidebar[index]` |
| 3 | Không còn sidebar item chưa trong `processed_chat_ids` |

---

## 5. WIN APP

### 5.1 Trách nhiệm

| Chức năng | Mô tả |
|-----------|--------|
| Detect cửa sổ | `win32gui`, keyword trong `CAPTURE_TARGETS` |
| Chụp màn hình | PrintWindow → dxcam → ImageGrab; bỏ header `CHAT_TOP_SKIP_PX` |
| Upload ảnh | `POST /reconciliation/ocr` (sẽ đổi tên `/perceive` khi có YOLO) |
| Thực thi action | `scroll_chat_up`, `click_at`, `click_next_chat` |
| FSM | `AccountingLogic` → refactor thành state + `execute_action()` |
| UI | Tab Đối soát: start/stop, log, xem ảnh, CSV |

### 5.2 Công nghệ (thực tế trong repo)

| Thành phần | Công nghệ |
|------------|-----------|
| UI | PySide6 |
| Capture | dxcam, PrintWindow, PIL |
| Automation | **pynput** (không dùng pyautogui) |
| Detect window | pywin32 |
| HTTP | requests (`app/shared/api_client.py`) |
| Async UI | QThread worker |

### 5.3 Capture flow

```text
Detect app window (Zalo / Chrome)
    ↓
Crop bỏ title bar (top_skip)
    ↓
Encode JPEG
    ↓
POST backend (+ session_id)
    ↓
Lưu capture_offset_x/y cho map bbox → screen coords
```

---

## 6. BACKEND — Perception pipeline

### 6.1 Pipeline mục tiêu

```text
Screenshot (bytes)
    ↓
[Planned] YOLO inference → boxes (class, bbox normalized)
    ↓
Layout builder:
    - chat_region
    - messages[] (bubble)
    - sidebar[]
    - transfer_image crops
    ↓
OCR từng crop (không OCR full màn hình)
    ↓
Perception JSON (schema yolo.json)
    ↓
Cache theo image hash (đã có)
```

### 6.2 YOLO — class đề xuất

| Class | Mục đích |
|-------|----------|
| `chat_region` | Vùng tin nhắn chính |
| `sidebar` | Cột danh sách hội thoại |
| `message_bubble` | Một tin nhắn (text) |
| `transfer_image` | Ảnh bill / screenshot CK (nguồn ảnh) |
| `transaction_summary` | Bubble tin **tổng hợp** nhiều giao dịch (nguồn text) |
| `date_separator` | Nhãn ngày (tùy chọn) |
| `scroll_area` | Vùng cuộn (tùy chọn) |

### 6.3 OCR

| Engine | Vai trò |
|--------|---------|
| **EasyOCR** (vi + en) | Đang dùng — `ocr_engine.py` |
| **PaddleOCR** | Khuyến nghị cho ảnh bill CK (Phase 3) |
| Tesseract | Không khuyến nghị |

### 6.4 API hiện có và kế hoạch

| Method | Path | Trạng thái | Mô tả |
|--------|------|------------|--------|
| POST | `/reconciliation/ocr` | ✅ | OCR screenshot → `OcrResponse` |
| POST | `/reconciliation/detect-transaction` | ✅ | Keyword + regex từ text |
| DELETE | `/reconciliation/cache/{session_id}` | ✅ | Reset session |
| POST | `/reconciliation/perceive` | ⏳ | YOLO + OCR + layout (thay/thêm ocr) |
| POST | `/reconciliation/plan` | ⏳ | Input snapshot → `AgentAction` |
| POST | `/reconciliation/analyze` | ⏳ | Batch giao dịch → tổng hợp LLM |

---

## 7. JSON — Perception snapshot

Mẫu tham chiếu: **`yolo.json`** (bbox normalized 0–1).

### 7.1 Perception response (mục tiêu)

```json
{
  "session_id": "uuid",
  "app_type": "zalo_pc",
  "chat_detected": true,
  "screen": {
    "width": 1920,
    "height": 1080,
    "capture_offset": { "x": 100, "y": 150 }
  },
  "chat_region": {
    "x": 0.19,
    "y": 0.06,
    "w": 0.62,
    "h": 0.85
  },
  "messages": [
    {
      "id": "msg_a1b2",
      "role": "user",
      "type": "text",
      "text": "Anh vừa chuyển khoản 500k",
      "time": "09:18",
      "date": "2026-05-19",
      "bbox": { "x": 0.25, "y": 0.4, "w": 0.35, "h": 0.08 }
    },
    {
      "id": "msg_c3d4",
      "role": "other",
      "type": "transaction_image",
      "text": "",
      "bbox": { "x": 0.22, "y": 0.5, "w": 0.4, "h": 0.25 },
      "image_path": "exports/sessions/{session_id}/msg_c3d4.jpg"
    },
    {
      "id": "msg_sum01",
      "role": "other",
      "type": "transaction_summary",
      "text": "Tổng hợp GD 19/05:\n1. 500,000đ VCB FT001\n2. 1,200,000đ MB FT002",
      "time": "08:00",
      "bbox": { "x": 0.22, "y": 0.3, "w": 0.45, "h": 0.15 }
    }
  ],
  "sidebar": [
    {
      "id": "chat_001",
      "name": "Thanh Mai",
      "selected": true,
      "bbox": { "x": 0.02, "y": 0.12, "w": 0.16, "h": 0.06 }
    }
  ],
  "state": "reading_history",
  "processed": {
    "message_ids": [],
    "chat_ids": []
  },
  "stop_date": "2026-05-01"
}
```

### 7.2 OcrResponse hiện tại (pixel)

Backend trả tọa độ **pixel** — `backend/reconciliation/models.py`:

```json
{
  "session_id": "...",
  "chat_region": { "x": 310, "y": 0, "width": 900, "height": 850 },
  "messages": [
    {
      "id": "msg_xxx",
      "x": 350, "y": 220, "width": 700, "height": 120,
      "type": "text",
      "date": "2026-05-19",
      "text": "..."
    }
  ],
  "sidebar": [
    { "name": "Thanh Mai", "x": 10, "y": 120, "width": 180, "height": 40 }
  ]
}
```

**Migration:** Chuẩn hóa dần sang bbox normalized trong API; app convert sang screen khi click.

---

## 8. AI Planner — AgentAction

### 8.1 Request `POST /reconciliation/plan`

```json
{
  "session_id": "uuid",
  "snapshot": { "...": "Perception JSON §7.1" },
  "goal": "read_until_stop_date",
  "stop_date": "2026-05-01"
}
```

### 8.2 Response

```json
{
  "action": "scroll",
  "params": {
    "direction": "up",
    "amount": 3
  },
  "confidence": 0.92,
  "reason": "Chưa thấy tin trước stop_date; còn vùng trống phía trên"
}
```

### 8.3 Bảng action

| action | params | Mô tả |
|--------|--------|--------|
| `scroll` | `direction`, `amount` | Cuộn lịch sử |
| `click` | `bbox_ref` hoặc `x`, `y` | Click tọa độ (ưu tiên bbox_ref) |
| `open_chat` | `sidebar_index` hoặc `chat_id` | Mở hội thoại sidebar |
| `stop_inner` | — | Kết thúc đọc chat hiện tại |
| `stop_outer` | — | Kết thúc toàn phiên |
| `wait` | `ms` | Đợi UI load |

### 8.4 Rule planner (ưu tiên trước LLM)

```text
IF không message mới sau 2 scroll → stop_inner
IF message.date <= stop_date → stop_inner
IF sidebar có item chưa processed → open_chat(index)
ELSE → scroll up (default amount từ config)
```

LLM chỉ gọi khi: sidebar trùng tên, layout lạ, `chat_detected=false`, hoặc rule trả `confidence < threshold`.

---

## 9. State machine (FSM)

```text
                    ┌─────────┐
                    │  IDLE   │
                    └────┬────┘
                         │ start
                         ▼
                    ┌─────────┐
         ┌─────────│ CAPTURE │◄────────┐
         │         └────┬────┘         │
         │              ▼              │
         │         ┌─────────┐         │
         │         │ PERCEIVE│         │
         │         └────┬────┘         │
         │              ▼              │
         │         ┌─────────┐         │
         │         │  PLAN   │         │
         │         └────┬────┘         │
         │              ▼              │
         │    ┌─────────────────┐    │
         │    │      ACT        │────┘ scroll / wait
         │    └────────┬────────┘
         │              │ open_chat
         │              ▼
         │    ┌─────────────────┐
         │    │  NEXT_CHAT      │──► reset cache → CAPTURE
         │    └────────┬────────┘
         │              │ stop_outer
         ▼              ▼
                    ┌─────────┐
                    │  DONE   │
                    └─────────┘
```

**Trạng thái lưu trong `ReconciliationState`:** `session_id`, `processed_messages`, `processed_chat_ids`, `capture_offset`, `stop_date`, `no_new_count`, `running`.

---

## 10. Phát hiện & lưu giao dịch

### 10.1 Nguồn dữ liệu — Zalo & Messenger

Trên **Zalo PC**, **Zalo Web** và **Messenger**, cùng một hội thoại thường có **hai dạng tin** chứa thông tin chuyển khoản. Hệ thống **bắt buộc trích xuất và lưu từ cả hai**, không ưu tiên loại trừ loại kia.

| Nguồn | `source_type` | Mô tả | Ví dụ điển hình |
|-------|---------------|--------|-----------------|
| **A — Tin tổng hợp giao dịch** | `summary_text` | Một bubble **text** liệt kê nhiều GD hoặc báo CK gọn (có thể nhiều dòng) | Zalo: *"Tổng hợp giao dịch ngày 19/05…"*, list số tiền + nội dung; Messenger: tin dài có nhiều dòng amount |
| **B — Ảnh chụp chuyển khoản** | `transfer_image` | Ảnh bill app ngân hàng / screenshot màn hình CK | User gửi ảnh VCB, MB, Napas; Zalo/Messenger hiển thị thumbnail trong bubble |

```text
Hội thoại chat
    │
    ├── [A] summary_text     → OCR bubble → parse nhiều dòng → N bản ghi Transaction
    │
    └── [B] transfer_image   → YOLO crop → OCR ảnh → 1 bản ghi Transaction / ảnh
```

**Lưu ý nghiệp vụ:**

- Cùng một khoản CK có thể xuất hiện **cả** tin tổng hợp **và** ảnh bill → cần `dedupe_key` / `linked_message_ids` để đối soát, không ghi trùng nếu khớp mã FT + số tiền + thời gian.
- Tin tổng hợp có thể chứa **1 hoặc nhiều** giao dịch trong một `message_id` → tách thành nhiều dòng trong danh sách, cùng `parent_message_id`.

### 10.2 Loại tin nhắn & nhận diện

| `message.type` | Nguồn | Nhận diện (mục tiêu) | Pipeline |
|----------------|-------|----------------------|----------|
| `text` | A (nếu khớp pattern tổng hợp) | Keyword: *tổng hợp*, *danh sách giao dịch*, *báo cáo*, nhiều dòng `\d+.*đ` / FT | `parse_summary_message()` |
| `text` | A (tin CK đơn lẻ) | Một GD trong một bubble | `detect_transaction()` hiện tại |
| `transaction_summary` | A (chuyên biệt) | YOLO class hoặc rule: bubble cao, ≥2 dòng amount | LLM / rule split dòng |
| `transaction_image` | B | YOLO `transfer_image` hoặc tỷ lệ ảnh lớn, ít text | OCR Paddle trên crop |

**Zalo vs Messenger (khác biệt UI, cùng schema đầu ra):**

| Đặc điểm | Zalo PC / Web | Messenger |
|----------|---------------|-----------|
| Tin tổng hợp | Hay có tiêu đề + bảng số tiền theo dòng | Thường plain text, ít format |
| Ảnh CK | Thumbnail trong bubble, có thể kèm caption ngắn | Tương tự; có thể có reaction |
| `app_type` trong record | `zalo_pc` / `zalo_web` | `messenger_web` / `messenger_desktop` |

### 10.3 Trích xuất theo từng nguồn

#### Nguồn A — Tin tổng hợp (`summary_text`)

```text
OCR toàn bubble (EasyOCR)
    ↓
Phân loại: summary vs tin CK đơn
    ↓
Tách dòng (regex + LLM fallback):
    - mỗi dòng: time?, amount, content, mã FT?, ngân hàng?
    ↓
Sinh 1 TransactionRecord / dòng hợp lệ
    ↓
source_type = summary_text
raw_text = nguyên văn bubble
```

**Pattern gợi ý (rule):** nhiều dòng khớp amount; từ khóa *tổng hợp*, *giao dịch*, *đã nhận*, *đã chuyển*; danh sách đánh số `1.` `2.`.

#### Nguồn B — Ảnh chuyển khoản (`transfer_image`)

```text
YOLO transfer_image → crop
    ↓
Lưu ảnh gốc crop → transfer_image_path
    ↓
OCR ảnh (PaddleOCR khuyến nghị)
    ↓
Trích: amount, bank, transaction_code, account, beneficiary, transfer_time
    ↓
source_type = transfer_image
```

**Caption text** (nếu có dưới ảnh): merge vào `content`, không thay OCR ảnh.

### 10.4 Danh sách giao dịch — các trường bắt buộc

Mỗi **một dòng giao dịch** trong `transactions.json` / CSV / báo cáo đối soát dùng chung schema `TransactionRecord`.

#### Bảng trường đầy đủ

| Trường | Kiểu | Bắt buộc | Mô tả |
|--------|------|----------|--------|
| `id` | string | ✅ | ID duy nhất toàn phiên, VD: `tx_20260520_001` |
| `session_id` | string | ✅ | Phiên đối soát |
| `app_type` | string | ✅ | `zalo_pc` \| `zalo_web` \| `messenger_web` \| `messenger_desktop` |
| `chat_id` | string | ✅ | ID hội thoại (sidebar / hash tên) |
| `chat_name` | string | ✅ | Tên nhóm / người chat |
| `message_id` | string | ✅ | ID bubble chứa nguồn (ảnh hoặc tin tổng hợp) |
| `parent_message_id` | string | | Bubble gốc nếu tách từ tin tổng hợp ( = `message_id` nếu 1-1) |
| `line_index` | int | | Thứ tự dòng trong tin tổng hợp (0, 1, 2…) — null nếu ảnh CK |
| `source_type` | string | ✅ | `summary_text` \| `transfer_image` \| `single_text` (tin CK một dòng) |
| `transaction_date` | string | | Ngày GD `YYYY-MM-DD` (từ bubble / OCR ảnh) |
| `transaction_time` | string | | Giờ `HH:MM` hoặc `YYYY-MM-DD HH:MM:SS` |
| `sender` | string | | Người gửi tin (đối soát nhóm) |
| `direction` | string | | `incoming` \| `outgoing` \| `unknown` (nhận / chuyển) |
| `amount` | string | ✅ | Số tiền chuẩn hóa, VD: `500000` hoặc `500,000đ` |
| `currency` | string | | Mặc định `VND` |
| `bank` | string | | Mã / tên NH: VCB, MB, TCB, … |
| `transaction_code` | string | | Mã FT, ref, mã GD app NH |
| `account_number` | string | | STK hiển thị trên bill (nếu có) |
| `beneficiary` | string | | Tên người nhận / gửi trên bill |
| `content` | string | | Nội dung CK / memo / dòng tổng hợp |
| `raw_text` | string | | OCR nguyên văn bubble hoặc ảnh (debug) |
| `confidence` | float | | 0–1 độ tin cậy trích xuất |
| `screenshot_path` | string | | Ảnh màn hình full lúc capture |
| `transfer_image_path` | string | | Đường dẫn crop ảnh CK — **chỉ** `source_type=transfer_image` |
| `summary_excerpt` | string | | Đoạn trích tin tổng hợp — **chỉ** `source_type=summary_text` |
| `dedupe_key` | string | | Hash(amount + code + date + chat) để gộp trùng A↔B |
| `linked_record_ids` | string[] | | ID bản ghi khác cùng một khoản (ảnh ↔ dòng tổng hợp) |
| `is_duplicate` | bool | | Đã match với bản ghi khác nguồn |
| `status` | string | | `extracted` \| `needs_review` \| `confirmed` |
| `created_at` | string | | ISO timestamp lúc hệ thống ghi nhận |

#### CSV export (mở rộng từ hiện tại)

**Hiện tại (✅):**

```text
time,sender,amount,bank,transaction_code,content
```

**Mục tiêu (⏳) — khớp schema trên:**

```text
id,session_id,app_type,chat_name,message_id,source_type,transaction_date,transaction_time,sender,direction,amount,currency,bank,transaction_code,account_number,beneficiary,content,transfer_image_path,summary_excerpt,dedupe_key,status
```

#### Ví dụ JSON — cùng hội thoại, hai nguồn

```json
{
  "transactions": [
    {
      "id": "tx_001",
      "session_id": "abc-123",
      "app_type": "zalo_pc",
      "chat_id": "chat_thanh_mai",
      "chat_name": "Thanh Mai",
      "message_id": "msg_summary_01",
      "parent_message_id": "msg_summary_01",
      "line_index": 0,
      "source_type": "summary_text",
      "transaction_date": "2026-05-19",
      "transaction_time": "09:15",
      "sender": "Thanh Mai",
      "direction": "incoming",
      "amount": "500000",
      "currency": "VND",
      "bank": "VCB",
      "transaction_code": "FT240519001",
      "content": "CK đơn hàng #1024",
      "raw_text": "1. 500,000đ - VCB FT240519001 - CK đơn hàng #1024",
      "summary_excerpt": "Tổng hợp GD 19/05: 1. 500,000đ...",
      "transfer_image_path": null,
      "dedupe_key": "vcb|500000|FT240519001|2026-05-19",
      "linked_record_ids": ["tx_002"],
      "is_duplicate": false,
      "status": "extracted"
    },
    {
      "id": "tx_002",
      "session_id": "abc-123",
      "app_type": "zalo_pc",
      "chat_id": "chat_thanh_mai",
      "chat_name": "Thanh Mai",
      "message_id": "msg_img_02",
      "source_type": "transfer_image",
      "transaction_date": "2026-05-19",
      "transaction_time": "09:18",
      "sender": "Thanh Mai",
      "direction": "incoming",
      "amount": "500000",
      "currency": "VND",
      "bank": "VCB",
      "transaction_code": "FT240519001",
      "beneficiary": "CONG TY ABC",
      "content": "",
      "raw_text": "VIETCOMBANK ... FT240519001 ... 500,000 VND",
      "transfer_image_path": "exports/sessions/abc-123/screenshots/msg_img_02.jpg",
      "summary_excerpt": null,
      "dedupe_key": "vcb|500000|FT240519001|2026-05-19",
      "linked_record_ids": ["tx_001"],
      "is_duplicate": true,
      "status": "confirmed"
    }
  ]
}
```

### 10.5 Detect transaction — rule (tin text đơn / dòng tổng hợp)

**Keyword:** ck, chuyển khoản, đã ck, chuyển tiền, vietcombank, mbbank, napas, bill, tổng hợp, giao dịch

**Regex:**

| Loại | Pattern |
|------|---------|
| Amount | `\d{1,3}(,\d{3})*(\s?(đ\|k\|tr\|vnd))?` |
| Mã GD | `FT\d+` |
| Tài khoản | `\d{8,16}` |

File: `backend/reconciliation/transaction_detector.py` — mở rộng: `parse_summary_lines(text) -> list[TransactionRecord]`.

### 10.6 Ảnh chuyển khoản (nguồn B)

1. YOLO class `transfer_image` → crop
2. OCR riêng trên crop (PaddleOCR khuyến nghị)
3. Lưu file: `exports/sessions/{session_id}/screenshots/{message_id}.jpg`
4. Điền đủ trường §10.4; `source_type = transfer_image`

### 10.7 Lưu trữ

| Định dạng | Nội dung |
|-----------|----------|
| `transactions_{timestamp}.csv` | ✅ Đang có — sẽ mở rộng cột theo §10.4 |
| `transactions.json` | ⏳ Mảng `TransactionRecord` đầy đủ trường |
| `exports/sessions/{session_id}/` | ⏳ `screenshots/`, `summaries/` (optional cache text tổng hợp) |

### 10.8 AI phân tích & đối soát `POST /reconciliation/analyze`

**Input:** toàn bộ `TransactionRecord` trong phiên (cả `summary_text` và `transfer_image`).

**Output:**

- Danh sách giao dịch **đã gộp** (ưu tiên ảnh khi trùng `dedupe_key`)
- Cảnh báo: chỉ có tổng hợp chưa có ảnh, chỉ có ảnh chưa có dòng tổng hợp
- Tóm tắt tiếng Việt cho kế toán

Dùng Ollama (`gemma4:e2b`) + prompt JSON schema §10.4.

---

## 11. RAM CACHE

### 11.1 Mục tiêu

- Tránh OCR trùng ảnh (hash)
- Theo dõi message/chat đã xử lý
- Reset khi chuyển hội thoại (OUTER)

### 11.2 Cấu trúc

```python
chat_cache = {
    session_id: {
        "processed_messages": set(),
        "processed_chat_ids": set(),
        "image_hashes": [],
        "last_scroll_y": 0,
        "last_message_id": None,
    }
}
```

File: `backend/reconciliation/cache.py` — có thể nâng Redis sau.

---

## 12. Pseudo code — FULL SYSTEM

```python
def run_full_session(stop_date: str, max_chats: int):
    init_storage()
    state = ReconciliationState(stop_date=stop_date)

    for chat in outer_iterator(state):  # sidebar chưa processed
        reset_cache(state.session_id)
        state.processed_messages.clear()

        while state.running:
            img = capture_window(state.capture_target)
            snapshot = post_perceive(img, state.session_id)
            action = post_plan(snapshot, state)

            if action.type == "stop_outer":
                return
            if action.type == "stop_inner":
                break

            for msg in new_messages(snapshot, state):
                if msg.type == "transaction_image":
                    records = extract_from_transfer_image(msg)
                elif msg.type in ("transaction_summary", "text") and is_summary(msg):
                    records = parse_summary_message(msg)  # nhiều dòng → nhiều record
                else:
                    records = [detect_transaction(msg)] if detect_transaction(msg) else []
                for tx in records:
                    save_transaction(tx, msg)  # source_type: transfer_image | summary_text | single_text

                if should_stop_inner(msg, stop_date):
                    break

            execute_action(action, snapshot, state.capture_offset)

            if inner_should_stop(state):
                break

        mark_chat_processed(chat)
```

---

## 13. Tối ưu hiệu năng

| Kỹ thuật | Mô tả |
|----------|--------|
| OCR theo crop | Chỉ vùng YOLO detect, không full màn hình |
| Hash cache | `_ocr_hash_cache` — reuse kết quả cùng ảnh |
| Dedupe message | `processed_messages` + overlap khi scroll |
| Planner throttle | Gọi LLM mỗi N vòng hoặc khi state đổi |
| Multi-thread (tùy chọn) | Capture ‖ upload ‖ detect ‖ export |

---

## 14. Stack khuyến nghị

| Thành phần | Công nghệ | Ghi chú |
|------------|-----------|---------|
| Win App | Python + PySide6 | `app/` |
| Backend | FastAPI | `backend/` |
| UI detection | YOLOv8/v11 + CV fallback | `backend/reconciliation/vision/yolo_layout.py` |
| OCR chat | EasyOCR | Đang dùng |
| OCR bill | PaddleOCR | Planned |
| LLM local | Ollama `gemma4:e2b` | Chat + plan + analyze |
| Automation | pynput | `app/logic/reconciliation/mouse_control.py` |
| Capture | dxcam + PrintWindow | `app/logic/reconciliation/screenshot.py` |
| Cache | RAM → Redis | Tùy scale |
| Export | CSV + JSON + files | `exports/` |

---

## 15. Lộ trình triển khai (UPDATE)

| Phase | Nội dung | Ước lượng |
|-------|----------|-----------|
| **1 — Perception** | YOLO inference, layout builder, OCR crop; chuẩn hóa JSON | 2–3 tuần |
| **2 — Planner** | FSM refactor, `POST /reconciliation/plan`, rule + LLM | 1–2 tuần |
| **3 — Actuator** | `execute_action`, click theo bbox/sidebar thật | 1 tuần |
| **4 — Persistence** | Schema §10.4, ảnh CK + parse tin tổng hợp, dedupe, `/analyze` | 1–2 tuần |

---

## 16. Workflow hoàn chỉnh (tóm tắt)

```text
[Mở app chat]
    ↓
OUTER: chọn hội thoại (click sidebar / planner)
    ↓
INNER:
    Capture → Perceive (YOLO+OCR) → Plan → Act
    → Detect & lưu giao dịch (tin tổng hợp + ảnh CK)
    → Scroll … cho đến stop
    ↓
OUTER: chat tiếp theo
    ↓
Analyze (tổng hợp JSON) → báo cáo / CSV / JSON
```

---

## 17. Tham chiếu file trong repo

| File | Vai trò |
|------|---------|
| `markdown.md` | Spec này |
| `yolo.json` | Mẫu Perception JSON (normalized bbox) |
| `PROJECT_STRUCTURE.md` | Cây thư mục + API đã triển khai |
| `app/logic/reconciliation/orchestrator.py` | INNER/OUTER loop |
| `app/logic/reconciliation/screenshot.py` | Chụp cửa sổ / vùng chat |
| `app/logic/reconciliation/mouse_control.py` | Scroll, click, focus |
| `app/ui/reconciliation/reconciliation_widget.py` | Tab Đối soát (PySide6) |
| `backend/reconciliation/ocr_service.py` | Pipeline OCR |
| `backend/reconciliation/models.py` | Pydantic schemas |

---

## Lịch sử thay đổi spec

| Ngày | Thay đổi |
|------|----------|
| 2026-05-19 | Khởi tạo spec automation + INNER/OUTER |
| 2026-05-20 | Bổ sung YOLO, layout, FSM, AI planner, JSON yolo.json, trạng thái triển khai, lộ trình UPDATE |
| 2026-05-20 | §10: hai nguồn Zalo/Messenger (summary_text + transfer_image), schema TransactionRecord đầy đủ |
