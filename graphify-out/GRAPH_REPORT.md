# Graph Report - .  (2026-05-22)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 742 nodes · 1305 edges · 65 communities (40 shown, 25 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 234 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 60|Community 60]]

## God Nodes (most connected - your core abstractions)
1. `ReconciliationOrchestrator` - 45 edges
2. `AmiWindow` - 17 edges
3. `MessagesListDialog` - 16 edges
4. `yolo_layout()` - 15 edges
5. `CaptureError` - 14 edges
6. `ocr_messages()` - 14 edges
7. `ChatPage` - 13 edges
8. `post_json()` - 13 edges
9. `ImageViewerDialog` - 12 edges
10. `split_chat_transactions()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `rule_planner()` --calls--> `is_date_separator_text()`  [INFERRED]
  app/logic/reconciliation/planner.py → backend/reconciliation/date_separator.py
- `rule_planner()` --calls--> `resolve_chat_date_display()`  [INFERRED]
  app/logic/reconciliation/planner.py → backend/reconciliation/date_separator.py
- `rule_planner()` --calls--> `message_reached_stop_threshold()`  [INFERRED]
  app/logic/reconciliation/planner.py → backend/reconciliation/stop_datetime.py
- `is_summary_message()` --calls--> `strict_money_line_match()`  [INFERRED]
  app/logic/reconciliation/transaction_extract.py → backend/transaction_money.py
- `split_summary_lines()` --calls--> `strict_money_line_match()`  [INFERRED]
  app/logic/reconciliation/transaction_extract.py → backend/transaction_money.py

## Communities (65 total, 25 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (32): # Gửi tin nhắn ở chế độ streaming         Gọi đồng bộ — caller nên chạy hàm này, mark_transaction_messages(), AgentAction, Hành động tiếp theo: tên action + tham số (hướng scroll, index sidebar, bbox_ref, normalize_snapshot(), Orchestrator — điều phối loop-1 / loop-2 theo structure.md.  Luồng:   1) Chụp, Điều phối phiên đối soát — loop-1 / loop-2., Tương thích UI 'Chụp + Perceive' — fallback /perceive nếu chưa có /yolo. (+24 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (21): QDialog, ImageViewerDialog, JsonViewerDialog, MessagesListDialog, # Dialog preview — tab reconciliation - ImageViewerDialog: xem ảnh screenshot (, Xem OCR response (dict) ở dạng JSON pretty-print + copy + lưu., Xem OCR response (dict) ở dạng JSON pretty-print + copy + lưu., Bảng tổng hợp tin nhắn: phiên hiện tại, phiên đã lưu, hoặc tất cả phiên. (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.10
Nodes (30): _bubble_y(), build_chat_sessions(), _dominant_role(), _marker_id(), Gom bubble OCR thành lượt chat (session) giữa các mốc ngày/giờ.  Mỗi session =, Từ danh sách bubble (đã sort theo Y), tạo dict session_id → entry chat_session., _session_date(), _session_id() (+22 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (31): bbox_center_screen(), _bbox_dims(), bbox_to_pixels(), chat_region_layout(), _chat_region_pixels(), chat_scroll_clicks(), chat_scroll_focus_screen(), is_normalized_bbox() (+23 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (29): chat_completion(), _ollama_url(), OllamaError, # Client gọi Ollama (model gemma4:e2b) Hỗ trợ chat completion thường + streamin, # Gọi Ollama chat API (non-stream), trả nội dung assistant, # Gọi Ollama chat API ở chế độ streaming     Yield từng đoạn text (chunk) khi O, build_messages(), build_ollama_payload() (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (28): detect_transaction_api(), parse_summary_api(), find_transaction_money(), Nhận diện số tiền giao dịch hợp lệ (VN) — tránh báo sai cảnh hội thoại thường., Trả match đầu tiên theo độ ưu tiên; None nếu không có mẫu tiền hợp lệ., Dùng cho tin tổng hợp nhiều dòng: dòng có mẫu tiền rõ ràng., strict_money_line_match(), _detect_bank() (+20 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (30): YOLO/CV phân tích bố cục màn hình — cache layout, trả chat_region + sidebar., yolo_layout(), LayoutRatios, Dataclass tỉ lệ layout — tránh circular import giữa layout_regions và vision., apply_env_overrides(), compute_layout(), _env_float_optional(), Tính vùng sidebar / chat cho pipeline OCR reconciliation. Tỉ lệ lấy từ cache (Y (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (14): ChatLogic, # Logic Module Chat — gọi backend, giữ lịch sử hội thoại, Xử lý chat qua backend (prompt + Ollama)., # Gửi tin nhắn → nhận reply tiếng Việt từ backend (non-stream), Gửi tin nhắn, trả (ok, text)., ChatPage, ChatStreamWorker, _on_done() (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (27): capture_chat_region(), capture_full_screen(), _capture_region(), capture_window(), CaptureInfo, chat_region_screen_rect(), _ensure_windows_dpi_awareness(), _focus_window() (+19 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (23): split_transactions_api(), append_transaction_record(), append_transactions_csv(), init_csv_file(), init_json_file(), Ghi dữ liệu giao dịch ra CSV (Excel-friendly, UTF-8 BOM) và transactions.json., Tạo file CSV với header nếu chưa tồn tại (idempotent khi đã có file)., Khởi tạo JSON rỗng { \"transactions\": [] } nếu chưa có. (+15 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (8): QWidget, _coords_from_result(), _on_perceive(), _on_worker_done(), UI Reconciliation — date picker, chế độ quét, nút Chạy/Dừng., Tab Đối soát — loop-1/loop-2 + export., ReconciliationWorker, run()

### Community 11 - "Community 11"
Cohesion: 0.14
Nodes (22): is_date_separator_centered(), Mốc ngày thường canh giữa khung chat., _cluster_dets(), _Det, _extract_date(), _get_reader(), _infer_role_from_position(), _is_zalo_hd_badge() (+14 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (18): QFrame, add_labeled_stop_date(), apply_qss(), Card, load_qss(), make_hline(), make_stop_date_edit(), make_vline() (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.19
Nodes (21): segment_queue_activate(), SplitTransactionsRequest, activate_queue(), deactivate_queue(), drain_finished(), enqueue_segment(), _ensure_worker(), _get_queue() (+13 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (20): BaseModel, AgentActionResponse, AnalyzeRequest, AnalyzeResponse, AnalyzeWarning, CaptureOffset, ChatSegmentInfo, LlmSplitResult (+12 more)

### Community 15 - "Community 15"
Cohesion: 0.16
Nodes (8): main(), Win App — Entry point (PySide6) Chạy: python -m app.main, QMainWindow, AmiWindow, _enable_windows_dpi_awareness(), _escape(), Main window — Sidebar | Stack module | SystemLog, run_app()

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (16): _bubble_sort_y(), _bubbles_for_chat(), catalog_to_list(), ingest_snapshot(), list_session_ids(), load_all_sessions_messages(), load_session_messages(), messages_file() (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.12
Nodes (15): clear_cache(), ocr_screenshot(), API Reconciliation — /yolo, /ocr, /plan + endpoints tương thích., OCR — cropped=True khi ảnh đã là vùng chat (loop-2)., _read_upload(), segment_queue_drain(), segment_queue_enqueue(), segment_queue_status() (+7 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (11): Enum, FsmState, Dataclass cho module Reconciliation — markdown.md §8–10.  - FsmState: trạng th, Payload gửi POST /reconciliation/analyze và ghi transactions.json., Schema §10.4 — một dòng giao dịch., Trạng thái chạy một phiên: UUID session, chat hiện tại, offset/size ảnh capture,, Các phase chính của vòng đối soát (inner/outer)., Một giao dịch đã parse: nguồn summary / ảnh CK / tin đơn; có dedupe_key để gộp t (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.17
Nodes (13): list_processed(), plan_action(), cache_stats(), get_session(), RAM cache phiên đối soát — markdown.md §11., reset_session(), SessionCache, CachedLayoutEntry (+5 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (15): add_labeled_stop_date(), apply_qss(), load_qss(), make_hline(), make_stop_date_edit(), make_vline(), _parse_default_stop_datetime(), # Widget tiện ích dùng chung cho Win App (PySide6) - StyleLoader: load các file (+7 more)

### Community 21 - "Community 21"
Cohesion: 0.21
Nodes (14): main(), _parse_args(), _py_filter(), # Auto-reload supervisor cho Win App Mô phỏng `uvicorn --reload`: spawn `python, Chạy app 1 lần, không reload — return exit code., Khởi chạy Win App như 1 subprocess (kế thừa stdout/stderr của parent)., Dừng subprocess (terminate → kill nếu quá hạn)., Chỉ phản ứng với file .py thật, bỏ qua cache. (+6 more)

