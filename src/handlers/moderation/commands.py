"""Команды модерации: /ban, /mute, /kick, /unban, /unmute."""

from datetime import UTC, datetime, timedelta

from aiogram import Bot, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command

from src.common.keyboards import get_unban_keyboard, get_unmute_keyboard
from src.common.permissions import can_bot_restrict, is_user_admin
from src.handlers.moderation.utils import (
    MIN_MUTE_SECONDS,
    are_moderation_cmds_enabled,
    build_action_message,
    check_admin_permissions,
    check_target_user,
    get_mute_permissions,
    get_unmute_permissions,
)
from src.utils import parse_timedelta

router = Router(name="moderation_commands")


async def get_target_user(
    message: types.Message,
    bot: Bot,
) -> tuple[int | None, str | None]:
    """Получает ID и имя целевого пользователя из сообщения."""
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.full_name

    args = message.text.split()[1:] if message.text else []
    if not args:
        return None, None

    first_arg = args[0]

    # Проверяем ID
    if first_arg.isdigit():
        return int(first_arg), f"ID:{first_arg}"

    # Проверяем @username
    if first_arg.startswith("@"):
        try:
            chat = await bot.get_chat(first_arg)
            if chat.id:
                name = chat.full_name or chat.username or first_arg
                return chat.id, name
        except Exception:
            pass

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


# ==================== БАН ====================


@router.message(Command("ban"))
async def cmd_ban(message: types.Message, bot: Bot) -> None:
    """Бан пользователя: /ban [время] [причина]."""
    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    error = await check_admin_permissions(
        message, bot, "❌ У меня нет прав на блокировку пользователей."
    )
    if error:
        await message.answer(error)
        return

    user_id, user_name = await get_target_user(message, bot)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите @username/ID"
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

        response = build_action_message(action, user_name, duration, reason)
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_unban_keyboard(user_id),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при бане: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message, bot: Bot) -> None:
    """Разбан пользователя: /unban."""
    if not await are_moderation_cmds_enabled(message.chat.id):
        return

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

    user_id, user_name = await get_target_user(message, bot)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите @username/ID"
        )
        return

    try:
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        await message.answer(
            f"✅ <b>Разбан</b>\n👤 Пользователь: {user_name}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при разбане: {e}")


# ==================== МУТ ====================


@router.message(Command("mute"))
async def cmd_mute(message: types.Message, bot: Bot) -> None:
    """Мут пользователя: /mute [время] [причина]."""
    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    error = await check_admin_permissions(
        message, bot, "❌ У меня нет прав на ограничение пользователей."
    )
    if error:
        await message.answer(error)
        return

    user_id, user_name = await get_target_user(message, bot)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите @username/ID"
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

        response = build_action_message(action, user_name, duration, reason)
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_unmute_keyboard(user_id),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при муте: {e}")


@router.message(Command("unmute"))
async def cmd_unmute(message: types.Message, bot: Bot) -> None:
    """Снятие мута: /unmute."""
    if not await are_moderation_cmds_enabled(message.chat.id):
        return

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

    user_id, user_name = await get_target_user(message, bot)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите @username/ID"
        )
        return

    try:
        await bot.restrict_chat_member(
            chat_id, user_id, permissions=get_unmute_permissions()
        )
        await message.answer(
            f"🔊 <b>Мут снят</b>\n👤 Пользователь: {user_name}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при снятии мута: {e}")


# ==================== КИК ====================


@router.message(Command("kick"))
async def cmd_kick(message: types.Message, bot: Bot) -> None:
    """Кик пользователя: /kick [причина]."""
    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    error = await check_admin_permissions(
        message, bot, "❌ У меня нет прав на кик пользователей."
    )
    if error:
        await message.answer(error)
        return

    user_id, user_name = await get_target_user(message, bot)
    if not user_id:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или укажите @username/ID"
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
            reason=reason,
        )
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при кике: {e}")
