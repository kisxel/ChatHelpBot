"""Команды репорта: !admin, !report и т.д."""

import re

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat
from src.handlers.moderation.utils import are_report_cmds_enabled

router = Router(name="reports")

# Паттерн для команд репорта
REPORT_CMD_PATTERN = re.compile(
    r"^[!/](admin|админ|report|репорт)(?:\s+(.*))?$", re.IGNORECASE
)


async def get_chat_owner_id(chat_id: int) -> int | None:
    """Получает ID владельца чата (кто активировал бота)."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            return chat.activated_by
    return None


@router.message(F.text.regexp(REPORT_CMD_PATTERN))
async def report_command(message: types.Message, bot: Bot) -> None:
    """Обработчик команд репорта: !admin, !админ, !report, !репорт."""
    if message.chat.type == ChatType.PRIVATE or not message.from_user:
        return

    if not await are_report_cmds_enabled(message.chat.id):
        return

    chat_id = message.chat.id
    chat_title = message.chat.title or "Без названия"

    owner_id = await get_chat_owner_id(chat_id)
    if not owner_id:
        await message.answer("❌ Бот не активирован в этом чате.")
        return

    reporter = message.from_user.full_name
    match = REPORT_CMD_PATTERN.match(message.text)
    report_text = match.group(2) if match and match.group(2) else None

    try:
        if message.reply_to_message:
            reported_msg = message.reply_to_message
            reported_user = (
                reported_msg.from_user.full_name
                if reported_msg.from_user
                else "Неизвестно"
            )

            notification = (
                f"🚨 <b>Новый репорт</b>\n\n"
                f"📍 Чат: {chat_title}\n"
                f"👤 Отправил: {reporter}\n"
                f"⚠️ На пользователя: {reported_user}"
            )
            if report_text:
                notification += f"\n💬 Комментарий: {report_text}"
            notification += "\n\nСообщение ниже:"

            await bot.send_message(owner_id, notification, parse_mode="HTML")
            await reported_msg.forward(owner_id)
        else:
            notification = (
                f"🚨 <b>Новый репорт</b>\n\n"
                f"📍 Чат: {chat_title}\n"
                f"👤 Отправил: {reporter}"
            )
            if report_text:
                notification += f"\n💬 Сообщение: {report_text}"
            else:
                notification += "\n\n<i>Репорт без указания сообщения</i>"

            await bot.send_message(owner_id, notification, parse_mode="HTML")

        await message.answer("✅ Репорт отправлен администратору.")
    except Exception:
        await message.answer(
            "❌ Не удалось отправить репорт. "
            "Возможно, администратор заблокировал бота."
        )