### Community 22 - "Community 22"
Cohesion: 0.21
Nodes (11): perceive_screenshot(), Tương thích cũ: YOLO layout (cache) + OCR full → Perception JSON., NormalizedBBox, PerceptionMessage, PerceptionSidebarItem, ScreenInfo, _infer_message_type(), pixel_to_perception() (+3 more)

### Community 23 - "Community 23"
Cohesion: 0.25
Nodes (7): QLabel, Badge, FormField, Label nhỏ ở trên + widget ở dưới (vd cho Entry)., Chấm tròn 10x10 màu xanh (ok) hoặc đỏ (lỗi)., Pill label. variant ∈ {ok, error, warn, info, primary, muted}., StatusDot

### Community 24 - "Community 24"
Cohesion: 0.20
Nodes (9): app_type, chat_detected, chat_region, h, w, x, y, messages (+1 more)

### Community 25 - "Community 25"
Cohesion: 0.24
Nodes (6): Badge, FormField, Label nhỏ ở trên + widget ở dưới (vd cho Entry)., Chấm tròn 10x10 màu xanh (ok) hoặc đỏ (lỗi)., Pill label. variant ∈ {ok, error, warn, info, primary, muted}., StatusDot

### Community 26 - "Community 26"
Cohesion: 0.33
Nodes (3): MessageBubble, 1 message trong chat. role ∈ {user, ai, system, error, thinking}., Đổi role (vd: thinking → ai khi nhận chunk đầu).

