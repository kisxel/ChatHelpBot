"""Проверка прав пользователей и бота."""

from aiogram import Bot, types
from aiogram.enums import ChatMemberStatus


async def is_user_admin(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Проверяет, является ли пользователь администратором чата."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except Exception:
        return False


async def is_bot_admin(chat_id: int, bot: Bot) -> bool:
    """Проверяет, является ли бот администратором чата."""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        return bot_member.status == ChatMemberStatus.ADMINISTRATOR
    except Exception:
        return False


async def can_bot_restrict(chat_id: int, bot: Bot) -> bool:
    """Проверяет, может ли бот ограничивать пользователей."""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if isinstance(bot_member, types.ChatMemberAdministrator):
            return bot_member.can_restrict_members
        return False
    except Exception:
        return False


async def can_bot_delete(chat_id: int, bot: Bot) -> bool:
    """Проверяет, может ли бот удалять сообщения."""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if isinstance(bot_member, types.ChatMemberAdministrator):
            return bot_member.can_delete_messages
        return False
    except Exception:
        return False
