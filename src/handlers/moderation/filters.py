"""Фильтрация сообщений пользователей."""

import contextlib

from aiogram import Bot, types
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat, UserFilter

# Максимальная длина сообщения в уведомлении о фильтре
MAX_FILTER_NOTIFICATION_LENGTH = 200


def should_filter_message(text_lower: str, f: UserFilter) -> bool:
    """Проверяет, должно ли сообщение быть отфильтровано."""
    patterns = [p.strip().lower() for p in f.pattern.split(",")]

    if f.filter_type == "block":
        return any(p and p in text_lower for p in patterns)

    if f.filter_type == "allow":
        contains_allowed = any(p and p in text_lower for p in patterns)
        return not contains_allowed

    return False


async def check_user_filters(message: types.Message, bot: Bot) -> None:
    """Проверяет сообщение на соответствие фильтрам пользователя."""
    if not message.from_user or not message.text:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(
            select(UserFilter).where(
                UserFilter.chat_id == chat_id,
                UserFilter.user_id == user_id,
                UserFilter.is_active,
            )
        )
        filters = list(result.scalars().all())

    if not filters:
        return

    text_lower = message.text.lower()

    for f in filters:
        if should_filter_message(text_lower, f):
            if f.notify:
                await notify_admin_about_filter(message, bot)
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id, message.message_id)
            return


async def notify_admin_about_filter(message: types.Message, bot: Bot) -> None:
    """Отправляет уведомление админу об удалённом сообщении по фильтру."""
    chat_id = message.chat.id

    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        chat = result.scalar_one_or_none()

    if not chat or not chat.activated_by:
        return

    try:
        user_name = message.from_user.full_name if message.from_user else "?"
        chat_title = message.chat.title or "Без названия"

        notification = (
            f"🗑 <b>Удалено по фильтру</b>\n\n"
            f"📍 Чат: {chat_title}\n"
            f"👤 Пользователь: {user_name}\n"
            f"💬 Сообщение: {message.text[:MAX_FILTER_NOTIFICATION_LENGTH]}"
        )
        if len(message.text) > MAX_FILTER_NOTIFICATION_LENGTH:
            notification += "..."

        await bot.send_message(
            chat.activated_by, notification, parse_mode="HTML"
        )
    except Exception:
        pass
