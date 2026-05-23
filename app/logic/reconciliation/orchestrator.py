"""
Orchestrator — điều phối loop-1 / loop-2 theo structure.md.

Luồng:
  1) Chụp full → POST /yolo → cache layout (1 lần / phiên)
  2) loop-1 (OUTER): chọn chat sidebar → loop-2
  3) loop-2 (INNER): chụp vùng chat → POST /ocr (cropped) → kiểm tra ngày → cuộn
  4) Plan worker nền: tách giao dịch qua segment-queue (không chặn OCR)
"""

from __future__ import annotations

import json
import uuid
from typing import Callable

import time

from app.logic.api_client import ApiError, delete, get_json, post_json, post_multipart
from app.logic.reconciliation.bbox import bbox_center_screen, bbox_to_pixels, item_to_bbox
from app.logic.reconciliation.csv_export import (
    _existing_transaction_codes,
    append_transaction_record,
    init_csv_file,
    init_json_file,
)
from app.logic.reconciliation.date_filter import message_reached_stop_threshold
from app.logic.reconciliation.message_store import (
    catalog_to_list,
    ingest_snapshot,
    load_all_sessions_messages,
    load_session_messages,
    mark_transaction_messages,
    persist_messages,
)
from app.logic.reconciliation.models import AgentAction, FsmState, ReconciliationState, TransactionRecord
from app.logic.reconciliation.mouse_control import click_at, click_next_chat, execute_action, focus_chat_center
from app.logic.reconciliation.planner import rule_planner
from app.logic.reconciliation.screenshot import (
    CaptureError,
    capture_chat_region,
    capture_window,
    infer_layout_app_type,
)
from app.logic.reconciliation.transaction_extract import (
    is_summary_message,
    new_tx_id,
    records_from_detect,
    records_from_transaction_results,
    records_from_parse_summary,
    records_from_split_response,
)
from backend.reconciliation.transfer_receipt import (
    is_multi_transaction_segment,
    is_transfer_receipt_text,
    parse_transfer_receipts,
)

PLAN_CONFIDENCE_THRESHOLD = 0.75


def _sidebar_chat_id(item: dict, index: int) -> str:
    return str(item.get("id") or item.get("name") or f"chat_{index}")


