"""Обработка постов из привязанного канала."""

import asyncio
import contextlib
import json

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from src.database.core import async_session
from src.database.models import Chat

router = Router(name="channel_posts")

# Минимальная длина ID канала для определения формата
MIN_CHANNEL_ID_LENGTH = 10


def to_full_channel_id(channel_id: int) -> int:
    """Преобразует ID канала в полный формат с -100."""
    str_id = str(abs(channel_id))
    if str_id.startswith("100") and len(str_id) > MIN_CHANNEL_ID_LENGTH:
        return -abs(channel_id)
    return int(f"-100{str_id}")


def get_buttons_from_json(buttons_json: str | None) -> list[dict]:
    """Парсит кнопки из JSON."""
    if not buttons_json:
        return []
    try:
        return json.loads(buttons_json)
    except (json.JSONDecodeError, TypeError):
        return []


def build_post_keyboard(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    """Строит клавиатуру из кнопок-ссылок в 2 столбика."""
    if not buttons:
        return None

    # Фильтруем валидные кнопки
    valid_buttons = [
        InlineKeyboardButton(text=btn["text"], url=btn["url"])
        for btn in buttons
        if btn.get("text") and btn.get("url")
    ]

    if not valid_buttons:
        return None

    # Распределяем кнопки по 2 в ряд
    keyboard = []
    for i in range(0, len(valid_buttons), 2):
        row = valid_buttons[i : i + 2]
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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


async def send_post_message(
    bot: Bot,
    chat_id: int,
    reply_to_message_id: int,
    text: str | None,
    media_id: str | None,
    media_type: str | None,
    keyboard: InlineKeyboardMarkup | None,
) -> types.Message | None:
    """Отправляет сообщение под пост с медиа и кнопками."""
    try:
        if media_id and media_type:
            if media_type == "photo":
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=media_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    reply_to_message_id=reply_to_message_id,
                )
            if media_type == "video":
                return await bot.send_video(
                    chat_id=chat_id,
                    video=media_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    reply_to_message_id=reply_to_message_id,
                )
            if media_type == "animation":
                return await bot.send_animation(
                    chat_id=chat_id,
                    animation=media_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    reply_to_message_id=reply_to_message_id,
                )
        elif text:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                reply_to_message_id=reply_to_message_id,
            )
    except Exception:
        pass
    return None


async def edit_post_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str | None,
    media_type: str | None,
    keyboard: InlineKeyboardMarkup | None,
) -> None:
    """Редактирует сообщение - убирает текст про закрытие чата."""
    with contextlib.suppress(Exception):
        if media_type:
            # Для медиа редактируем caption
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            # Для текста редактируем text
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )


async def reopen_and_edit_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    original_text: str | None,
    media_type: str | None,
    keyboard: InlineKeyboardMarkup | None,
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
        await edit_post_message(
            bot, chat_id, message_id, original_text, media_type, keyboard
        )


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.sender_chat,
)
async def handle_channel_post(message: types.Message, bot: Bot) -> None:
    """Обрабатывает сообщения от канала в группе комментариев."""
    chat = await get_active_chat()

    if not chat or chat.chat_id != message.chat.id:
        return

    if not chat.channel_post_enabled:
        return

    if not chat.linked_channel_id:
        return

    # Должен быть либо текст, либо медиа
    if not chat.channel_post_text and not chat.channel_post_media_id:
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

    # Строим клавиатуру
    buttons = get_buttons_from_json(chat.channel_post_buttons)
    keyboard = build_post_keyboard(buttons)

    # Формируем текст
    original_text = chat.channel_post_text
    post_text = original_text or ""
    if close_duration > 0 and post_text:
        post_text += (
            f"\n\n<i>[Чат отключён на {close_duration} сек. "
            f"для предотвращения спама от ботов]</i>"
        )

    # Отправляем ответ
    sent_message = await send_post_message(
        bot=bot,
        chat_id=chat.chat_id,
        reply_to_message_id=message.message_id,
        text=post_text if post_text else None,
        media_id=chat.channel_post_media_id,
        media_type=chat.channel_post_media_type,
        keyboard=keyboard,
    )

    # Открываем чат через N секунд и редактируем сообщение
    if close_duration > 0 and sent_message:
        await reopen_and_edit_message(
            bot=bot,
            chat_id=chat.chat_id,
            message_id=sent_message.message_id,
            original_text=original_text,
            media_type=chat.channel_post_media_type,
            keyboard=keyboard,
            delay=close_duration,
        )
