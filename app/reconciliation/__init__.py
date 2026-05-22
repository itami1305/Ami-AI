"""
Module Reconciliation — đối soát giao dịch qua chat (Zalo/Messenger).

Luồng tổng quát (theo markdown.md §4, §7–§12):
    OUTER: duyệt từng hội thoại trong sidebar → INNER.
    INNER: CAPTURE ảnh cửa sổ → PERCEIVE (OCR/backend) → PLAN (AI hoặc rule) → ACT (scroll/click).

Thành phần:
    - logic.ReconciliationLogic: FSM điều phối vòng lặp + gọi API /reconciliation/*.
    - ui: tab PySide6 (worker thread, không block UI).
    - models: ReconciliationState, TransactionRecord, AgentAction, FsmState.
    - transaction_extract: nhận diện tin tổng hợp / ảnh CK → TransactionRecord.
    - message_store: catalog tin nhắn → messages.json.
    - csv_export: transactions.csv + transactions.json.
    - planner: fallback khi API plan không dùng được hoặc confidence thấp.
    - bbox, automation: chuyển bbox → click (pynput trong module này).
    - capture: chụp cửa sổ Zalo/Chrome.
    - dialogs: preview ảnh / JSON / danh tin.
    - paths: exports/reconciliation/sessions/{session_id}/.

API backend: prefix /reconciliation/*.
"""
