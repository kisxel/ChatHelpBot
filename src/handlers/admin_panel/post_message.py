"""Настройки сообщения для ответа на пост канала."""

import contextlib
import json

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import update

from src.database.core import async_session
from src.database.models import Chat
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="post_message")

# Константы
MAX_TEXT_LENGTH = 1024  # Для caption медиа
MAX_TEXT_PREVIEW = 100
MAX_BUTTONS = 10
MAX_BUTTON_TEXT_LENGTH = 64


class PostMessageStates(StatesGroup):
    """Состояния для настройки сообщения поста."""

    waiting_text = State()
    waiting_media = State()
    waiting_button_text = State()
    waiting_button_url = State()
    editing_button_text = State()
    editing_button_url = State()


def get_buttons_from_json(buttons_json: str | None) -> list[dict]:
    """Парсит кнопки из JSON."""
    if not buttons_json:
        return []
    try:
        return json.loads(buttons_json)
    except (json.JSONDecodeError, TypeError):
        return []


def buttons_to_json(buttons: list[dict]) -> str:
    """Конвертирует кнопки в JSON."""
    return json.dumps(buttons, ensure_ascii=False)


def build_post_keyboard(
    buttons: list[dict], include_close_text: bool = False
) -> InlineKeyboardMarkup | None:
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


def get_post_message_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура меню настройки сообщения поста."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить текст",
                    callback_data="post_msg:edit_text",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖼 Изменить медиа",
                    callback_data="post_msg:edit_media",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔘 Управление кнопками",
                    callback_data="post_msg:buttons",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👁 Посмотреть превью",
                    callback_data="post_msg:preview",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить медиа",
                    callback_data="post_msg:delete_media",
                ),
                InlineKeyboardButton(
                    text="🔄 Сбросить всё",
                    callback_data="post_msg:reset_all",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="settings:channel",
                )
            ],
        ]
    )


def get_buttons_menu_keyboard(buttons: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура управления кнопками."""
    keyboard = []

    # Показываем существующие кнопки
    for i, btn in enumerate(buttons):
        btn_text = btn.get("text", "?")[:20]
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {i + 1}. {btn_text}",
                    callback_data=f"post_msg:btn_edit:{i}",
                ),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"post_msg:btn_del:{i}",
                ),
            ]
        )

    # Кнопка добавления если не превышен лимит
    if len(buttons) < MAX_BUTTONS:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="➕ Добавить кнопку",
                    callback_data="post_msg:btn_add",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="settings:channel_post_text",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# === Главное меню сообщения поста ===


@router.callback_query(F.data == "settings:channel_post_text")
async def callback_post_message_menu(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Меню настройки сообщения для поста."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    # Формируем информацию
    text_preview = chat.channel_post_text or "Не задан"
    if len(text_preview) > MAX_TEXT_PREVIEW:
        text_preview = text_preview[:MAX_TEXT_PREVIEW] + "..."

    media_info = "Нет"
    if chat.channel_post_media_type:
        media_types = {
            "photo": "🖼 Фото",
            "video": "🎬 Видео",
            "animation": "🎞 GIF",
        }
        media_info = media_types.get(chat.channel_post_media_type, "📎 Файл")

    buttons = get_buttons_from_json(chat.channel_post_buttons)
    buttons_info = f"{len(buttons)} шт." if buttons else "Нет"

    menu_text = (
        f"📝 <b>Текст под пост</b>\n\n"
        f"<b>Текст:</b>\n{text_preview}\n\n"
        f"<b>Медиа:</b> {media_info}\n"
        f"<b>Кнопки:</b> {buttons_info}"
    )

    # Пробуем редактировать, если не получается (медиа) - удаляем и отправляем новое
    try:
        await callback.message.edit_text(
            menu_text,
            parse_mode="HTML",
            reply_markup=get_post_message_menu_keyboard(),
        )
    except TelegramBadRequest:
        # Сообщение с медиа - удаляем и отправляем новое
        await callback.message.delete()
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=menu_text,
            parse_mode="HTML",
            reply_markup=get_post_message_menu_keyboard(),
        )

    await callback.answer()


# === Редактирование текста ===


@router.callback_query(F.data == "post_msg:edit_text")
async def callback_edit_text(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Редактирование текста сообщения."""
    await callback.message.edit_text(
        "📝 <b>Введите текст сообщения</b>\n\n"
        "Вы можете использовать форматирование:\n"
        "• <b>жирный</b> — &lt;b&gt;текст&lt;/b&gt;\n"
        "• <i>курсив</i> — &lt;i&gt;текст&lt;/i&gt;\n"
        "• <a href='https://example.com'>ссылка</a> — "
        "&lt;a href='URL'&gt;текст&lt;/a&gt;\n\n"
        "Или используйте встроенное форматирование Telegram.",
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
    await state.set_state(PostMessageStates.waiting_text)
    await callback.answer()


@router.message(StateFilter(PostMessageStates.waiting_text))
async def process_text(message: types.Message, state: FSMContext) -> None:
    """Обработка текста сообщения."""
    if not message.text and not message.caption:
        await message.answer("❌ Отправьте текстовое сообщение")
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    # Получаем текст с учётом форматирования
    post_text = message.html_text if message.text else message.caption or ""

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
        "✅ Текст сохранён!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="settings:channel_post_text",
                    )
                ]
            ]
        ),
    )


