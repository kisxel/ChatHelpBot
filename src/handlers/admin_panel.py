"""Панель управления для администратора в ЛС."""

import contextlib
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, func, select, update

from src.database.core import async_session
from src.database.models import Chat, MessageStats, UserFilter

router = Router()


class FilterStates(StatesGroup):
    """Состояния для настройки фильтров."""

    waiting_user_id = State()
    waiting_filter_type = State()
    waiting_pattern = State()


async def get_admin_chat(user_id: int) -> Chat | None:
    """Получает чат, где пользователь является админом (активатором)."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.activated_by == user_id, Chat.is_active)
        )
        return result.scalar_one_or_none()


async def get_chat_stats(chat_id: int) -> dict:
    """Получает статистику чата за последние 7 дней."""
    week_ago = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
    async with async_session() as session:
        result = await session.execute(
            select(func.sum(MessageStats.message_count)).where(
                MessageStats.chat_id == chat_id, MessageStats.date >= week_ago
            )
        )
        messages_week = result.scalar() or 0
        return {"messages_week": messages_week}


async def deactivate_chat(chat_id: int) -> None:
    """Деактивирует чат."""
    async with async_session() as session:
        await session.execute(
            update(Chat).where(Chat.chat_id == chat_id).values(is_active=False)
        )
        await session.commit()


async def toggle_chat_closed(chat_id: int, closed: bool) -> None:
    """Открывает или закрывает чат."""
    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat_id)
            .values(is_closed=closed)
        )
        await session.commit()


def get_panel_keyboard(chat: Chat) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру панели управления."""
    closed_text = "🔓 Открыть чат" if chat.is_closed else "🔒 Закрыть чат"
    closed_action = "open" if chat.is_closed else "close"

    buttons = [
        [
            InlineKeyboardButton(
                text=closed_text,
                callback_data=f"panel:toggle:{closed_action}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Фильтры сообщений",
                callback_data="panel:filters",
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="panel:stats",
            )
        ],
        [
            InlineKeyboardButton(
                text="🚪 Деактивировать бота",
                callback_data="panel:deactivate",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Обновить", callback_data="panel:refresh"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_filters_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру управления фильтрами."""
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить фильтр",
                callback_data="panel:filter_add",
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Список фильтров",
                callback_data="panel:filter_list",
            )
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_panel_text(chat: Chat, bot: Bot) -> str:
    """Формирует текст панели управления."""
    try:
        tg_chat = await bot.get_chat(chat.chat_id)
        member_count = await bot.get_chat_member_count(chat.chat_id)
        title = tg_chat.title or "Без названия"
    except Exception:
        title = chat.title or "Без названия"
        member_count = "?"

    stats = await get_chat_stats(chat.chat_id)
    status = "🔒 Закрыт" if chat.is_closed else "🔓 Открыт"

    return (
        f"🎛 <b>Панель управления</b>\n\n"
        f"📍 <b>Чат:</b> {title}\n"
        f"📊 <b>Статус:</b> {status}\n"
        f"👥 <b>Участников:</b> {member_count}\n"
        f"💬 <b>Сообщений за 7 дней:</b> {stats['messages_week']}\n"
        f"✅ <b>Бот работает</b>"
    )


@router.message(Command("panel"))
async def cmd_panel(message: types.Message, bot: Bot) -> None:
    """Команда для открытия панели управления."""
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(
            "❌ Панель управления доступна только в ЛС с ботом."
        )
        return

    user_id = message.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await message.answer(
            "❌ У вас нет активного чата.\n"
            "Добавьте бота в чат и выполните /setup"
        )
        return

    text = await get_panel_text(chat, bot)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_panel_keyboard(chat),
    )


@router.callback_query(F.data == "panel:refresh")
async def callback_panel_refresh(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Обновление панели."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    text = await get_panel_text(chat, bot)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_panel_keyboard(chat),
        )
    await callback.answer("✅ Обновлено")


@router.callback_query(F.data == "panel:main")
async def callback_panel_main(callback: types.CallbackQuery, bot: Bot) -> None:
    """Возврат к главной панели."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    text = await get_panel_text(chat, bot)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_panel_keyboard(chat),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("panel:toggle:"))
async def callback_toggle_chat(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Открытие/закрытие чата."""
    action = callback.data.split(":")[2]
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    closed = action == "close"
    await toggle_chat_closed(chat.chat_id, closed)

    try:
        if closed:
            await bot.set_chat_permissions(
                chat.chat_id,
                types.ChatPermissions(can_send_messages=False),
            )
            await callback.answer("🔒 Чат закрыт")
        else:
            await bot.set_chat_permissions(
                chat.chat_id,
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
            await callback.answer("🔓 Чат открыт")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
        return

    # Обновляем панель
    chat = await get_admin_chat(user_id)
    if chat:
        text = await get_panel_text(chat, bot)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_panel_keyboard(chat),
            )


@router.callback_query(F.data == "panel:deactivate")
async def callback_deactivate(callback: types.CallbackQuery, bot: Bot) -> None:
    """Подтверждение деактивации."""
    await callback.message.edit_text(
        "⚠️ <b>Вы уверены?</b>\n\n"
        "Бот будет деактивирован в чате.\n"
        "Вы сможете активировать его снова командой /setup",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, деактивировать",
                        callback_data="panel:deactivate_confirm",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="panel:main"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "panel:deactivate_confirm")
async def callback_deactivate_confirm(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Деактивация бота."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    # Уходим из чата
    with contextlib.suppress(Exception):
        await bot.leave_chat(chat.chat_id)

    await deactivate_chat(chat.chat_id)

    await callback.message.edit_text(
        "✅ Бот деактивирован.\n\n"
        "Чтобы использовать бота снова, добавьте его в чат и выполните /setup",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "panel:filters")
async def callback_filters_menu(callback: types.CallbackQuery) -> None:
    """Меню фильтров сообщений."""
    await callback.message.edit_text(
        "⚙️ <b>Фильтры сообщений</b>\n\n"
        "Здесь вы можете настроить автоматическое удаление "
        "сообщений отдельных пользователей.\n\n"
        "<b>Типы фильтров:</b>\n"
        "• <b>Блокировать</b> — удалять сообщения содержащие паттерн\n"
        "• <b>Только разрешить</b> — удалять сообщения НЕ содержащие паттерн",
        parse_mode="HTML",
        reply_markup=get_filters_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "panel:filter_add")
async def callback_filter_add(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Начало добавления фильтра."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    await state.update_data(filter_chat_id=chat.chat_id)
    await state.set_state(FilterStates.waiting_user_id)

    await callback.message.edit_text(
        "👤 <b>Добавление фильтра</b>\n\n"
        "Введите ID пользователя, для которого нужно настроить фильтр:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="panel:filters",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(FilterStates.waiting_user_id))
async def process_filter_user_id(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка ввода ID пользователя."""
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя (число)")
        return

    user_id = int(message.text)
    await state.update_data(filter_user_id=user_id)
    await state.set_state(FilterStates.waiting_filter_type)

    await message.answer(
        f"👤 <b>Пользователь:</b> {user_id}\n\nВыберите тип фильтра:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚫 Блокиро��ать содержащие",
                        callback_data="filter_type:block",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Только разрешить содержащие",
                        callback_data="filter_type:allow",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="panel:filters_cancel",
                    )
                ],
            ]
        ),
    )


@router.callback_query(F.data == "panel:filters_cancel")
async def callback_filters_cancel(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Отмена добавления фильтра."""
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Фильтры сообщений</b>\n\n"
        "Здесь вы можете настроить автоматическое удаление "
        "сообщений отдельных пользователей.\n\n"
        "<b>Типы фильтров:</b>\n"
        "• <b>Блокировать</b> — удалять сообщения содержащие паттерн\n"
        "• <b>Только разрешить</b> — удалять сообщения НЕ содержащие паттерн",
        parse_mode="HTML",
        reply_markup=get_filters_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("filter_type:"),
    StateFilter(FilterStates.waiting_filter_type),
)
async def process_filter_type(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Обработка выбора типа фильтра."""
    filter_type = callback.data.split(":")[1]
    await state.update_data(filter_type=filter_type)
    await state.set_state(FilterStates.waiting_pattern)

    type_text = (
        "удалять сообщения <b>содержащие</b>"
        if filter_type == "block"
        else "удалять сообщения <b>НЕ содержащие</b>"
    )

    await callback.message.edit_text(
        f"Бот будет {type_text} указанный текст.\n\n"
        "Введите паттерн (текст) для фильтрации:\n"
        "<i>Несколько вариантов через запятую: слово1, слово2</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(FilterStates.waiting_pattern))
async def process_filter_pattern(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка ввода паттерна фи��ьтра."""
    if not message.text:
        await message.answer("❌ Введите текст для фильтрации")
        return

    pattern = message.text.strip()
    data = await state.get_data()

    chat_id = data["filter_chat_id"]
    user_id = data["filter_user_id"]
    filter_type = data["filter_type"]

    async with async_session() as session:
        new_filter = UserFilter(
            chat_id=chat_id,
            user_id=user_id,
            filter_type=filter_type,
            pattern=pattern,
            is_active=True,
        )
        session.add(new_filter)
        await session.commit()

    await state.clear()

    type_text = "блокировать" if filter_type == "block" else "разрешать только"

    await message.answer(
        f"✅ <b>Фильтр добавлен!</b>\n\n"
        f"👤 Пользователь: {user_id}\n"
        f"📝 Тип: {type_text}\n"
        f"🔤 Паттерн: {pattern}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ К фильтрам",
                        callback_data="panel:filters",
                    )
                ]
            ]
        ),
    )


@router.callback_query(F.data == "panel:filter_list")
async def callback_filter_list(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Список фильтров чата."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(UserFilter).where(
                UserFilter.chat_id == chat.chat_id, UserFilter.is_active
            )
        )
        filters = list(result.scalars().all())

    if not filters:
        await callback.message.edit_text(
            "📋 <b>Список фильтров</b>\n\n<i>Фильтры не настроены</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад", callback_data="panel:filters"
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return

    text = "📋 <b>Список фильтров</b>\n\n"
    buttons = []

    for f in filters:
        type_emoji = "🚫" if f.filter_type == "block" else "✅"
        # Пробуем получить имя пользователя
        try:
            tg_user = await bot.get_chat(f.user_id)
            user_name = tg_user.full_name or tg_user.username or str(f.user_id)
        except Exception:
            user_name = str(f.user_id)

        text += f"{type_emoji} {f.user_id} ({user_name}): <code>{f.pattern[:20]}</code>\n"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить #{f.id}",
                    callback_data=f"panel:filter_del:{f.id}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:filters")]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("panel:filter_del:"))
