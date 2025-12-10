"""Управление фильтрами сообщений."""

import contextlib

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, select, update

from src.common.keyboards import get_filters_keyboard
from src.database.core import async_session
from src.database.models import UserFilter
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="panel_filters")


class FilterStates(StatesGroup):
    """Состояния для настройки фильтров."""

    waiting_user_id = State()
    waiting_filter_type = State()
    waiting_pattern = State()
    editing_pattern = State()


@router.callback_query(F.data == "panel:filters")
async def callback_filters_menu(callback: types.CallbackQuery) -> None:
    """Меню фильтров сообщений."""
    await callback.message.edit_text(
        "⚙️ <b>Фильтры сообщений</b>\n\n"
        "Здесь вы можете настроить автоматическое удаление "
        "сообщений отдельных пользователей.\n\n"
        "<b>Типы фильтров:</b>\n"
        "• <b>Блокировать</b> — удалять сообщения содержащие паттерн\n"
        "• <b>Разрешить только</b> — удалять сообщения НЕ содержащие паттерн",
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
                        text="🚫 Блокировать содержащие",
                        callback_data="filter_type:block",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Разрешить только содержащие",
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
        "• <b>Разрешить только</b> — удалять сообщения НЕ содержащие паттерн",
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
    """Обработка ввода паттерна фильтра."""
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


async def build_filter_list_view(
    filters: list, bot: Bot
) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """Строит текст и кнопки для списка фильтров."""
    text = "📋 <b>Список фильтров</b>\n\n"
    buttons = []

    for idx, f in enumerate(filters, 1):
        type_emoji = "🚫" if f.filter_type == "block" else "✅"
        notify_emoji = "🔔" if f.notify else "🔕"

        try:
            tg_user = await bot.get_chat(f.user_id)
            user_name = tg_user.full_name or tg_user.username or str(f.user_id)
        except Exception:
            user_name = str(f.user_id)

        text += (
            f"<b>{idx}.</b> {type_emoji} {f.user_id} ({user_name}): "
            f"<code>{f.pattern[:20]}</code> {notify_emoji}\n"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{idx}. ✏️",
                    callback_data=f"panel:filter_edit:{f.id}",
                ),
                InlineKeyboardButton(
                    text=f"{idx}. {notify_emoji}",
                    callback_data=f"panel:filter_notify:{f.id}",
                ),
                InlineKeyboardButton(
                    text=f"{idx}. 🗑",
                    callback_data=f"panel:filter_del:{f.id}",
                ),
            ]
        )

    return text, buttons


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

    text, buttons = await build_filter_list_view(filters, bot)
    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:filters")]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("panel:filter_notify:"))
async def callback_filter_notify_toggle(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Переключение уведомлений для конкретного фильтра."""
    filter_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        result = await session.execute(
            select(UserFilter).where(UserFilter.id == filter_id)
        )
        f = result.scalar_one_or_none()
        if f:
            new_value = not f.notify
            await session.execute(
                update(UserFilter)
                .where(UserFilter.id == filter_id)
                .values(notify=new_value)
            )
            await session.commit()
            status = "включены" if new_value else "выключены"
            await callback.answer(f"🔔 Уведомления {status}")
        else:
            await callback.answer("❌ Фильтр не найден", show_alert=True)
            return

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

    text, buttons = await build_filter_list_view(filters, bot)
    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:filters")]
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )


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

    text, buttons = await build_filter_list_view(filters, bot)
    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:filters")]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("panel:filter_edit:"))
async def callback_filter_edit(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    """Начало редактирования паттерна фильтра."""
    filter_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        result = await session.execute(
            select(UserFilter).where(UserFilter.id == filter_id)
        )
        f = result.scalar_one_or_none()

    if not f:
        await callback.answer("❌ Фильтр не найден", show_alert=True)
        return

    await state.update_data(editing_filter_id=filter_id)
    await state.set_state(FilterStates.editing_pattern)

    await callback.message.edit_text(
        f"✏️ <b>Редактирование фильтра #{filter_id}</b>\n\n"
        f"Текущий паттерн: <code>{f.pattern}</code>\n\n"
        "Введите новый паттерн:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="panel:filter_list",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(FilterStates.editing_pattern))
async def process_filter_edit_pattern(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка нового паттерна фильтра."""
    if not message.text:
        await message.answer("❌ Введите текст для фильтрации")
        return

    data = await state.get_data()
    filter_id = data.get("editing_filter_id")

    if not filter_id:
        await state.clear()
        await message.answer("❌ Ошибка: фильтр не найден")
        return

    new_pattern = message.text.strip()

    async with async_session() as session:
        await session.execute(
            update(UserFilter)
            .where(UserFilter.id == filter_id)
            .values(pattern=new_pattern)
        )
        await session.commit()

    await state.clear()

    await message.answer(
        f"✅ <b>Фильтр обновлён!</b>\n\n"
        f"Новый паттерн: <code>{new_pattern}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📋 К списку фильтров",
                        callback_data="panel:filter_list",
                    )
                ]
            ]
        ),
    )
