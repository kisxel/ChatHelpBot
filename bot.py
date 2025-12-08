import asyncio
import logging
from aiogram import Bot, Dispatcher
from src.config import BOT_TOKEN
from src.database.core import init_db

from src.handlers import user

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(user.router)

    print("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Стоп")
