"""
# Logic Module Chat — gọi backend, giữ lịch sử hội thoại
"""

from typing import Callable

from app.shared.api_client import ApiError, post_json, post_stream


class ChatLogic:
    """Xử lý chat qua backend (prompt + Ollama)."""

    def __init__(self) -> None:
        # --- Lịch sử hội thoại gửi lên backend ---
        self._history: list[dict[str, str]] = []

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    def clear_history(self) -> None:
        """Xóa lịch sử chat."""
        self._history.clear()

    def send_message(self, message: str) -> str:
        """
        # Gửi tin nhắn → nhận reply tiếng Việt từ backend (non-stream)
        """
        payload = {
            "message": message.strip(),
            "history": self._history,
        }
        result = post_json("/chat/completions", payload)
        reply = result.get("reply", "")

        # --- Cập nhật lịch sử local ---
        self._history.append({"role": "user", "content": message.strip()})
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def send_message_safe(self, message: str) -> tuple[bool, str]:
        """Gửi tin nhắn, trả (ok, text)."""
        try:
            reply = self.send_message(message)
            return True, reply
        except ApiError as exc:
            return False, f"Lỗi kết nối backend: {exc}"

    # ----------------------------------------------------------------- Stream
    def send_message_stream(
        self,
        message: str,
        on_chunk: Callable[[str], None],
        on_done: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        # Gửi tin nhắn ở chế độ streaming
        Gọi đồng bộ — caller nên chạy hàm này trong thread.
        Lịch sử chỉ được cập nhật khi stream kết thúc thành công.
        """
        message = message.strip()
        if not message:
            on_error("Tin nhắn rỗng.")
            return

        payload = {"message": message, "history": self._history}
        full_reply: list[str] = []

        try:
            for evt in post_stream("/chat/stream", payload):
                if "chunk" in evt:
                    chunk = evt["chunk"]
                    if chunk:
                        full_reply.append(chunk)
                        on_chunk(chunk)
                elif "error" in evt:
                    on_error(str(evt["error"]))
                    return
                elif evt.get("done"):
                    break
        except ApiError as exc:
            on_error(f"Lỗi kết nối backend: {exc}")
            return

        reply = "".join(full_reply).strip()
        if not reply:
            on_error("Không nhận được nội dung phản hồi.")
            return

        self._history.append({"role": "user", "content": message})
        self._history.append({"role": "assistant", "content": reply})
        on_done(reply)
