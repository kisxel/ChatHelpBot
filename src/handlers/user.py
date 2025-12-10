from aiogram import Bot, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat

router = Router()


async def get_chat_from_db(chat_id: int) -> Chat | None:
    """Получает информацию о чате из базы данных."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        return result.scalar_one_or_none()


@router.message(Command("start"))
async def cmd_start(message: types.Message, bot: Bot) -> None:
    # В групповом чате проверяем активацию
    if message.chat.type != ChatType.PRIVATE:
        chat = await get_chat_from_db(message.chat.id)
        if chat and chat.is_active:
            await message.answer("✅ Бот уже активирован в этом чате!")
        else:
            await message.answer(
                "⚠️ Бот не активирован в этом чате.\n"
                "Администратор может активировать его командой /setup"
            )
        return

    # В личных сообщениях показываем приветствие
    await message.answer(
        "👋 Привет! Я бот-модератор.\n\n"
        "Я помогаю следить за порядком в чатах.\n\n"
        "📝 <b>Как начать работу:</b>\n"
        "1. Добавьте меня в групповой чат\n"
        "2. Назначьте меня администратором\n"
        "3. Выполните команду /setup\n\n"
        "💡 Используйте /help для списка команд",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎛 Панель управления",
                        callback_data="open_panel",
                    )
                ]
            ]
        ),
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "📖 <b>Список команд:</b>\n\n"
        "<b>Основные:</b>\n"
        "/start - начать работу с ботом\n"
        "/help - показать это сообщение\n\n"
        "<b>Настройка:</b>\n"
        "/setup - активировать бота в чате\n"
        "/check - проверить состояние бота (в чате)\n\n"
        "<b>Панель управления:</b>\n"
        "/panel - панель управления (в ЛС с ботом)\n\n"
        "<b>Модерация:</b>\n"
        "/ban [время] [причина] - забанить (или: бан)\n"
        "/unban - разбанить (или: разбан)\n"
        "/mute [время] [причина] - замутить (или: мут)\n"
        "/unmute - снять мут (или: размут)\n"
        "/kick [причина] - кикнуть (или: кик)\n\n"
        "<b>Репорт:</b>\n"
        "!admin [текст] - позвать админа\n"
        "!report [текст] - отправить жалобу\n\n"
        "<b>Формат времени:</b>\n"
        "30s (30с), 5m (5м), 2h (2ч), 1d (1д), 1w (1н)\n"
        "Пример: 1d12h30m или 1д12ч30м",
        parse_mode="HTML",
    )


@router.message(Command("about"))
async def cmd_about(message: types.Message) -> None:
    await message.answer(
        "ℹ️ <b>О боте</b>\n\n<i>Soon...</i>",
        parse_mode="HTML",
    )
