"""Статистика чата."""

from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from src.database.core import async_session
from src.database.models import MessageStats, UserFilter
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="panel_stats")


async def get_chat_stats(chat_id: int) -> dict:
    """Получает статистику чата."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )

    async with async_session() as session:
        result = await session.execute(
            select(func.sum(MessageStats.message_count)).where(
                MessageStats.chat_id == chat_id, MessageStats.date >= week_ago
            )
        )
        messages_week = result.scalar() or 0

    return {"messages_week": messages_week}


@router.callback_query(F.data == "panel:stats")
async def callback_chat_stats(callback: types.CallbackQuery, bot: Bot) -> None:
    """Статистика чата."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    try:
        tg_chat = await bot.get_chat(chat.chat_id)
        member_count = await bot.get_chat_member_count(chat.chat_id)
        title = tg_chat.title or "Без названия"
    except Exception:
        title = chat.title or "Без названия"
        member_count = "?"

    stats = await get_chat_stats(chat.chat_id)

    async with async_session() as session:
        result = await session.execute(
            select(func.count(UserFilter.id)).where(
                UserFilter.chat_id == chat.chat_id, UserFilter.is_active
            )
        )
        filters_count = result.scalar() or 0

    text = (
        f"📊 <b>Статистика: {title}</b>\n\n"
        f"👥 <b>Участников:</b> {member_count}\n"
        f"💬 <b>Сообщений за 7 дней:</b> {stats['messages_week']}\n"
        f"⚙️ <b>Активных фильтров:</b> {filters_count}\n"
        f"📅 <b>Активирован:</b> {chat.activated_at}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="panel:main"
                    )
                ]
            ]
        ),
    )
    await callback.answer()
