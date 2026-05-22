"""
# Module ghép prompt Chat
Giữ cấu trúc prompt trước khi đưa vào AI local — luôn yêu cầu trả lời tiếng Việt.
"""

from typing import Any

# --- System prompt cố định: bắt buộc tiếng Việt ---
SYSTEM_PROMPT_VI = """Bạn là trợ lý AI của Ami-AI.
QUY TẮC BẮT BUỘC:
- Luôn trả lời bằng tiếng Việt.
- Trả lời rõ ràng, súc tích, lịch sự.
- Nếu người dùng hỏi bằng ngôn ngữ khác, vẫn trả lời bằng tiếng Việt.
- Không bịa đặt thông tin; nếu không chắc, nói rõ là không biết.
"""


def build_messages(user_message: str, history: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """
    # Ghép danh sách message cho Ollama
    - system: quy tắc tiếng Việt
    - history: lịch sử hội thoại (role + content)
    - user: tin nhắn hiện tại
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT_VI},
    ]

    # --- Thêm lịch sử nếu có ---
    if history:
        for item in history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if content.strip():
                messages.append({"role": role, "content": content})

    # --- Tin nhắn người dùng hiện tại ---
    messages.append({"role": "user", "content": user_message})
    return messages


def build_ollama_payload(
    messages: list[dict[str, str]], model: str, stream: bool = False
) -> dict[str, Any]:
    """
    # Tạo body request gửi Ollama /api/chat
    """
    return {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