### Community 27 - "Community 27"
Cohesion: 0.33
Nodes (3): MessageBubble, 1 message trong chat. role ∈ {user, ai, system, error, thinking}., Đổi role (vd: thinking → ai khi nhận chunk đầu).

### Community 28 - "Community 28"
Cohesion: 0.33
Nodes (6): ChatRegion, OcrPixelResponse, _image_hash(), process_screenshot(), OCR pixel pipeline — EasyOCR (backend.reconciliation.ocr_engine)., RuntimeError

### Community 29 - "Community 29"
Cohesion: 0.40
Nodes (3): lifespan(), # Backend FastAPI — Entry point Chạy: uvicorn backend.main:app --reload --host, Khởi động/tắt backend — plan worker kích hoạt theo phiên qua API.

### Community 31 - "Community 31"
Cohesion: 0.40
Nodes (5): QPushButton, NavButton, Nút điều hướng sidebar, hỗ trợ trạng thái 'checked' (active)., NavButton, Nút điều hướng sidebar, hỗ trợ trạng thái 'checked' (active).

### Community 33 - "Community 33"
Cohesion: 0.50
Nodes (3): Worker nền — xử lý hàng đợi đoạn chat (Ollama tách giao dịch) không chặn loop OC, Tắt worker khi phiên kết thúc., stop_session_worker()

## Knowledge Gaps
- **12 isolated node(s):** `app_type`, `chat_detected`, `x`, `y`, `w` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ReconciliationOrchestrator` connect `Community 0` to `Community 3`, `Community 5`, `Community 10`, `Community 16`, `Community 18`?**
  _High betweenness centrality (0.251) - this node is a cross-community bridge._
- **Why does `ocr_messages()` connect `Community 11` to `Community 10`, `Community 2`, `Community 28`, `Community 14`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `detect_transaction_api()` connect `Community 5` to `Community 0`, `Community 17`, `Community 14`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `ReconciliationOrchestrator` (e.g. with `FsmState` and `AgentAction`) actually correct?**
  _`ReconciliationOrchestrator` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `str` (e.g. with `_spawn()` and `_relpath()`) actually correct?**
  _`str` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `AmiWindow` (e.g. with `StatusDot` and `NavButton`) actually correct?**
  _`AmiWindow` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `MessagesListDialog` (e.g. with `ReconciliationWorker` and `reconciliation_widget.py`) actually correct?**
  _`MessagesListDialog` has 2 INFERRED edges - model-reasoned connections that need verification._