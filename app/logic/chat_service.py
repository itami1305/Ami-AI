"""
Chat service — gọi POST /chat/completions, /chat/stream.
"""

from app.chat.logic import ChatLogic as ChatService

__all__ = ["ChatService"]
