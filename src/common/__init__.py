"""Общие утилиты и функции."""

from src.common.permissions import (
    can_bot_delete,
    can_bot_restrict,
    is_bot_admin,
    is_user_admin,
)

__all__ = [
    "can_bot_delete",
    "can_bot_restrict",
    "is_bot_admin",
    "is_user_admin",
]
