"""Основная панель управления."""

import contextlib

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.common.keyboards import get_panel_keyboard, get_settings_keyboard
from src.database.models import Chat
from src.handlers.admin_panel.utils import (
    deactivate_chat,
    get_admin_chat,
    toggle_chat_closed,
)

router = Router(name="panel_main")


async def get_panel_text(chat: Chat, bot: Bot) -> str:
    """Формирует текст панели управления."""
    try:
        tg_chat = await bot.get_chat(chat.chat_id)
        member_count = await bot.get_chat_member_count(chat.chat_id)
        title = tg_chat.title or "Без названия"
    except Exception:
        title = chat.title or "Без названия"
        member_count = "?"

    status = "🔒 Закрыт" if chat.is_closed else "🔓 Открыт"

    return (
        f"🎛 <b>Панель управления</b>\n\n"
        f"📍 <b>Чат:</b> {title}\n"
        f"📊 <b>Статус:</b> {status}\n"
        f"👥 <b>Участников:</b> {member_count}\n"
        f"✅ <b>Бот работает</b>"
    )


@router.message(Command("panel"))
async def cmd_panel(message: types.Message, bot: Bot) -> None:
    """Команда /panel - открытие панели управления."""
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


@router.callback_query(F.data == "open_panel")
async def callback_open_panel(callback: types.CallbackQuery, bot: Bot) -> None:
    """Открытие панели управления по кнопке из /start."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer(
            "❌ У вас нет активного чата.\n"
            "Добавьте бота в чат и выполните /setup",
            show_alert=True,
        )
        return

    text = await get_panel_text(chat, bot)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_panel_keyboard(chat),
    )
    await callback.answer()


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

    # Обновляем меню настроек
    chat = await get_admin_chat(user_id)
    if chat:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                "⚙️ <b>Настройки бота</b>\n\n"
                "Здесь вы можете настроить параметры бота.",
                parse_mode="HTML",
                reply_markup=get_settings_keyboard(chat),
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
                        text="❌ Отмена", callback_data="panel:settings"
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

    with contextlib.suppress(Exception):
        await bot.leave_chat(chat.chat_id)

    await deactivate_chat(chat.chat_id)

    await callback.message.edit_text(
        "✅ Бот деактивирован.\n\n"
        "Чтобы использовать бота снова, добавьте его в чат и выполните /setup",
        parse_mode="HTML",
    )
    await callback.answer()