def normalize_snapshot(ocr_result: dict, state: ReconciliationState) -> dict:
    """Đưa kết quả OCR/YOLO về schema snapshot thống nhất."""
    if ocr_result.get("screen") and ocr_result.get("messages"):
        snap = dict(ocr_result)
        snap.setdefault("session_id", state.session_id)
        snap.setdefault("app_type", state.app_type)
        snap.setdefault(
            "processed",
            {
                "message_ids": list(state.processed_messages),
                "chat_ids": list(state.processed_chat_ids),
            },
        )
        snap.setdefault("stop_date", state.stop_date)
        return snap

    sw = state.capture_width or int(ocr_result.get("image_width") or 1)
    sh = state.capture_height or int(ocr_result.get("image_height") or 1)

    if state.yolo_layout and ocr_result.get("messages") and not ocr_result.get("sidebar"):
        cr = state.yolo_layout.get("chat_region") or {}
        crop_w = int(ocr_result.get("image_width") or 0)
        crop_h = int(ocr_result.get("image_height") or 0)
        cr_px = bbox_to_pixels(item_to_bbox(cr, sw, sh), sw, sh) if cr else (0, 0, sw, sh)
        ox, oy = cr_px[0], cr_px[1]
        messages = []
        for msg in ocr_result.get("messages") or []:
            mid = msg.get("id") or f"msg_{uuid.uuid4().hex[:8]}"
            raw = dict(msg)
            if crop_w > 0 and crop_h > 0 and (crop_w < sw or crop_h < sh):
                raw = {
                    **raw,
                    "x": int(msg.get("x", 0)) + ox,
                    "y": int(msg.get("y", 0)) + oy,
                    "width": int(msg.get("width", msg.get("w", 0))),
                    "height": int(msg.get("height", msg.get("h", 0))),
                }
            messages.append(
                {
                    "id": mid,
                    "role": msg.get("role", "other"),
                    "type": msg.get("type", "text"),
                    "text": msg.get("text", ""),
                    "time": msg.get("time", ""),
                    "date": msg.get("date"),
                    "bbox": item_to_bbox(raw, sw, sh),
                }
            )
        sidebar = state.yolo_layout.get("sidebar") or []
        return {
            "session_id": ocr_result.get("session_id", state.session_id),
            "app_type": state.app_type,
            "chat_detected": bool(messages or sidebar),
            "screen": {
                "width": sw,
                "height": sh,
                "capture_offset": {"x": state.capture_offset_x, "y": state.capture_offset_y},
            },
            "chat_region": cr,
            "cropped_ocr": crop_w > 0 and crop_h > 0 and (crop_w < sw or crop_h < sh),
            "messages": messages,
            "sidebar": sidebar,
            "state": "reading_history",
            "processed": {
                "message_ids": list(state.processed_messages),
                "chat_ids": list(state.processed_chat_ids),
            },
            "stop_date": state.stop_date,
        }

    messages = []
    for msg in ocr_result.get("messages") or []:
        mid = msg.get("id") or f"msg_{uuid.uuid4().hex[:8]}"
        messages.append(
            {
                "id": mid,
                "role": msg.get("role", "other"),
                "type": msg.get("type", "text"),
                "text": msg.get("text", ""),
                "time": msg.get("time", ""),
                "date": msg.get("date"),
                "bbox": item_to_bbox(msg, sw, sh),
            }
        )
    sidebar = []
    for i, item in enumerate(ocr_result.get("sidebar") or []):
        sidebar.append(
            {
                "id": _sidebar_chat_id(item, i),
                "name": item.get("name", ""),
                "bbox": item_to_bbox(item, sw, sh),
            }
        )
    chat_region = ocr_result.get("chat_region") or {}
    return {
        "session_id": ocr_result.get("session_id", state.session_id),
        "app_type": state.app_type,
        "chat_detected": bool(messages or sidebar),
        "screen": {
            "width": sw,
            "height": sh,
            "capture_offset": {"x": state.capture_offset_x, "y": state.capture_offset_y},
        },
        "chat_region": item_to_bbox(chat_region, sw, sh) if chat_region else {},
        "messages": messages,
        "sidebar": sidebar,
        "state": "reading_history",
        "processed": {
            "message_ids": list(state.processed_messages),
            "chat_ids": list(state.processed_chat_ids),
        },
        "stop_date": state.stop_date,
    }


