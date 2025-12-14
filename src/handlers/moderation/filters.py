"""Фильтрация сообщений пользователей."""

import contextlib
from pathlib import Path

from aiogram import Bot, types
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat, UserFilter

# Максимальная длина сообщения в уведомлении о фильтре
MAX_FILTER_NOTIFICATION_LENGTH = 200

# Путь к файлу со списком запрещённых слов
BAD_WORDS_FILE = (
    Path(__file__).parent.parent.parent.parent / "data" / "bad_words.txt"
)


# Кэш запрещённых слов (для производительности)
class BadWordsCache:
    """Кэш для запрещённых слов."""

    def __init__(self) -> None:
        self.words: set[str] | None = None
        self.mtime: float = 0


_cache = BadWordsCache()


def load_bad_words() -> set[str]:
    """Загружает список запрещённых слов из файла с кэшированием."""
    if not BAD_WORDS_FILE.exists():
        return set()

    # Проверяем, изменился ли файл
    current_mtime = BAD_WORDS_FILE.stat().st_mtime
    if _cache.words is not None and current_mtime == _cache.mtime:
        return _cache.words

    # Перезагружаем кэш
    with open(BAD_WORDS_FILE, encoding="utf-8") as f:
        _cache.words = {line.strip().lower() for line in f if line.strip()}
    _cache.mtime = current_mtime

    return _cache.words


def contains_bad_word(text: str) -> bool:
    """Проверяет, содержит ли текст запрещённые слова."""
    bad_words = load_bad_words()
    if not bad_words:
        return False

    text_lower = text.lower()
    return any(word in text_lower for word in bad_words)


def get_message_text(message: types.Message) -> str | None:
    """Получает текст из сообщения любого типа."""
    # Обычный текст
    if message.text:
        return message.text
    # Подпись к медиа (фото, видео, документ)
    if message.caption:
        return message.caption
    return None


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
    if not message.from_user:
        return

    # Получаем текст из любого типа сообщения
    text = get_message_text(message)
    if not text:
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

    text_lower = text.lower()

    for f in filters:
        if should_filter_message(text_lower, f):
            if f.notify:
                await notify_admin_about_filter(message, bot, text)
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id, message.message_id)
            return


async def notify_admin_about_filter(
    message: types.Message, bot: Bot, text: str
) -> None:
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

        msg_preview = text[:MAX_FILTER_NOTIFICATION_LENGTH]
        notification = (
            f"🗑 <b>Удалено по фильтру</b>\n\n"
            f"📍 Чат: {chat_title}\n"
            f"👤 Пользователь: {user_name}\n"
            f"💬 Сообщение: {msg_preview}"
        )
        if len(text) > MAX_FILTER_NOTIFICATION_LENGTH:
            notification += "..."

        await bot.send_message(
            chat.activated_by, notification, parse_mode="HTML"
        )
    except Exception:
        pass


async def check_bad_words(message: types.Message, bot: Bot) -> bool:
    """Проверяет сообщение на запрещённые слова и удаляет при необходимости.

    Возвращает True, если сообщение было удалено.
    """
    if not message.from_user:
        return False

    # Получаем текст из любого типа сообщения
    text = get_message_text(message)
    if not text:
        return False

    chat_id = message.chat.id

    # Проверяем, включена ли фильтрация запрещённых слов для этого чата
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        chat = result.scalar_one_or_none()

    if not chat or not chat.bad_words_enabled:
        return False

    # Проверяем текст на запрещённые слова
    if contains_bad_word(text):
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id, message.message_id)
        return True

    return False
