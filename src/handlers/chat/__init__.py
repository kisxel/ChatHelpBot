"""Обработчики управления чатом."""

from aiogram import Router

from src.handlers.chat.channel_posts import router as channel_posts_router
from src.handlers.chat.commands import router as commands_router

router = Router(name="chat_main")
router.include_router(commands_router)
router.include_router(channel_posts_router)

__all__ = ["router"]