async def callback_filter_delete(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Удаление фильтра."""
    filter_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        await session.execute(
            delete(UserFilter).where(UserFilter.id == filter_id)
        )
        await session.commit()

    await callback.answer("✅ Фильтр удалён")

    # Обновляем список фильтров
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        return

    async with async_session() as session:
        result = await session.execute(
            select(UserFilter).where(
                UserFilter.chat_id == chat.chat_id, UserFilter.is_active
            )
        )
        filters = list(result.scalars().all())

    if not filters:
        await callback.message.edit_text(
            "📋 <b>Список фильтров</b>\n\n<i>Фильтры не настроены</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад", callback_data="panel:filters"
                        )
                    ]
                ]
            ),
        )
        return

    text = "📋 <b>Список фильтров</b>\n\n"
    buttons = []

    for f in filters:
        type_emoji = "🚫" if f.filter_type == "block" else "✅"
        try:
            tg_user = await bot.get_chat(f.user_id)
            user_name = tg_user.full_name or tg_user.username or str(f.user_id)
        except Exception:
            user_name = str(f.user_id)

        text += f"{type_emoji} {f.user_id} ({user_name}): <code>{f.pattern[:20]}</code>\n"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить #{f.id}",
                    callback_data=f"panel:filter_del:{f.id}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:filters")]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data == "panel:stats")
async def callback_chat_stats(callback: types.CallbackQuery, bot: Bot) -> None:
    """Статистика чата."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    try:
        tg_chat = await bot.get_chat(chat.chat_id)
        member_count = await bot.get_chat_member_count(chat.chat_id)
        title = tg_chat.title or "Без названия"
    except Exception:
        title = chat.title or "Без названия"
        member_count = "?"

    stats = await get_chat_stats(chat.chat_id)

    async with async_session() as session:
        result = await session.execute(
            select(func.count(UserFilter.id)).where(
                UserFilter.chat_id == chat.chat_id, UserFilter.is_active
            )
        )
        filters_count = result.scalar() or 0

    text = (
        f"📊 <b>Статистика: {title}</b>\n\n"
        f"👥 <b>Участников:</b> {member_count}\n"
        f"💬 <b>Сообщений за 7 дней:</b> {stats['messages_week']}\n"
        f"⚙️ <b>Активных фильтров:</b> {filters_count}\n"
        f"📅 <b>Активирован:</b> {chat.activated_at}"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад", callback_data="panel:main"
                    )
                ]
            ]
        ),
    )
    await callback.answer()
