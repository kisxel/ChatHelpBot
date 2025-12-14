"""Антиспам система."""

import contextlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router, types
from sqlalchemy import select

from src.common.keyboards import get_unmute_keyboard
from src.common.permissions import can_bot_restrict, is_user_admin
from src.database.core import async_session
from src.database.models import MessageStats
from src.handlers.moderation.filters import check_bad_words, check_user_filters
from src.handlers.moderation.text_commands import cache_user
from src.handlers.moderation.utils import get_mute_permissions
from src.utils import format_timedelta

router = Router(name="antispam")

# Настройки анти-спама
SPAM_MAX_MESSAGES = 4  # Максимум сообщений
SPAM_TIME_WINDOW = 3  # За последние N секунд
SPAM_MUTE_DURATION = timedelta(minutes=5)  # Мут за спам
SPAM_MUTE_COOLDOWN_SECONDS = 10  # Интервал между сообщениями о муте

# Хранение сообщений пользователей
# Формат: {(chat_id, user_id): [(timestamp, message_id), ...]}
user_messages: dict[tuple[int, int], list[tuple[datetime, int]]] = defaultdict(
    list
)

# Трекинг последних спам-мутов
# Формат: {(chat_id, user_id): timestamp_последнего_мута}
recent_spam_mutes: dict[tuple[int, int], datetime] = {}


def clean_old_messages(chat_id: int, user_id: int) -> None:
    """Удаляет старые записи о сообщениях пользователя."""
    key = (chat_id, user_id)
    if key not in user_messages:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SPAM_TIME_WINDOW)
    user_messages[key] = [
        (ts, msg_id) for ts, msg_id in user_messages[key] if ts > cutoff
    ]


def check_and_get_spam_messages(
    chat_id: int, user_id: int, message_id: int
) -> list[int] | None:
    """Проверяет на спам и возвращает список message_id для удаления."""
    key = (chat_id, user_id)
    clean_old_messages(chat_id, user_id)

    user_messages[key].append((datetime.now(timezone.utc), message_id))

    if len(user_messages[key]) > SPAM_MAX_MESSAGES:
        return [msg_id for _, msg_id in user_messages[key]]

    return None


async def update_message_stats(chat_id: int) -> None:
    """Обновляет статистику сообщений за сегодня."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with async_session() as session:
        result = await session.execute(
            select(MessageStats).where(
                MessageStats.chat_id == chat_id, MessageStats.date == today
            )
        )
        stats = result.scalar_one_or_none()

        if stats:
            stats.message_count += 1
        else:
            stats = MessageStats(chat_id=chat_id, date=today, message_count=1)
            session.add(stats)

        await session.commit()


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def antispam_handler(message: types.Message, bot: Bot) -> None:
    """Обработчик анти-спама для всех сообщений в группах."""
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Кэшируем пользователя для поиска по @username
    cache_user(chat_id, message.from_user)

    # Пропускаем администраторов
    if await is_user_admin(chat_id, user_id, bot):
        return

    # Пропускаем если бот не может ограничивать
    if not await can_bot_restrict(chat_id, bot):
        return

    # Проверяем на спам
    spam_msg_ids = check_and_get_spam_messages(
        chat_id, user_id, message.message_id
    )
    if spam_msg_ids:
        key = (chat_id, user_id)
        now = datetime.now(timezone.utc)
        last_mute = recent_spam_mutes.get(key)

        # Если мут был недавно - просто удаляем сообщение
        if (
            last_mute
            and (now - last_mute).total_seconds() < SPAM_MUTE_COOLDOWN_SECONDS
        ):
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id, message.message_id)
            return

        try:
            # Мутим пользователя
            until_date = now + SPAM_MUTE_DURATION
            await bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=get_mute_permissions(),
                until_date=until_date,
            )

            # Запоминаем время мута
            recent_spam_mutes[key] = now

            # Удаляем спам-сообщения
            for msg_id in spam_msg_ids:
                with contextlib.suppress(Exception):
                    await bot.delete_message(chat_id, msg_id)

            # Очищаем счётчик
            user_messages[(chat_id, user_id)] = []

            await message.answer(
                f"🔇 <b>Авто-мут за спам</b>\n"
                f"👤 Пользователь: {message.from_user.full_name}\n"
                f"⏱ Срок: {format_timedelta(SPAM_MUTE_DURATION)}",
                parse_mode="HTML",
                reply_markup=get_unmute_keyboard(user_id),
            )
        except Exception:
            pass

    # Обновляем статистику сообщений
    await update_message_stats(chat_id)

    # Проверяем на запрещённые слова (если удалено - не проверяем фильтры)
    if await check_bad_words(message, bot):
        return

    # Проверяем фильтры пользователя
    await check_user_filters(message, bot)
