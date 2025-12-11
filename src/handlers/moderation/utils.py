"""Общие утилиты для модерации."""

from datetime import timedelta

from aiogram import Bot, types
from aiogram.enums import ChatType
from sqlalchemy import select

from src.common.permissions import can_bot_restrict, is_user_admin
from src.database.core import async_session
from src.database.models import Chat
from src.utils import format_timedelta

# Минимальное время мута (30 секунд)
MIN_MUTE_SECONDS = 30


def get_mute_permissions() -> types.ChatPermissions:
    """Возвращает права для замьюченного пользователя."""
    return types.ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )


def get_unmute_permissions() -> types.ChatPermissions:
    """Возвращает стандартные права пользователя."""
    return types.ChatPermissions(
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
    )


def build_action_message(
    action: str,
    user_name: str,
    duration: timedelta | None = None,
    reason: str | None = None,
) -> str:
    """Формирует сообщение о действии модератора."""
    text = f"{action}\n👤 Пользователь: {user_name}"
    if duration:
        text += f"\n⏱ Срок: {format_timedelta(duration)}"
    if reason:
        text += f"\n📝 Причина: {reason}"
    return text


async def check_admin_permissions(
    message: types.Message,
    bot: Bot,
    error_msg: str,
) -> str | None:
    """Проверяет права админа и бота. Возвращает ошибку или None."""
    if message.chat.type == ChatType.PRIVATE:
        return "❌ Эта команда работает только в групповых чатах."

    if not await is_user_admin(message.chat.id, message.from_user.id, bot):
        return "❌ У вас нет прав администратора."

    if not await can_bot_restrict(message.chat.id, bot):
        return error_msg

    return None


async def check_target_user(
    message: types.Message,
    bot: Bot,
    user_id: int,
    action_name: str,
) -> str | None:
    """Проверяет целевого пользователя. Возвращает ошибку или None."""
    if user_id == message.from_user.id:
        return f"❌ Вы не можете {action_name} себя."

    if user_id == bot.id:
        return f"❌ Вы не можете {action_name} меня."

    if await is_user_admin(message.chat.id, user_id, bot):
        return f"❌ Нельзя {action_name} администратора."

    return None


async def are_moderation_cmds_enabled(chat_id: int) -> bool:
    """Проверяет, включены ли команды модерации для чата."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            return chat.enable_moderation_cmds
        return True


async def are_report_cmds_enabled(chat_id: int) -> bool:
    """Проверяет, включены ли команды репортов для чата."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            return chat.enable_report_cmds
        return True
