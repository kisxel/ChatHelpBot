from aiogram import Router, types
from aiogram.filters import Command

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    await message.answer(
        "👋 Привет! Я бот-модератор.\n\n"
        "Я помогаю следить за порядком в чатах.\n\n"
        "📝 <b>Как начать работу:</b>\n"
        "1. Добавьте меня в групповой чат\n"
        "2. Назначьте меня администратором\n"
        "3. Выполните команду /setup\n\n"
        "💡 Используйте /help для списка команд",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "📖 <b>Список команд:</b>\n\n"
        "<b>Основные:</b>\n"
        "/start - начать работу с ботом\n"
        "/help - показать это сообщение\n\n"
        "<b>Для чатов:</b>\n"
        "/setup - активировать бота в чате\n"
        "/status - проверить статус бота\n",
        parse_mode="HTML",
    )
