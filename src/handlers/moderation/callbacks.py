"""Callback-обработчики кнопок модерации."""

from aiogram import Bot, F, Router, types

from src.common.permissions import is_user_admin
from src.handlers.moderation.utils import get_unmute_permissions

router = Router(name="moderation_callbacks")


@router.callback_query(F.data.startswith("unban:"))
async def callback_unban(callback: types.CallbackQuery, bot: Bot) -> None:
    """Обработчик кнопки разбана."""
    if not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    chat_id = callback.message.chat.id

    if not await is_user_admin(chat_id, callback.from_user.id, bot):
        await callback.answer("❌ Только администраторы", show_alert=True)
        return

    try:
        user_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    try:
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        await callback.answer("✅ Пользователь разбанен")

        if callback.message.text:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <i>Разбанен</i>",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("unmute:"))
async def callback_unmute(callback: types.CallbackQuery, bot: Bot) -> None:
    """Обработчик кнопки размута."""
    if not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    chat_id = callback.message.chat.id

    if not await is_user_admin(chat_id, callback.from_user.id, bot):
        await callback.answer("❌ Только администраторы", show_alert=True)
        return

    try:
        user_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    try:
        await bot.restrict_chat_member(
            chat_id, user_id, permissions=get_unmute_permissions()
        )
        await callback.answer("✅ Мут снят")

        if callback.message.text:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <i>Мут снят</i>",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