# === Редактирование медиа ===


@router.callback_query(F.data == "post_msg:edit_media")
async def callback_edit_media(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Редактирование медиа."""
    await callback.message.edit_text(
        "🖼 <b>Отправьте медиа</b>\n\n"
        "Поддерживаемые типы:\n"
        "• Фото\n"
        "• Видео\n"
        "• GIF (анимация)\n\n"
        "Медиа будет прикреплено к сообщению.",
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
    await state.set_state(PostMessageStates.waiting_media)
    await callback.answer()


@router.message(StateFilter(PostMessageStates.waiting_media))
async def process_media(message: types.Message, state: FSMContext) -> None:
    """Обработка медиа."""
    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    media_id = None
    media_type = None

    if message.photo:
        media_id = message.photo[-1].file_id  # Берём самое большое фото
        media_type = "photo"
    elif message.video:
        media_id = message.video.file_id
        media_type = "video"
    elif message.animation:
        media_id = message.animation.file_id
        media_type = "animation"
    else:
        await message.answer(
            "❌ Отправьте фото, видео или GIF",
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
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(
                channel_post_media_id=media_id,
                channel_post_media_type=media_type,
            )
        )
        await session.commit()

    await state.clear()

    media_names = {"photo": "Фото", "video": "Видео", "animation": "GIF"}
    await message.answer(
        f"✅ {media_names.get(media_type, 'Медиа')} сохранено!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="settings:channel_post_text",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data == "post_msg:delete_media")
async def callback_delete_media(callback: types.CallbackQuery) -> None:
    """Удаление медиа."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    if not chat.channel_post_media_id:
        await callback.answer("ℹ️ Медиа не установлено", show_alert=True)
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(channel_post_media_id=None, channel_post_media_type=None)
        )
        await session.commit()

    await callback.answer("✅ Медиа удалено")

    # Обновляем меню
    chat = await get_admin_chat(user_id)
    text_preview = chat.channel_post_text or "Не задан"
    if len(text_preview) > MAX_TEXT_PREVIEW:
        text_preview = text_preview[:MAX_TEXT_PREVIEW] + "..."

    buttons = get_buttons_from_json(chat.channel_post_buttons)
    buttons_info = f"{len(buttons)} шт." if buttons else "Нет"

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            f"📝 <b>Текст под пост</b>\n\n"
            f"<b>Текст:</b>\n{text_preview}\n\n"
            f"<b>Медиа:</b> Нет\n"
            f"<b>Кнопки:</b> {buttons_info}",
            parse_mode="HTML",
            reply_markup=get_post_message_menu_keyboard(),
        )


