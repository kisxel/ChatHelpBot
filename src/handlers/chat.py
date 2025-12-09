"""Обработчики для управления чатами."""

from aiogram import Bot, Router, types
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat

router = Router()


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


async def get_chat_from_db(chat_id: int) -> Chat | None:
    """Получает информацию о чате из базы данных."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        return result.scalar_one_or_none()


async def activate_chat(
    chat_id: int, title: str | None, activated_by: int
) -> Chat:
    """Активирует чат в базе данных."""
    async with async_session() as session:
        chat = await get_chat_from_db(chat_id)
        if chat:
            chat.is_active = True
            chat.title = title
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
    """Команда для активации бота в чате."""
    # Проверяем, что команда вызвана в группе
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах.\n"
            "Добавьте меня в группу и выполните /setup там."
        )
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

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

    await message.answer(
        "✅ Бот успешно активирован в этом чате!\n\n"
        "Доступные команды:\n"
        "/status - проверить статус бота\n"
        "/help - список всех команд"
    )


@router.message(Command("status"))
async def cmd_status(message: types.Message, bot: Bot) -> None:
    """Команда для проверки статуса бота в чате."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "ℹ️ Эта команда работает только в групповых чатах."
        )
        return

    chat_id = message.chat.id
    chat = await get_chat_from_db(chat_id)

    bot_is_admin = await is_bot_admin(chat_id, bot)

    status_text = "📊 <b>Статус бота в чате</b>\n\n"

    if chat and chat.is_active:
        status_text += "✅ Бот активирован\n"
    else:
        status_text += "❌ Бот не активирован (используйте /setup)\n"

    if bot_is_admin:
        status_text += "✅ Бот является администратором\n"
    else:
        status_text += "⚠️ Бот НЕ является администратором\n"

    await message.answer(status_text, parse_mode="HTML")