class ReconciliationOrchestrator:
    """Điều phối phiên đối soát — loop-1 / loop-2."""

    def __init__(self, on_log: Callable[[str], None] | None = None) -> None:
        self._on_log = on_log or (lambda _m: None)
        self.state = ReconciliationState()

    def log(self, msg: str) -> None:
        self._on_log(msg)

    def _set_fsm(self, fsm: FsmState) -> None:
        self.state.fsm_state = fsm

    # --- API backend ---

    def upload_yolo(self, image_bytes: bytes) -> dict:
        files = {"file": ("screenshot.jpg", image_bytes, "image/jpeg")}
        data = {
            "session_id": self.state.session_id,
            "app_type": self.state.app_type,
        }
        return post_multipart("/reconciliation/yolo", files=files, data=data)

    def upload_ocr(self, image_bytes: bytes, *, cropped: bool = True) -> dict:
        files = {"file": ("chat.jpg", image_bytes, "image/jpeg")}
        data = {
            "session_id": self.state.session_id,
            "app_type": self.state.app_type,
            "cropped": "true" if cropped else "false",
        }
        return post_multipart("/reconciliation/ocr", files=files, data=data)

    def upload_perceive(self, image_bytes: bytes) -> dict:
        """Tương thích UI 'Chụp + Perceive' — fallback /perceive nếu chưa có /yolo."""
        try:
            layout = self.upload_yolo(image_bytes)
            self.state.yolo_layout = layout
            if layout.get("sidebar"):
                return normalize_snapshot(layout, self.state)
            ocr = self.upload_ocr(image_bytes, cropped=False)
            return normalize_snapshot({**layout, **ocr}, self.state)
        except ApiError:
            files = {"file": ("screenshot.jpg", image_bytes, "image/jpeg")}
            data = {
                "session_id": self.state.session_id,
                "app_type": self.state.app_type,
                "capture_offset_x": str(self.state.capture_offset_x),
                "capture_offset_y": str(self.state.capture_offset_y),
            }
            try:
                return post_multipart("/reconciliation/perceive", files=files, data=data)
            except ApiError as exc:
                if "404" not in str(exc):
                    raise
                return post_multipart("/reconciliation/ocr", files=files, data=data)

    def _activate_plan_worker(self) -> None:
        payload = {
            "session_id": self.state.session_id,
            "app_type": self.state.app_type,
            "csv_path": str(self.state.csv_path) if self.state.csv_path else None,
            "save_csv": False,
        }
        try:
            post_json("/reconciliation/segment-queue/activate", payload)
            self.log("Plan worker nền đã bật.")
        except ApiError as exc:
            self.log(f"Không bật được plan worker: {exc}")

    def _deactivate_plan_worker(self) -> None:
        try:
            post_json(f"/reconciliation/segment-queue/deactivate/{self.state.session_id}", {})
        except ApiError:
            pass

    def _get_plan_worker_status(self) -> dict:
        try:
            return get_json(f"/reconciliation/segment-queue/status/{self.state.session_id}")
        except ApiError:
            return {}

    def _wait_for_plan_worker_completion(
        self,
        *,
        poll_sec: float = 2.0,
        max_wait_sec: float = 900.0,
    ) -> None:
        """Chờ worker AI xử lý hết hàng đợi đoạn chat (giữ active, drain kết quả)."""
        deadline = time.monotonic() + max_wait_sec
        idle_rounds = 0
        while time.monotonic() < deadline:
            st = self._get_plan_worker_status()
            pending = int(st.get("pending") or 0)
            processing = st.get("processing_id")
            finished_n = int(st.get("finished_pending") or 0)

            self._drain_plan_worker()

            if pending == 0 and not processing:
                idle_rounds += 1
                if finished_n == 0 and idle_rounds >= 2:
                    return
            else:
                idle_rounds = 0
            time.sleep(poll_sec)

        self.log("Hết thời gian chờ AI — có thể còn đoạn trong hàng đợi.")

    def post_plan(self, snapshot: dict) -> AgentAction:
        payload = {
            "session_id": self.state.session_id,
            "snapshot": snapshot,
            "goal": "read_until_stop_date",
            "stop_date": self.state.stop_date,
            "no_new_count": self.state.no_new_count,
            "segment_only": self.state.segment_mode,
        }
        try:
            raw = post_json("/reconciliation/plan", payload)
            action = AgentAction(
                action=raw.get("action", "scroll"),
                params=raw.get("params") or {},
                confidence=float(raw.get("confidence", 0.5)),
                reason=raw.get("reason", ""),
            )
            if action.confidence >= PLAN_CONFIDENCE_THRESHOLD:
                return self._sanitize_segment_plan(action)
            self.log(f"Plan confidence thấp ({action.confidence:.2f}) — rule local.")
        except ApiError as exc:
            if "404" not in str(exc):
                self.log(f"Lỗi /reconciliation/plan: {exc}")
        return self._sanitize_segment_plan(rule_planner(snapshot, self.state))

    def _sanitize_segment_plan(self, action: AgentAction) -> AgentAction:
        if not self.state.segment_mode:
            return action
        if action.action == "open_chat":
            return AgentAction(
                action="scroll",
                params={"direction": "up"},
                confidence=max(action.confidence, 0.85),
                reason="Chế độ đoạn: không đổi chat — cuộn lên.",
            )
        if action.action == "stop_outer":
            return AgentAction(
                action="stop_inner",
                confidence=action.confidence,
                reason=f"Đoạn chat: {action.reason}",
            )
        return action

    def detect_transaction(self, text: str, sender: str = "", time: str = "") -> dict:
        return post_json(
            "/reconciliation/detect-transaction",
            {"text": text, "sender": sender, "time": time},
        )

    def parse_summary(self, text: str, sender: str = "", time: str = "", message_id: str = "") -> dict:
        return post_json(
            "/reconciliation/parse-summary",
            {"text": text, "sender": sender, "time": time, "message_id": message_id},
        )

    def analyze_session(self) -> dict:
        txs = [r.to_json_dict() for r in self.state.records_by_id.values()]
        return post_json(
            "/reconciliation/analyze",
            {"session_id": self.state.session_id, "transactions": txs},
        )

    def reset_cache(self) -> None:
        delete(f"/reconciliation/cache/{self.state.session_id}")

    def capture_screenshot(self) -> bytes:
        data, info = capture_window(self.state.capture_target)
        self.state.capture_offset_x = info.left
        self.state.capture_offset_y = info.top
        self.state.capture_width = info.width
        self.state.capture_height = info.height
        layout_app = infer_layout_app_type(info.title, info.target)
        self.state.layout_app_type = layout_app  # type: ignore[assignment]
        label = "Zalo PC" if info.target == "zalo" else "Google Chrome"
        method = f", {info.method}" if info.method else ""
        self.log(
            f"Đã chụp {label}: {info.title} "
            f"({info.width}×{info.height}, bỏ {info.top_skip}px header{method}, layout={layout_app})"
        )
        return data

    def capture_chat_only(self) -> bytes:
        if not self.state.yolo_layout:
            return self.capture_screenshot()
        return capture_chat_region(
            self.state.yolo_layout,
            self.state.capture_offset_x,
            self.state.capture_offset_y,
            self.state.capture_width,
            self.state.capture_height,
        )

    def _init_yolo_layout(self) -> None:
        self.log("YOLO: nhận diện bố cục màn hình...")
        screenshot = self.capture_screenshot()
        layout = self.upload_yolo(screenshot)
        self.state.yolo_layout = layout
        src = layout.get("layout_source", "?")
        cr = layout.get("chat_region") or {}
        self.log(
            f"YOLO OK ({src}) — chat_region x={cr.get('x')} y={cr.get('y')} "
            f"w={cr.get('w')} h={cr.get('h')}, sidebar={len(layout.get('sidebar') or [])} mục"
        )

    def _save_records(self, records: list[TransactionRecord]) -> None:
        json_path = self.state.json_path
        csv_path = self.state.csv_path
        if json_path is None or csv_path is None:
            return
        for record in records:
            code = (record.transaction_code or "").strip()
            if code and code in self.state.transaction_codes:
                self.log(f"Bỏ qua GD trùng mã giao dịch: {code}")
                continue

            seq = self.state.transaction_count + 1
            record.id = new_tx_id(self.state.session_id, seq)
            if record.dedupe_key and record.dedupe_key in self.state.dedupe_keys:
                record.is_duplicate = True
                existing = self._find_by_dedupe(record.dedupe_key)
                if existing:
                    record.linked_record_ids.append(existing.id)
                    existing.linked_record_ids.append(record.id)

            if not append_transaction_record(csv_path, json_path, record):
                self.log(f"Bỏ qua GD trùng mã giao dịch (JSON): {code}")
                continue
            if record.dedupe_key and not record.is_duplicate:
                self.state.dedupe_keys.add(record.dedupe_key)
            if code:
                self.state.transaction_codes.add(code)
            self.state.records_by_id[record.id] = record
            mark_transaction_messages(self.state.messages_catalog, [record.message_id])
            self.state.transaction_count += 1
            self.log(
                f"Đã lưu GD #{self.state.transaction_count} ({record.source_type}): "
                f"{record.amount} → {csv_path.name}"
            )

    def _find_by_dedupe(self, key: str) -> TransactionRecord | None:
        for rec in self.state.records_by_id.values():
            if rec.dedupe_key == key and not rec.is_duplicate:
                return rec
        return None

    def _extract_records_from_message(self, msg: dict) -> list[TransactionRecord]:
        msg_id = msg.get("id", "")
        text = (msg.get("text") or "").strip()
        msg_type = msg.get("type", "text")
        msg_date = msg.get("date") or ""
        msg_time = msg.get("time") or ""
        role = (msg.get("role") or "").strip()
        if role == "self":
            sender = "self"
        elif role == "other":
            sender = self.state.current_chat_name or "other"
        else:
            sender = role or self.state.current_chat_name or ""

        if msg_type == "chat_session":
            if not msg.get("is_transaction"):
                return []
            records: list[TransactionRecord] = []
            if is_multi_transaction_segment(text):
                parsed = parse_transfer_receipts(
                    text, sender=sender, time=msg_time or msg_date
                )
                records = records_from_transaction_results(
                    parsed,
                    sender=sender,
                    msg_date=msg_date,
                    msg_time=msg_time,
                    state=self.state,
                    message_id=msg_id,
                    source_type="bank_sms_lines",
                    raw_text=text,
                )
            elif is_transfer_receipt_text(text):
                records = records_from_detect(
                    self.detect_transaction,
                    text=text,
                    sender=sender,
                    msg_date=msg_date,
                    msg_time=msg_time,
                    state=self.state,
                    message_id=msg_id,
                    source_type="transfer_receipt_ocr",
                )
            elif is_summary_message(text):
                records = records_from_parse_summary(
                    lambda t, **kw: self.parse_summary(t, **kw),
                    text=text,
                    sender=sender,
                    msg_date=msg_date,
                    msg_time=msg_time,
                    state=self.state,
                    message_id=msg_id,
                )
            else:
                records = records_from_detect(
                    self.detect_transaction,
                    text=text,
                    sender=sender,
                    msg_date=msg_date,
                    msg_time=msg_time,
                    state=self.state,
                    message_id=msg_id,
                    source_type="llm_chat_segment",
                )

            if records:
                return records

            self.log(
                f"Enqueue AI tách GD — đoạn {msg_id} "
                f"({msg_date or msg_time or '—'}, {len(text)} ký tự)"
            )
            try:
                post_json(
                    "/reconciliation/segment-queue/enqueue",
                    {
                        "session_id": self.state.session_id,
                        "app_type": self.state.app_type,
                        "segment": {
                            "id": msg_id,
                            "text": text,
                            "date": msg_date,
                            "time": msg_time,
                            "sender": sender,
                            "role": role,
                            "chat_id": self.state.current_chat_id,
                            "chat_name": self.state.current_chat_name,
                            "marker_before": msg.get("marker_before") or "",
                            "marker_after": msg.get("marker_after") or "",
                            "member_count": int(msg.get("member_count") or 0),
                            "is_transaction": True,
                        },
                    },
                )
            except ApiError as exc:
                self.log(f"Enqueue segment lỗi: {exc}")
            return []

        if msg_type == "transaction_image":
            path = msg.get("image_path")
            if self.state.session_dir and msg_id and not path:
                path = str(self.state.session_dir / "screenshots" / f"{msg_id}.jpg")
            return records_from_detect(
                self.detect_transaction,
                text=text or "[ảnh chuyển khoản]",
                sender=sender,
                msg_date=msg_date,
                msg_time=msg_time,
                state=self.state,
                message_id=msg_id,
                source_type="transfer_image",
                transfer_image_path=path,
            )

        if msg_type == "transaction_summary" or (text and is_summary_message(text)):
            parsed = records_from_parse_summary(
                lambda t, **kw: self.parse_summary(t, **kw),
                text=text,
                sender=sender,
                msg_date=msg_date,
                msg_time=msg_time,
                state=self.state,
                message_id=msg_id,
            )
            if parsed:
                return parsed
            lines = text.splitlines() if text else []
            records: list[TransactionRecord] = []
            for idx, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                records.extend(
                    records_from_detect(
                        self.detect_transaction,
                        text=line,
                        sender=sender,
                        msg_date=msg_date,
                        msg_time=msg_time,
                        state=self.state,
                        message_id=msg_id,
                        source_type="summary_text",
                        line_index=idx,
                        summary_excerpt=text[:500],
                    )
                )
            return records

        if not text:
            return []
        return records_from_detect(
            self.detect_transaction,
            text=text,
            sender=sender,
            msg_date=msg_date,
            msg_time=msg_time,
            state=self.state,
            message_id=msg_id,
            source_type="single_text",
        )

    def _drain_plan_worker(self) -> None:
        try:
            data = post_json(f"/reconciliation/segment-queue/drain/{self.state.session_id}", {})
            for result in data.get("results") or []:
                records = records_from_split_response(result, state=self.state)
                if records:
                    self._save_records(records)
        except ApiError:
            pass

    def ingest_messages_from_snapshot(self, snapshot: dict) -> int:
        self.state.ensure_session_paths()
        added = ingest_snapshot(
            self.state.messages_catalog,
            snapshot,
            chat_id=self.state.current_chat_id,
            chat_name=self.state.current_chat_name,
            reconciliation_session_id=self.state.session_id,
            bubble_catalog=self.state.bubble_catalog,
        )
        persist_messages(self.state.session_dir, self.state.messages_catalog)
        return added

    def ingest_perceive_raw(self, raw: dict) -> int:
        snapshot = normalize_snapshot(raw, self.state)
        if not self.state.current_chat_name:
            sidebar = snapshot.get("sidebar") or []
            if sidebar:
                self.state.current_chat_name = sidebar[0].get("name", "") or ""
        return self.ingest_messages_from_snapshot(snapshot)

    def get_messages(self, scope: str = "current", session_id: str | None = None) -> list[dict]:
        if scope == "all_sessions":
            return load_all_sessions_messages()
        if scope == "session" and session_id:
            return load_session_messages(session_id)
        return catalog_to_list(self.state.messages_catalog)

    def process_new_messages(self, snapshot: dict) -> tuple[int, bool]:
        del snapshot
        round_new = 0
        stop_inner = False
        for entry in list(self.state.messages_catalog.values()):
            if entry.get("type") != "chat_session":
                continue
            sess_id = entry.get("id", "")
            if not sess_id or sess_id in self.state.processed_messages:
                continue
            self.state.processed_messages.add(sess_id)
            round_new += 1
            if not entry.get("is_transaction"):
                self.log(
                    f"Bỏ qua đoạn chat (không GD): {sess_id} "
                    f"— {entry.get('date') or '—'}"
                )
                continue
            self.log(
                f"Xử lý đoạn chat có GD: {sess_id} "
                f"— {entry.get('date') or '—'} ({entry.get('member_count', 0)} tin)"
            )
            records = self._extract_records_from_message(entry)
            if records:
                self._save_records(records)

            msg_date = entry.get("date") or ""
            if msg_date and self.state.stop_date:
                if message_reached_stop_threshold(msg_date, self.state.stop_date):
                    self.log(
                        f"Dừng loop-2: session {msg_date} tới ngưỡng stop_date {self.state.stop_date}"
                    )
                    stop_inner = True
                    break
        self._drain_plan_worker()
        return round_new, stop_inner

    def _set_chat_from_sidebar(self, snapshot: dict) -> None:
        sidebar = snapshot.get("sidebar") or []
        for i, item in enumerate(sidebar):
            if item.get("selected"):
                self.state.current_chat_id = _sidebar_chat_id(item, i)
                self.state.current_chat_name = item.get("name") or self.state.current_chat_id
                return
        if sidebar:
            item = sidebar[0]
            self.state.current_chat_id = _sidebar_chat_id(item, 0)
            self.state.current_chat_name = item.get("name") or self.state.current_chat_id
        else:
            self.state.current_chat_id = "segment"
            self.state.current_chat_name = "Đoạn chat"

    def run_inner_loop(self, max_iterations: int | None = 50) -> None:
        """loop-2: chụp vùng chat → OCR → kiểm tra ngày → cuộn."""
        self.log("Bắt đầu loop-2 (INNER)...")

        i = 0
        while True:
            if not self.state.running:
                break
            if max_iterations is not None and i >= max_iterations:
                self.log(f"loop-2: đạt giới hạn {max_iterations} vòng.")
                break
            i += 1

            self._set_fsm(FsmState.CAPTURE)
            self.log(f"loop-2 {i}: chụp vùng chat...")
            try:
                screenshot = self.capture_chat_only()
                if self.state.session_dir:
                    shot_path = self.state.session_dir / "screenshots" / f"chat_{i:03d}.jpg"
                    shot_path.write_bytes(screenshot)
                    self.state.last_screenshot_path = str(shot_path)
            except CaptureError as exc:
                self.log(f"Lỗi capture: {exc}")
                break
            except Exception as exc:
                self.log(f"Lỗi capture: {exc}")
                break

            self._set_fsm(FsmState.PERCEIVE)
            try:
                raw = self.upload_ocr(screenshot, cropped=True)
                snapshot = normalize_snapshot(raw, self.state)
            except Exception as exc:
                self.log(f"Lỗi OCR: {exc}")
                break

            if self.state.segment_mode and not self.state.current_chat_id:
                self._set_chat_from_sidebar(snapshot)

            added = self.ingest_messages_from_snapshot(snapshot)
            if added:
                self.log(
                    f"Lượt chat: +{added} session "
                    f"(tổng {len(self.state.messages_catalog)}, "
                    f"{len(self.state.bubble_catalog)} bubble)"
                )

            round_new, stop_inner = self.process_new_messages(snapshot)
            if stop_inner:
                break

            self._set_fsm(FsmState.PLAN)
            action = self.post_plan(snapshot)
            self.log(f"PLAN → {action.action} ({action.reason})")

            if action.action == "stop_outer":
                self.state.running = False
                break
            if action.action == "stop_inner":
                break

            if not self.state.segment_mode:
                if round_new == 0:
                    self.state.no_new_count += 1
                    if self.state.no_new_count >= 2:
                        self.log("loop-2 kết thúc: không tin mới sau scroll.")
                        break
                else:
                    self.state.no_new_count = 0

            self._set_fsm(FsmState.ACT)
            if action.action not in ("stop_inner", "stop_outer"):
                fx, fy = focus_chat_center(
                    snapshot,
                    self.state.capture_offset_x,
                    self.state.capture_offset_y,
                    self.state.capture_width,
                    self.state.capture_height,
                    capture_target=self.state.capture_target,
                    yolo_layout=self.state.yolo_layout,
                )
                self.state.next_chat_y = execute_action(
                    action,
                    snapshot,
                    self.state.capture_offset_x,
                    self.state.capture_offset_y,
                    self.state.capture_width,
                    self.state.capture_height,
                    sidebar_x=self.state.sidebar_x,
                    next_chat_y=self.state.next_chat_y,
                )
                if action.action == "scroll":
                    self.log(f"Đã focus khung chat ({fx}, {fy}) và cuộn.")

        self.log("Kết thúc loop-2.")

    def _pick_next_chat(self, snapshot: dict | None = None) -> dict | None:
        sidebar = (snapshot or {}).get("sidebar") or []
        if not sidebar and self.state.yolo_layout:
            sidebar = self.state.yolo_layout.get("sidebar") or []
        for i, item in enumerate(sidebar):
            cid = _sidebar_chat_id(item, i)
            if cid not in self.state.processed_chat_ids:
                return {"index": i, "id": cid, "name": item.get("name", cid), "item": item}
        return None

    def _open_chat(self, chat: dict, snapshot: dict) -> None:
        sw = self.state.capture_width
        sh = self.state.capture_height
        item = chat.get("item")
        if item and sw and sh:
            sx, sy = bbox_center_screen(
                item,
                self.state.capture_offset_x,
                self.state.capture_offset_y,
                sw,
                sh,
            )
            click_at(sx, sy)
        else:
            self.state.next_chat_y = click_next_chat(
                self.state.sidebar_x, self.state.next_chat_y
            )

    def run_outer_iterator(self, max_chats: int) -> None:
        """loop-1: lần lượt mở từng hội thoại sidebar."""
        snapshot: dict = normalize_snapshot(self.state.yolo_layout or {}, self.state)

        for n in range(max_chats):
            if not self.state.running:
                break

            self._set_fsm(FsmState.NEXT_CHAT)
            chat = self._pick_next_chat(snapshot)
            if chat is None and n > 0:
                self.log("Đã xử lý hết chat sidebar.")
                break
            if chat is None:
                chat = {
                    "id": f"chat_{self.state.next_chat_y}",
                    "name": f"Chat {n + 1}",
                    "index": n,
                    "item": None,
                }

            cid = chat["id"]
            if cid in self.state.processed_chat_ids:
                continue

            self.state.processed_chat_ids.add(cid)
            self.state.current_chat_id = cid
            self.state.current_chat_name = chat.get("name", cid)
            self.reset_cache()
            self.state.processed_messages.clear()
            self.state.bubble_catalog.clear()
            self.state.no_new_count = 0

            self.log(f"loop-1: '{self.state.current_chat_name}'")
            if not self.state.segment_mode and (n > 0 or chat.get("item")):
                self._open_chat(chat, snapshot)

            self.run_inner_loop()

        self._set_fsm(FsmState.DONE)

    def _prepare_session(self, stop_date: str, *, segment: bool) -> None:
        self.state.running = True
        self.state.stop_requested = False
        self.state.segment_mode = segment
        self.state.stop_date = stop_date
        self.state.transaction_count = 0
        self.state.processed_messages.clear()
        self.state.processed_chat_ids.clear()
        self.state.dedupe_keys.clear()
        self.state.transaction_codes.clear()
        self.state.records_by_id.clear()
        self.state.messages_catalog.clear()
        self.state.bubble_catalog.clear()
        self.state.no_new_count = 0
        self.state.yolo_layout = None
        self.state.csv_path = None
        self.state.json_path = None
        self.state.session_dir = None
        self.state.ensure_session_paths()
        init_csv_file(self.state.csv_path)
        if self.state.json_path:
            init_json_file(self.state.json_path)
            if self.state.json_path.exists():
                data = json.loads(self.state.json_path.read_text(encoding="utf-8"))
                self.state.transaction_codes = _existing_transaction_codes(data)

    def _finalize_session(self, label: str) -> None:
        self.state.running = False
        self._set_fsm(FsmState.DONE)
        persist_messages(self.state.session_dir, self.state.messages_catalog)

        st = self._get_plan_worker_status()
        pending = int(st.get("pending") or 0)
        processing = st.get("processing_id")
        finished_n = int(st.get("finished_pending") or 0)
        if pending or processing or finished_n:
            if self.state.stop_requested:
                self.log(
                    "Đã dừng chụp/OCR — giữ kết nối AI, chờ phân tích và lưu các đoạn chat..."
                )
            else:
                self.log("Chờ AI hoàn tất phân tích các đoạn chat đã enqueue...")
            self._wait_for_plan_worker_completion()

        self._drain_plan_worker()
        self._deactivate_plan_worker()

        if self.state.transaction_count > 0:
            try:
                analysis = self.analyze_session()
                self.log(f"Phân tích: {analysis.get('summary_vi', '')[:200]}")
                warn_n = len(analysis.get("warnings") or [])
                if warn_n:
                    self.log(f"Cảnh báo đối soát: {warn_n}")
            except ApiError as exc:
                self.log(f"Không gọi được /analyze: {exc}")

        n_msg = len(self.state.messages_catalog)
        if n_msg:
            self.log(f"Đã lưu {n_msg} lượt chat → messages.json")
        n = self.state.transaction_count
        path = self.state.csv_path
        if n > 0:
            self.log(f"{label}: {n} giao dịch → {path}")
        else:
            self.log(f"{label}: không có giao dịch → {path}")

    def run_full(self, stop_date: str, max_chats: int = 3) -> None:
        """Khởi chạy chế độ đối soát toàn bộ."""
        self._prepare_session(stop_date, segment=False)
        self.log(
            f"Bắt đầu đối soát. stop_date={stop_date or '(không)'} — "
            f"export: {self.state.session_dir}"
        )
        try:
            self._init_yolo_layout()
            self._activate_plan_worker()
            self.run_outer_iterator(max_chats)
        finally:
            self._finalize_session("Hoàn tất")

    def run_chat_segment(self, stop_date: str) -> None:
        """Khởi chạy chế độ quét đoạn."""
        self._prepare_session(stop_date, segment=True)
        self.state.current_chat_id = ""
        self.state.current_chat_name = ""
        self.reset_cache()
        self.log(
            f"Chế độ quét đoạn — dừng tại stop_date. "
            f"stop_date={stop_date or '(chưa đặt)'} — export: {self.state.session_dir}"
        )
        try:
            self._init_yolo_layout()
            self._activate_plan_worker()
            self.run_inner_loop(max_iterations=None)
        finally:
            self._finalize_session("Hoàn tất đoạn")

    def stop(self) -> None:
        self.state.running = False
        self.state.stop_requested = True
        self.log("Đang dừng chụp/OCR — vẫn chờ AI phân tích các đoạn chat trong hàng đợi...")


ReconciliationLogic = ReconciliationOrchestrator

__all__ = ["ReconciliationLogic", "ReconciliationOrchestrator", "normalize_snapshot"]
