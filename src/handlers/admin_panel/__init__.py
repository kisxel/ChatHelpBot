"""Панель управления администратора."""

from aiogram import Router

from src.handlers.admin_panel.filters import router as filters_router
from src.handlers.admin_panel.panel import router as panel_router
from src.handlers.admin_panel.settings import router as settings_router
from src.handlers.admin_panel.stats import router as stats_router

router = Router(name="admin_panel")

router.include_router(panel_router)
router.include_router(filters_router)
router.include_router(settings_router)
router.include_router(stats_router)

__all__ = ["router"]
