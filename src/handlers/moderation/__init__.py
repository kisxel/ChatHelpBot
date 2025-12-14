"""Обработчики модерации."""

from aiogram import Router

from src.handlers.moderation.antispam import router as antispam_router
from src.handlers.moderation.callbacks import router as callbacks_router
from src.handlers.moderation.commands import router as commands_router
from src.handlers.moderation.reports import router as reports_router
from src.handlers.moderation.text_commands import (
    router as text_commands_router,
)
from src.handlers.moderation.warns import router as warns_router

router = Router(name="moderation")

router.include_router(commands_router)
router.include_router(warns_router)
router.include_router(text_commands_router)
router.include_router(reports_router)
router.include_router(callbacks_router)
router.include_router(antispam_router)

__all__ = ["router"]
