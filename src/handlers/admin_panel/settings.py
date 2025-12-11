"""Настройки бота."""

import contextlib

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import update

from src.common.keyboards import get_settings_keyboard
from src.database.core import async_session
from src.database.models import Chat
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="panel_settings")


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
