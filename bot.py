import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from src.config import BOT_TOKEN
from src.database.core import init_db
from src.handlers import admin_panel, chat, moderation, user

logging.basicConfig(level=logging.INFO)


async def set_bot_commands(bot: Bot) -> None:
    """Устанавливает меню команд бота."""
    # Команды для ЛС
    private_commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="panel", description="Панель управления"),
        BotCommand(command="about", description="О боте"),
    ]
    await bot.set_my_commands(
        private_commands, scope=BotCommandScopeAllPrivateChats()
    )

    # Команды для групповых чатов
    group_commands = [
        BotCommand(command="check", description="Проверить состояние бота"),
    ]
    await bot.set_my_commands(
        group_commands, scope=BotCommandScopeAllGroupChats()
    )


async def main() -> None:
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(user.router)
    dp.include_router(chat.router)
    dp.include_router(admin_panel.router)
    dp.include_router(moderation.router)

    # Устанавливаем меню команд
    await set_bot_commands(bot)

    print("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Стоп")
