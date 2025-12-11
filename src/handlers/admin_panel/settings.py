"""Настройки бота."""

import contextlib

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import update

from src.common.keyboards import (
    get_channel_settings_keyboard,
    get_settings_keyboard,
)
from src.database.core import async_session
from src.database.models import Chat
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="panel_settings")

# Константы
MAX_TEXT_PREVIEW_LENGTH = 100
MAX_TEXT_LENGTH = 4000
MIN_CHANNEL_ID_LENGTH = 10
MAX_CLOSE_DURATION = 300


def to_full_channel_id(channel_id: int) -> int:
    """Преобразует ID канала в полный формат с -100."""
    str_id = str(abs(channel_id))
    if str_id.startswith("100") and len(str_id) > MIN_CHANNEL_ID_LENGTH:
        return -abs(channel_id)
    return int(f"-100{str_id}")


class ChannelSettingsStates(StatesGroup):
    """Состояния для настройки канала."""

    waiting_channel_id = State()
    waiting_post_text = State()
    waiting_rules_text = State()
    waiting_close_duration = State()


@router.callback_query(F.data == "panel:settings")
async def callback_settings_menu(callback: types.CallbackQuery) -> None:
    """Меню настроек."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    await callback.message.edit_text(
        "⚙️ <b>Настройки бота</b>\n\n"
        "Здесь вы можете включить или выключить группы команд.\n\n"
        "<b>Команды модерации:</b>\n"
        "бан, мут, кик, разбан, размут (и англ. варианты)\n\n"
        "<b>Команды репортов:</b>\n"
        "!admin, !админ, !report, !репорт",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard(chat),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:toggle_mod")
async def callback_toggle_moderation(callback: types.CallbackQuery) -> None:
    """Переключение команд модерации."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    new_value = not chat.enable_moderation_cmds

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(enable_moderation_cmds=new_value)
        )
        await session.commit()

    chat = await get_admin_chat(user_id)
    status = "включены" if new_value else "выключены"
    await callback.answer(f"Команды модерации {status}")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=get_settings_keyboard(chat)
        )


@router.callback_query(F.data == "settings:toggle_report")
async def callback_toggle_report(callback: types.CallbackQuery) -> None:
    """Переключение команд репортов."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    new_value = not chat.enable_report_cmds

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(enable_report_cmds=new_value)
        )
        await session.commit()

    chat = await get_admin_chat(user_id)
    status = "включены" if new_value else "выключены"
    await callback.answer(f"Команды репортов {status}")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=get_settings_keyboard(chat)
        )


# === Настройки правил чата ===


@router.callback_query(F.data == "settings:rules")
async def callback_rules_menu(callback: types.CallbackQuery) -> None:
    """Меню правил чата."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    rules_text = chat.chat_rules_text or "Не заданы"
    if len(rules_text) > MAX_TEXT_PREVIEW_LENGTH:
        rules_text = rules_text[:MAX_TEXT_PREVIEW_LENGTH] + "..."

    await callback.message.edit_text(
        f"📜 <b>Правила чата</b>\n\n"
        f"Этот текст будет отправляться по команде !правила (!rules).\n\n"
        f"<b>Текущий текст:</b>\n{rules_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Изменить правила",
                        callback_data="settings:rules_edit",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="panel:settings"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:rules_edit")
async def callback_rules_edit(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Редактирование правил чата."""
    await callback.message.edit_text(
        "📜 <b>Введите текст правил чата</b>\n\n"
        "Этот текст будет отправляться по команде !правила (!rules).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="settings:rules"
                    )
                ]
            ]
        ),
    )
    await state.set_state(ChannelSettingsStates.waiting_rules_text)
    await callback.answer()


@router.message(StateFilter(ChannelSettingsStates.waiting_rules_text))
async def process_rules_text(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка введённого текста правил чата."""
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение с правилами")
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    rules_text = message.text.strip()

    if len(rules_text) > MAX_TEXT_LENGTH:
        await message.answer(
            f"❌ Текст слишком длинный. Максимум {MAX_TEXT_LENGTH} символов."
        )
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(chat_rules_text=rules_text)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        "✅ Правила чата сохранены!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад к правилам",
                        callback_data="settings:rules",
                    )
                ]
            ]
        ),
    )


