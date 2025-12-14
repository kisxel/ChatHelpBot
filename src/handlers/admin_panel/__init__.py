"""Панель управления администратора."""

from aiogram import Router

from src.handlers.admin_panel.bad_words import router as bad_words_router
from src.handlers.admin_panel.filters import router as filters_router
from src.handlers.admin_panel.panel import router as panel_router
from src.handlers.admin_panel.post_message import router as post_message_router
from src.handlers.admin_panel.settings import router as settings_router
from src.handlers.admin_panel.stats import router as stats_router
from src.handlers.admin_panel.warns import router as warns_router

router = Router(name="admin_panel")

router.include_router(panel_router)
router.include_router(post_message_router)  # FSM для сообщения поста
router.include_router(settings_router)  # FSM обработчики для канала
router.include_router(filters_router)  # FSM обработчики для фильтров
router.include_router(bad_words_router)  # FSM для запрещённых слов
router.include_router(stats_router)
router.include_router(warns_router)

__all__ = ["router"]