@router.callback_query(F.data == "post_msg:reset_all")
async def callback_reset_all(callback: types.CallbackQuery) -> None:
    """Сброс всех настроек текста под пост."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    # Проверяем есть ли что сбрасывать
    has_data = (
        chat.channel_post_text
        or chat.channel_post_media_id
        or chat.channel_post_buttons
    )

    if not has_data:
        await callback.answer("ℹ️ Нечего сбрасывать", show_alert=True)
        return

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(
                channel_post_text=None,
                channel_post_media_id=None,
                channel_post_media_type=None,
                channel_post_buttons=None,
            )
        )
        await session.commit()

    await callback.answer("✅ Все настройки сброшены")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            "📝 <b>Текст под пост</b>\n\n"
            "<b>Текст:</b>\nНе задан\n\n"
            "<b>Медиа:</b> Нет\n"
            "<b>Кнопки:</b> Нет",
            parse_mode="HTML",
            reply_markup=get_post_message_menu_keyboard(),
        )


# === Превью ===


@router.callback_query(F.data == "post_msg:preview")
async def callback_preview(callback: types.CallbackQuery, bot: Bot) -> None:
    """Показывает превью сообщения."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    if not chat.channel_post_text and not chat.channel_post_media_id:
        await callback.answer(
            "❌ Сообщение пустое. Добавьте текст или медиа.",
            show_alert=True,
        )
        return

    # Строим клавиатуру из кнопок
    buttons = get_buttons_from_json(chat.channel_post_buttons)
    keyboard = build_post_keyboard(buttons)

    # Добавляем кнопку "Назад" к превью
    back_button = [
        InlineKeyboardButton(
            text="◀️ Закрыть превью",
            callback_data="settings:channel_post_text",
        )
    ]

    if keyboard:
        keyboard.inline_keyboard.append(back_button)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[back_button])

    try:
        if chat.channel_post_media_id:
            # Отправляем с медиа
            if chat.channel_post_media_type == "photo":
                await callback.message.delete()
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=chat.channel_post_media_id,
                    caption=chat.channel_post_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            elif chat.channel_post_media_type == "video":
                await callback.message.delete()
                await bot.send_video(
                    chat_id=callback.message.chat.id,
                    video=chat.channel_post_media_id,
                    caption=chat.channel_post_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            elif chat.channel_post_media_type == "animation":
                await callback.message.delete()
                await bot.send_animation(
                    chat_id=callback.message.chat.id,
                    animation=chat.channel_post_media_id,
                    caption=chat.channel_post_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        else:
            # Только текст
            await callback.message.edit_text(
                chat.channel_post_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except TelegramBadRequest as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

    await callback.answer()


# === Управление кнопками ===


@router.callback_query(F.data == "post_msg:buttons")
async def callback_buttons_menu(callback: types.CallbackQuery) -> None:
    """Меню управления кнопками."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    buttons = get_buttons_from_json(chat.channel_post_buttons)

    await callback.message.edit_text(
        f"🔘 <b>Управление кнопками</b>\n\n"
        f"Кнопок: {len(buttons)}/{MAX_BUTTONS}\n\n"
        f"Нажмите на кнопку чтобы редактировать или удалить.",
        parse_mode="HTML",
        reply_markup=get_buttons_menu_keyboard(buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "post_msg:btn_add")
async def callback_add_button(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Добавление новой кнопки - шаг 1: текст."""
    await callback.message.edit_text(
        "🔘 <b>Добавление кнопки</b>\n\nВведите текст для кнопки:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )
    await state.set_state(PostMessageStates.waiting_button_text)
    await callback.answer()


@router.message(StateFilter(PostMessageStates.waiting_button_text))
async def process_button_text(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка текста кнопки."""
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение")
        return

    btn_text = message.text.strip()
    if len(btn_text) > MAX_BUTTON_TEXT_LENGTH:
        await message.answer(
            "❌ Текст кнопки слишком длинный (макс. {MAX_BUTTON_TEXT_LENGTH} символов)"
        )
        return

    await state.update_data(new_button_text=btn_text)
    await state.set_state(PostMessageStates.waiting_button_url)

    await message.answer(
        f"🔘 <b>Текст кнопки:</b> {btn_text}\n\n"
        "Теперь введите URL (ссылку) для кнопки:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )


@router.message(StateFilter(PostMessageStates.waiting_button_url))
async def process_button_url(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка URL кнопки."""
    if not message.text:
        await message.answer("❌ Отправьте ссылку")
        return

    url = message.text.strip()

    # Простая проверка URL
    if not url.startswith(("http://", "https://", "tg://")):
        await message.answer(
            "❌ Некорректная ссылка. Ссылка должна начинаться с http://, https:// или tg://"
        )
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    data = await state.get_data()
    btn_text = data.get("new_button_text", "Кнопка")

    # Добавляем кнопку
    buttons = get_buttons_from_json(chat.channel_post_buttons)
    buttons.append({"text": btn_text, "url": url})

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(channel_post_buttons=buttons_to_json(buttons))
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Кнопка добавлена!\n\n"
        f"<b>Текст:</b> {btn_text}\n"
        f"<b>Ссылка:</b> {url}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ К кнопкам",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("post_msg:btn_del:"))
async def callback_delete_button(callback: types.CallbackQuery) -> None:
    """Удаление кнопки."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    idx = int(callback.data.split(":")[2])
    buttons = get_buttons_from_json(chat.channel_post_buttons)

    if idx < 0 or idx >= len(buttons):
        await callback.answer("❌ Кнопка не найдена", show_alert=True)
        return

    deleted = buttons.pop(idx)

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(channel_post_buttons=buttons_to_json(buttons))
        )
        await session.commit()

    await callback.answer(f"✅ Кнопка «{deleted.get('text', '?')}» удалена")

    # Обновляем меню
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            f"🔘 <b>Управление кнопками</b>\n\n"
            f"Кнопок: {len(buttons)}/{MAX_BUTTONS}\n\n"
            f"Нажмите на кнопку чтобы редактировать или удалить.",
            parse_mode="HTML",
            reply_markup=get_buttons_menu_keyboard(buttons),
        )


@router.callback_query(F.data.startswith("post_msg:btn_edit:"))
async def callback_edit_button(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Редактирование кнопки."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    idx = int(callback.data.split(":")[2])
    buttons = get_buttons_from_json(chat.channel_post_buttons)

    if idx < 0 or idx >= len(buttons):
        await callback.answer("❌ Кнопка не найдена", show_alert=True)
        return

    btn = buttons[idx]

    await callback.message.edit_text(
        f"✏️ <b>Редактирование кнопки #{idx + 1}</b>\n\n"
        f"<b>Текст:</b> {btn.get('text', '?')}\n"
        f"<b>Ссылка:</b> {btn.get('url', '?')}\n\n"
        f"Выберите что изменить:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✏️ Изменить текст",
                        callback_data=f"post_msg:btn_edit_text:{idx}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔗 Изменить ссылку",
                        callback_data=f"post_msg:btn_edit_url:{idx}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="post_msg:buttons",
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("post_msg:btn_edit_text:"))
async def callback_edit_button_text(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Запрос нового текста кнопки."""
    idx = int(callback.data.split(":")[2])
    await state.update_data(editing_button_idx=idx)
    await state.set_state(PostMessageStates.editing_button_text)

    await callback.message.edit_text(
        "✏️ <b>Введите новый текст кнопки:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(PostMessageStates.editing_button_text))
async def process_edit_button_text(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка нового текста кнопки."""
    if not message.text:
        await message.answer("❌ Отправьте текстовое сообщение")
        return

    new_text = message.text.strip()
    if len(new_text) > MAX_BUTTON_TEXT_LENGTH:
        await message.answer(
            "❌ Текст слишком длинный (макс. {MAX_BUTTON_TEXT_LENGTH} символов)"
        )
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    data = await state.get_data()
    idx = data.get("editing_button_idx", 0)

    buttons = get_buttons_from_json(chat.channel_post_buttons)
    if idx < len(buttons):
        buttons[idx]["text"] = new_text

        async with async_session() as session:
            await session.execute(
                update(Chat)
                .where(Chat.chat_id == chat.chat_id)
                .values(channel_post_buttons=buttons_to_json(buttons))
            )
            await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Текст кнопки изменён на: {new_text}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ К кнопкам",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("post_msg:btn_edit_url:"))
async def callback_edit_button_url(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Запрос новой ссылки кнопки."""
    idx = int(callback.data.split(":")[2])
    await state.update_data(editing_button_idx=idx)
    await state.set_state(PostMessageStates.editing_button_url)

    await callback.message.edit_text(
        "🔗 <b>Введите новую ссылку:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(PostMessageStates.editing_button_url))
async def process_edit_button_url(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка новой ссылки кнопки."""
    if not message.text:
        await message.answer("❌ Отправьте ссылку")
        return

    new_url = message.text.strip()

    if not new_url.startswith(("http://", "https://", "tg://")):
        await message.answer(
            "❌ Некорректная ссылка. Должна начинаться с http://, https:// или tg://"
        )
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer("❌ Чат не найден")
        await state.clear()
        return

    data = await state.get_data()
    idx = data.get("editing_button_idx", 0)

    buttons = get_buttons_from_json(chat.channel_post_buttons)
    if idx < len(buttons):
        buttons[idx]["url"] = new_url

        async with async_session() as session:
            await session.execute(
                update(Chat)
                .where(Chat.chat_id == chat.chat_id)
                .values(channel_post_buttons=buttons_to_json(buttons))
            )
            await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Ссылка изменена на: {new_url}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ К кнопкам",
                        callback_data="post_msg:buttons",
                    )
                ]
            ]
        ),
    )
