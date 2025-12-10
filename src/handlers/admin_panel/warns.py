"""Управление варнами в панели администратора."""

import contextlib

from aiogram import Bot, F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, distinct, func, or_, select

from src.database.core import async_session
from src.database.models import Warn
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="panel_warns")

# Минимальное количество частей callback_data для username
MIN_PARTS_FOR_USERNAME = 4


def get_warns_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру управления варнами."""
    buttons = [
        [
            InlineKeyboardButton(
                text="📋 Список пользователей с варнами",
                callback_data="warns:list",
            )
        ],
        [
            InlineKeyboardButton(
                text="🧹 Снять все варны в чате",
                callback_data="warns:remove_all",
            )
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_warns_stats(chat_id: int) -> dict:
    """Получает статистику варнов в чате."""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(Warn.id)).where(Warn.chat_id == chat_id)
        )
        total_warns = result.scalar() or 0

        result = await session.execute(
            select(func.count(distinct(Warn.user_id))).where(
                Warn.chat_id == chat_id
            )
        )
        users_with_warns = result.scalar() or 0

    return {
        "total_warns": total_warns,
        "users_with_warns": users_with_warns,
    }


@router.callback_query(F.data == "panel:warns")
async def callback_warns_menu(callback: types.CallbackQuery, bot: Bot) -> None:
    """Меню управления варнами."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    stats = await get_warns_stats(chat.chat_id)

    await callback.message.edit_text(
        f"⚠️ <b>Управление варнами</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего варнов: {stats['total_warns']}\n"
        f"• Пользователей с варнами: {stats['users_with_warns']}\n\n"
        f"ℹ️ После 3 варнов пользователь получает бан.",
        parse_mode="HTML",
        reply_markup=get_warns_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "warns:list")
async def callback_warns_list(callback: types.CallbackQuery, bot: Bot) -> None:
    """Список пользователей с варнами."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    async with async_session() as session:
        # Получаем уникальных пользователей - группируем по user_id
        # Используем COALESCE чтобы объединить записи с одинаковым user_id
        result = await session.execute(
            select(
                func.coalesce(Warn.user_id, 0).label("uid"),
                func.max(Warn.username).label("uname"),
                func.count(Warn.id).label("warn_count"),
            )
            .where(Warn.chat_id == chat.chat_id)
            .group_by(func.coalesce(Warn.user_id, Warn.username))
            .order_by(func.count(Warn.id).desc())
            .limit(20)
        )
        users_warns = result.all()

    if not users_warns:
        await callback.message.edit_text(
            "📋 <b>Список варнов</b>\n\n<i>Нет пользователей с варнами</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад", callback_data="panel:warns"
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return

    text = "📋 <b>Пользователи с варнами</b>\n\n"
    buttons = []

    for uid, uname, warn_count in users_warns:
        user_id_db = uid if uid != 0 else None
        username_db = uname

        user_name = None
        if user_id_db:
            try:
                tg_user = await bot.get_chat(user_id_db)
                user_name = tg_user.full_name or tg_user.username
            except Exception:
                pass

        if not user_name:
            user_name = f"@{username_db}" if username_db else str(user_id_db)

        # Формируем callback_data с user_id и username
        cb_data = f"warns:clear:{user_id_db or 0}:{username_db or ''}"
        text += f"• {user_name} — <b>{warn_count}/3</b> варнов\n"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Снять варны: {user_name[:20]}",
                    callback_data=cb_data,
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:warns")]
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("warns:clear:"))
async def callback_warns_clear_user(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Снять варны с конкретного пользователя."""
    parts = callback.data.split(":")
    target_user_id_str = parts[2]
    target_username = (
        parts[3] if len(parts) >= MIN_PARTS_FOR_USERNAME else None
    )

    target_user_id = (
        int(target_user_id_str) if target_user_id_str != "0" else None
    )
    if target_username == "":
        target_username = None

    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    async with async_session() as session:
        # Строим условия для поиска
        conditions = [Warn.chat_id == chat.chat_id]
        if target_user_id and target_username:
            conditions.append(
                or_(
                    Warn.user_id == target_user_id,
                    Warn.username == target_username,
                )
            )
        elif target_user_id:
            conditions.append(Warn.user_id == target_user_id)
        elif target_username:
            conditions.append(Warn.username == target_username)

        result = await session.execute(
            select(func.count(Warn.id)).where(*conditions)
        )
        count = result.scalar() or 0

        await session.execute(delete(Warn).where(*conditions))
        await session.commit()

    # Определяем имя пользователя
    user_name = None
    if target_user_id:
        try:
            tg_user = await bot.get_chat(target_user_id)
            user_name = tg_user.full_name
        except Exception:
            pass

    if not user_name:
        user_name = (
            f"@{target_username}" if target_username else str(target_user_id)
        )

    await callback.answer(f"✅ Снято {count} варнов с {user_name}")

    # Обновляем список
    await callback_warns_list(callback, bot)


@router.callback_query(F.data == "warns:remove_all")
async def callback_warns_remove_all(callback: types.CallbackQuery) -> None:
    """Подтверждение снятия всех варнов."""
    await callback.message.edit_text(
        "⚠️ <b>Вы уверены?</b>\n\n"
        "Будут удалены все варны всех пользователей в чате.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, удалить все",
                        callback_data="warns:remove_all_confirm",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="panel:warns"
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "warns:remove_all_confirm")
async def callback_warns_remove_all_confirm(
    callback: types.CallbackQuery, bot: Bot
) -> None:
    """Удаление всех варнов в чате."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(func.count(Warn.id)).where(Warn.chat_id == chat.chat_id)
        )
        count = result.scalar() or 0

        await session.execute(delete(Warn).where(Warn.chat_id == chat.chat_id))
        await session.commit()

    # Отправляем поздравление в чат если были варны
    if count > 0:
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat.chat_id,
                "🎉 <b>День амнистии!</b>\n\n"
                "Все предупреждения в чате были сняты.\n",
                parse_mode="HTML",
            )

    await callback.answer(f"✅ Удалено {count} варнов")

    stats = await get_warns_stats(chat.chat_id)

    await callback.message.edit_text(
        f"⚠️ <b>Управление варнами</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего варнов: {stats['total_warns']}\n"
        f"• Пользователей с варнами: {stats['users_with_warns']}\n\n"
        f"ℹ️ После 3 варнов пользователь получает бан.",
        parse_mode="HTML",
        reply_markup=get_warns_keyboard(),
    )
