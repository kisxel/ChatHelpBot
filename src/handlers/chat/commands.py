"""Команды управления чатом: /setup, /check."""

from aiogram import Bot, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command
from sqlalchemy import select

from src.common.permissions import (
    can_bot_delete,
    can_bot_restrict,
    is_bot_admin,
    is_user_admin,
)
from src.database.core import async_session
from src.database.models import Chat

router = Router(name="chat")


async def get_chat_from_db(chat_id: int) -> Chat | None:
    """Получает информацию о чате из базы данных."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        return result.scalar_one_or_none()


async def has_active_chat() -> bool:
    """Проверяет, есть ли уже активный чат."""
    async with async_session() as session:
        result = await session.execute(select(Chat).where(Chat.is_active))
        return result.scalar_one_or_none() is not None


async def activate_chat(
    chat_id: int, title: str | None, activated_by: int
) -> Chat:
    """Активирует чат в базе данных."""
    async with async_session() as session:
        chat = await get_chat_from_db(chat_id)
        if chat:
            chat.is_active = True
            chat.title = title
            chat.activated_by = activated_by
            session.add(chat)
        else:
            chat = Chat(
                chat_id=chat_id,
                title=title,
                is_active=True,
                activated_by=activated_by,
            )
            session.add(chat)
        await session.commit()
        return chat


@router.message(Command("setup"))
async def cmd_setup(message: types.Message, bot: Bot) -> None:
    """Команда /setup - активация бота в чате."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах.\n"
            "Добавьте меня в группу и выполните /setup там. (администратор должен быть НЕ АНОНИМЕН)"
        )
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # Проверяем, не активирован ли уже бот в этом чате
    existing_chat = await get_chat_from_db(chat_id)
    if existing_chat and existing_chat.is_active:
        await message.answer("✅ Бот уже активирован в этом чате!")
        return

    # Проверяем, не активирован ли бот в другом чате
    if await has_active_chat():
        await message.answer(
            "❌ Бот уже активирован в другом чате.\n"
            "Сначала деактивируйте его там через /panel в ЛС с ботом."
        )
        return

    # Проверяем, является ли пользователь администратором
    if not await is_user_admin(chat_id, user_id, bot):
        await message.answer(
            "❌ Только администраторы чата могут активировать бота."
        )
        return

    # Проверяем, является ли бот администратором
    if not await is_bot_admin(chat_id, bot):
        await message.answer(
            "⚠️ Для корректной работы мне нужны права администратора.\n\n"
            "Пожалуйста, назначьте меня администратором с правами:\n"
            "• Удаление сообщений\n"
            "• Блокировка пользователей\n"
            "• Закрепление сообщений\n\n"
            "После этого выполните /setup ещё раз."
        )
        return

    # Активируем чат в базе данных
    await activate_chat(chat_id, message.chat.title, user_id)
    await message.answer("✅ Бот успешно активирован в этом чате!")


@router.message(Command("check"))
async def cmd_check(message: types.Message, bot: Bot) -> None:
    """Команда /check - проверка состояния бота."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах."
        )
        return

    chat_id = message.chat.id

    try:
        bot_can_restrict = await can_bot_restrict(chat_id, bot)
        bot_can_delete = await can_bot_delete(chat_id, bot)
        chat = await get_chat_from_db(chat_id)

        if chat and chat.is_active and bot_can_restrict and bot_can_delete:
            await message.answer("✅ Бот активирован и работает!")
        else:
            status_lines = ["🤖 <b>Состояние бота</b>\n"]

            if chat and chat.is_active:
                status_lines.append("✅ Бот активирован")
            else:
                status_lines.append("⚠️ Бот не активирован (/setup)")

            if bot_can_restrict:
                status_lines.append("✅ Может ограничивать пользователей")
            else:
                status_lines.append("❌ Нет прав на ограничение")

            if bot_can_delete:
                status_lines.append("✅ Может удалять сообщения")
            else:
                status_lines.append("❌ Нет прав на удаление сообщений")

            await message.answer("\n".join(status_lines), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка проверки: {e}")
