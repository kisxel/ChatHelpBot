"""Все обработчики бота."""

from src.handlers.admin_panel import router as admin_panel_router
from src.handlers.chat import router as chat_router
from src.handlers.moderation import router as moderation_router
from src.handlers.user import router as user_router

__all__ = [
    "admin_panel_router",
    "chat_router",
    "moderation_router",
    "user_router",
]
