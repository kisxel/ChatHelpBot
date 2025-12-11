"""Обработка постов из привязанного канала."""

import asyncio
import contextlib

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat

router = Router(name="channel_posts")

# Минимальная длина ID канала для определения формата
MIN_CHANNEL_ID_LENGTH = 10


def to_full_channel_id(channel_id: int) -> int:
    """Преобразует ID канала в полный формат с -100.

    Примеры:
    - 3298625352 -> -1003298625352
    - -1003298625352 -> -1003298625352
    - 1003298625352 -> -1003298625352
    """
    str_id = str(abs(channel_id))
    # Если уже начинается с 100 и достаточно длинный - просто добавляем минус
    if str_id.startswith("100") and len(str_id) > MIN_CHANNEL_ID_LENGTH:
        return -abs(channel_id)
    # Иначе добавляем -100 в начало
    return int(f"-100{str_id}")


async def get_active_chat() -> Chat | None:
    """Получает активный чат из базы данных."""
    async with async_session() as session:
        result = await session.execute(select(Chat).where(Chat.is_active))
        return result.scalar_one_or_none()


async def close_chat_temporarily(bot: Bot, chat_id: int) -> None:
    """Временно закрывает чат."""
    with contextlib.suppress(Exception):
        await bot.set_chat_permissions(
            chat_id,
            types.ChatPermissions(can_send_messages=False),
        )


async def open_chat(bot: Bot, chat_id: int) -> None:
    """Открывает чат."""
    with contextlib.suppress(Exception):
        await bot.set_chat_permissions(
            chat_id,
            types.ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )


async def reopen_and_edit_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    original_text: str,
    delay: int,
) -> None:
    """Открывает чат после задержки и редактирует сообщение."""
    await asyncio.sleep(delay)

    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        current_chat = result.scalar_one_or_none()

    if current_chat and not current_chat.is_closed:
        await open_chat(bot, chat_id)

        # Редактируем сообщение - убираем текст про закрытие чата
        with contextlib.suppress(Exception):
            await bot.edit_message_text(
                text=original_text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
            )


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.sender_chat,  # Только сообщения от каналов
)
async def handle_channel_post(message: types.Message, bot: Bot) -> None:
    """Обрабатывает сообщения от канала в группе комментариев."""
    chat = await get_active_chat()

    if not chat or chat.chat_id != message.chat.id:
        return

    if not chat.channel_post_enabled:
        return

    if not chat.linked_channel_id or not chat.channel_post_text:
        return

    if message.sender_chat.id != chat.linked_channel_id:
        return

    # Определяем нужно ли закрывать чат
    close_duration = (
        chat.close_chat_duration
        if chat.close_chat_on_post and chat.close_chat_duration > 0
        else 0
    )

    # Закрываем чат если нужно
    if close_duration > 0:
        await close_chat_temporarily(bot, chat.chat_id)

    # Формируем текст
    original_text = chat.channel_post_text
    post_text = original_text
    if close_duration > 0:
        post_text += (
            f"\n\n<i>[Чат отключён на {close_duration} сек. "
            f"для предотвращения спама от ботов]</i>"
        )

    # Отправляем ответ
    sent_message = None
    with contextlib.suppress(Exception):
        sent_message = await message.reply(post_text, parse_mode="HTML")

    # Открываем чат через N секунд и редактируем сообщение
    if close_duration > 0 and sent_message:
        await reopen_and_edit_message(
            bot,
            chat.chat_id,
            sent_message.message_id,
            original_text,
            close_duration,
        )
