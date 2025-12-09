"""Обработчики команд модерации: бан, мут, кик."""

from datetime import UTC, datetime, timedelta

from aiogram import Bot, Router, types
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command

from src.utils import format_timedelta, parse_timedelta

router = Router()

MIN_MUTE_SECONDS = 30


async def is_user_admin(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Проверяет, является ли пользователь администратором чата."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except Exception:
        return False


async def can_bot_restrict(chat_id: int, bot: Bot) -> bool:
    """Проверяет, может ли бот ограничивать пользователей."""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if isinstance(bot_member, types.ChatMemberAdministrator):
            return bot_member.can_restrict_members
        return False
    except Exception:
        return False


async def get_target_user(
    message: types.Message,
) -> tuple[int | None, str | None]:
    """Получает ID и имя целевого пользователя из сообщения."""
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.full_name

    args = message.text.split()[1:] if message.text else []
    if not args:
        return None, None

    first_arg = args[0]
    if first_arg.isdigit():
        return int(first_arg), f"ID:{first_arg}"

    return None, None


def parse_command_args(
    message: types.Message,
) -> tuple[timedelta | None, str | None]:
    """Парсит аргументы команды для получения времени и причины."""
    args = message.text.split()[1:] if message.text else []
    start_idx = 0 if message.reply_to_message else 1

    if len(args) <= start_idx:
        return None, None

    remaining_args = args[start_idx:]
    if not remaining_args:
        return None, None

    duration = parse_timedelta(remaining_args[0])
    if duration:
        reason = (
            " ".join(remaining_args[1:]) if len(remaining_args) > 1 else None
        )
    else:
        reason = " ".join(remaining_args) if remaining_args else None

    return duration, reason


def build_action_message(
    action: str,
    user_name: str,
    admin_name: str,
    duration: timedelta | None = None,
    reason: str | None = None,
) -> str:
    """Формирует сообщение о действии модератора."""
    text = f"{action}\n👤 Пользователь: {user_name}\n👮 Админ: {admin_name}"
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


# ==================== БАН ====================


@router.message(Command("ban"))
async def cmd_ban(message: types.Message, bot: Bot) -> None:
    """Бан пользователя: /ban [время] [причина]."""
    error = await check_admin_permissions(
        message, bot, "❌ У меня нет прав на блокировку пользователей."
    )
    if error:
        await message.answer(error)
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите ID: /ban <user_id>"
        )
        return

    error = await check_target_user(message, bot, user_id, "забанить")
    if error:
        await message.answer(error)
        return

    duration, reason = parse_command_args(message)

    try:
        if duration:
            until_date = datetime.now(UTC) + duration
            await bot.ban_chat_member(
                message.chat.id, user_id, until_date=until_date
            )
            action = "🚫 <b>Временный бан</b>"
        else:
            await bot.ban_chat_member(message.chat.id, user_id)
            action = "🚫 <b>Бан</b>"

        response = build_action_message(
            action, user_name, message.from_user.full_name, duration, reason
        )
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при бане: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message, bot: Bot) -> None:
    """Разбан пользователя: /unban."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах."
        )
        return

    chat_id = message.chat.id
    admin_id = message.from_user.id

    if not await is_user_admin(chat_id, admin_id, bot):
        await message.answer("❌ У вас нет прав администратора.")
        return

    if not await can_bot_restrict(chat_id, bot):
        await message.answer(
            "❌ У меня нет прав на управление пользователями."
        )
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите ID: /unban <user_id>"
        )
        return

    try:
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        await message.answer(
            f"✅ <b>Разбан</b>\n"
            f"👤 Пользователь: {user_name}\n"
            f"👮 Админ: {message.from_user.full_name}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при разбане: {e}")


# ==================== МУТ ====================


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


@router.message(Command("mute"))
async def cmd_mute(message: types.Message, bot: Bot) -> None:
    """Мут пользователя: /mute [время] [причина]."""
    error = await check_admin_permissions(
        message, bot, "❌ У меня нет прав на ограничение пользователей."
    )
    if error:
        await message.answer(error)
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите ID: /mute <user_id>"
        )
        return

    error = await check_target_user(message, bot, user_id, "замутить")
    if error:
        await message.answer(error)
        return

    duration, reason = parse_command_args(message)

    if duration and duration < timedelta(seconds=MIN_MUTE_SECONDS):
        await message.answer("❌ Минимальное время мута — 30 секунд.")
        return

    try:
        permissions = get_mute_permissions()
        if duration:
            until_date = datetime.now(UTC) + duration
            await bot.restrict_chat_member(
                message.chat.id,
                user_id,
                permissions=permissions,
                until_date=until_date,
            )
            action = "🔇 <b>Временный мут</b>"
        else:
            await bot.restrict_chat_member(
                message.chat.id, user_id, permissions=permissions
            )
            action = "🔇 <b>Мут</b>"

        response = build_action_message(
            action, user_name, message.from_user.full_name, duration, reason
        )
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при муте: {e}")


@router.message(Command("unmute"))
async def cmd_unmute(message: types.Message, bot: Bot) -> None:
    """Снятие мута: /unmute."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах."
        )
        return

    chat_id = message.chat.id
    admin_id = message.from_user.id

    if not await is_user_admin(chat_id, admin_id, bot):
        await message.answer("❌ У вас нет прав администратора.")
        return

    if not await can_bot_restrict(chat_id, bot):
        await message.answer(
            "❌ У меня нет прав на управление пользователями."
        )
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите ID: /unmute <user_id>"
        )
        return

    try:
        await bot.restrict_chat_member(
            chat_id, user_id, permissions=get_unmute_permissions()
        )
        await message.answer(
            f"🔊 <b>Мут снят</b>\n"
            f"👤 Пользователь: {user_name}\n"
            f"👮 Админ: {message.from_user.full_name}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при снятии мута: {e}")


# ==================== КИК ====================


@router.message(Command("kick"))
async def cmd_kick(message: types.Message, bot: Bot) -> None:
    """Кик пользователя: /kick [причина]."""
    error = await check_admin_permissions(
        message, bot, "❌ У меня нет прав на кик пользователей."
    )
    if error:
        await message.answer(error)
        return

    user_id, user_name = await get_target_user(message)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите ID: /kick <user_id>"
        )
        return

    error = await check_target_user(message, bot, user_id, "кикнуть")
    if error:
        await message.answer(error)
        return

    args = message.text.split()[1:] if message.text else []
    reason = (
        " ".join(args)
        if message.reply_to_message
        else " ".join(args[1:])
        if len(args) > 1
        else None
    )

    try:
        await bot.ban_chat_member(message.chat.id, user_id)
        await bot.unban_chat_member(
            message.chat.id, user_id, only_if_banned=True
        )
        response = build_action_message(
            "👢 <b>Кик</b>",
            user_name,
            message.from_user.full_name,
            reason=reason,
        )
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при кике: {e}")