# === Настройки канала ===


@router.callback_query(F.data == "settings:channel")
async def callback_channel_settings(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Меню настроек канала."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    # Получаем информацию о канале
    channel_info = "Не привязан"
    if chat.linked_channel_id:
        try:
            channel = await bot.get_chat(chat.linked_channel_id)
            channel_title = channel.title or "Без названия"
            channel_info = f"{chat.linked_channel_id} ({channel_title})"
        except Exception:
            channel_info = str(chat.linked_channel_id)

    post_preview = "Не задан"
    if chat.channel_post_text:
        post_preview = (
            chat.channel_post_text[:MAX_TEXT_PREVIEW_LENGTH] + "..."
            if len(chat.channel_post_text) > MAX_TEXT_PREVIEW_LENGTH
            else chat.channel_post_text
        )

    enabled_status = "✅ Вкл" if chat.channel_post_enabled else "❌ Выкл"
    close_status = (
        f"✅ Вкл ({chat.close_chat_duration} сек)"
        if chat.close_chat_on_post
        else "❌ Выкл"
    )

    await callback.message.edit_text(
        f"📢 <b>Настройки канала</b>\n\n"
        f"<b>ID канала:</b> {channel_info}\n"
        f"<b>Автоответ:</b> {enabled_status}\n"
        f"<b>Закрытие чата:</b> {close_status}\n\n"
        f"<b>Текст для поста:</b>\n{post_preview}",
        parse_mode="HTML",
        reply_markup=get_channel_settings_keyboard(chat),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:channel_id")
async def callback_channel_id_input(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Запрос ID канала."""
    await callback.message.edit_text(
        "📝 <b>Введите ID канала</b>\n\n"
        "Отправьте ID канала в любом формате:\n"
        "• 3298625352\n"
        "• -1003298625352\n\n"
        "Чтобы узнать ID канала, перешлите любое сообщение из него боту "
        "@userinfobot или подобному.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="settings:channel"
                    )
                ]
            ]
        ),
    )
    await state.set_state(ChannelSettingsStates.waiting_channel_id)
    await callback.answer()


@router.message(StateFilter(ChannelSettingsStates.waiting_channel_id))
async def process_channel_id(
    message: types.Message, state: FSMContext, bot: Bot
) -> None:
    """Обработка введённого ID канала."""
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение с ID канала")
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    text = message.text.strip()

    # Убираем минус для парсинга
    clean_text = text.lstrip("-")

    # Проверяем что это число
    if not clean_text.isdigit():
        await message.answer(
            "❌ Неверный формат. Введите ID канала.\n"
            "Например: 3298625352 или -1003298625352"
        )
        return

    # Преобразуем в полный формат -100XXXXXXXXXX
    full_channel_id = to_full_channel_id(int(clean_text))

    # Проверяем доступность канала
    channel_title = None
    try:
        channel = await bot.get_chat(full_channel_id)
        channel_title = channel.title
    except Exception:
        pass

    # Сохраняем полный ID канала в БД
    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(linked_channel_id=full_channel_id)
        )
        await session.commit()

    await state.clear()

    back_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад к настройкам канала",
                    callback_data="settings:channel",
                )
            ]
        ]
    )

    if channel_title:
        await message.answer(
            f"✅ Канал привязан: {channel_title} (ID: {full_channel_id})",
            reply_markup=back_keyboard,
        )
    else:
        await message.answer(
            f"✅ ID канала сохранён: {full_channel_id}\n\n"
            f"⚠️ Не удалось получить информацию о канале. "
            f"Убедитесь, что бот добавлен в канал как администратор.",
            reply_markup=back_keyboard,
        )


@router.callback_query(F.data == "settings:channel_post_text")
async def callback_post_text_menu(callback: types.CallbackQuery) -> None:
    """Меню текста для ответа на пост."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    post_text = chat.channel_post_text or "Не задан"
    if len(post_text) > MAX_TEXT_PREVIEW_LENGTH:
        post_text = post_text[:MAX_TEXT_PREVIEW_LENGTH] + "..."

    await callback.message.edit_text(
        f"📝 <b>Текст для ответа на пост</b>\n\n"
        f"Этот текст будет автоматически отправляться в комментарии "
        f"при появлении нового поста в канале.\n\n"
        f"<b>Текущий текст:</b>\n{post_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Изменить текст",
                        callback_data="settings:channel_post_text_edit",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="settings:channel"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:channel_post_text_edit")
async def callback_post_text_edit(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Редактирование текста для ответа на пост."""
    await callback.message.edit_text(
        "📝 <b>Введите текст для ответа на пост</b>\n\n"
        "Этот текст будет автоматически отправляться в комментарии "
        "при появлении нового поста в канале.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="settings:channel_post_text",
                    )
                ]
            ]
        ),
    )
    await state.set_state(ChannelSettingsStates.waiting_post_text)
    await callback.answer()


@router.message(StateFilter(ChannelSettingsStates.waiting_post_text))
async def process_post_text(message: types.Message, state: FSMContext) -> None:
    """Обработка введённого текста для поста."""
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение")
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    post_text = message.text.strip()

    if len(post_text) > MAX_TEXT_LENGTH:
        await message.answer(
            f"❌ Текст слишком длинный. Максимум {MAX_TEXT_LENGTH} символов."
        )
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(channel_post_text=post_text)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        "✅ Текст для поста сохранён!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад к тексту поста",
                        callback_data="settings:channel_post_text",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data == "settings:toggle_post_enabled")
async def callback_toggle_post_enabled(callback: types.CallbackQuery) -> None:
    """Переключение автоответа на посты."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    new_value = not chat.channel_post_enabled

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(channel_post_enabled=new_value)
        )
        await session.commit()

    status = "включён" if new_value else "выключен"
    await callback.answer(f"Автоответ {status}")

    # Обновляем меню
    chat = await get_admin_chat(user_id)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=get_channel_settings_keyboard(chat)
        )


@router.callback_query(F.data == "settings:toggle_close_chat")
async def callback_toggle_close_chat(callback: types.CallbackQuery) -> None:
    """Переключение закрытия чата после поста."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    new_value = not chat.close_chat_on_post

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(close_chat_on_post=new_value)
        )
        await session.commit()

    status = "включено" if new_value else "выключено"
    await callback.answer(f"Закрытие чата {status}")

    # Обновляем меню
    chat = await get_admin_chat(user_id)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=get_channel_settings_keyboard(chat)
        )


@router.callback_query(F.data == "settings:close_duration")
async def callback_close_duration_input(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Запрос длительности закрытия чата."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    current = chat.close_chat_duration if chat else 10

    await callback.message.edit_text(
        f"⏱ <b>Длительность закрытия чата</b>\n\n"
        f"Введите количество секунд, на которое будет закрыт чат "
        f"после появления поста.\n\n"
        f"<b>Текущее значение:</b> {current} сек.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="settings:channel"
                    )
                ]
            ]
        ),
    )
    await state.set_state(ChannelSettingsStates.waiting_close_duration)
    await callback.answer()


@router.message(StateFilter(ChannelSettingsStates.waiting_close_duration))
async def process_close_duration(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка введённой длительности."""
    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Введите число (количество секунд)")
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    duration = int(message.text.strip())

    if duration < 1 or duration > MAX_CLOSE_DURATION:
        await message.answer(
            "❌ Введите число от 1 до {MAX_CLOSE_DURATION} секунд"
        )
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(close_chat_duration=duration)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Длительность закрытия: {duration} сек.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад к настройкам канала",
                        callback_data="settings:channel",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data == "settings:channel_remove")
async def callback_channel_remove(callback: types.CallbackQuery) -> None:
    """Удаление привязки канала."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    if not chat.linked_channel_id:
        await callback.answer("ℹ️ Канал не привязан", show_alert=True)
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(linked_channel_id=None, channel_post_text=None)
        )
        await session.commit()

    await callback.answer("✅ Привязка канала удалена")

    chat = await get_admin_chat(user_id)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            "📢 <b>Настройки канала</b>\n\n"
            "<b>ID канала:</b> Не привязан\n"
            "<b>Автоответ:</b> ✅ Вкл\n"
            "<b>Закрытие чата:</b> ❌ Выкл\n\n"
            "<b>Текст для поста:</b>\nНе задан",
            parse_mode="HTML",
            reply_markup=get_channel_settings_keyboard(chat),
        )
