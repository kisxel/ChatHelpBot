"""Обработчики команд модерации: бан, мут, кик."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.utils import format_timedelta, parse_timedelta

router = Router()

MIN_MUTE_SECONDS = 30

# Анти-спам: хранение сообщений пользователей
# Формат: {(chat_id, user_id): [timestamp1, timestamp2, ...]}
user_messages: dict[tuple[int, int], list[datetime]] = defaultdict(list)

# Настройки анти-спама
SPAM_MAX_MESSAGES = 10  # Максимум сообщений
SPAM_TIME_WINDOW = 10  # За последние N секунд
SPAM_MUTE_DURATION = timedelta(minutes=5)  # Мут за спам

# Регулярные выражения для команд без слэша (русский язык)
# Только в начале строки и как отдельная команда
TEXT_CMD_PATTERN = re.compile(
    r"^(мут|бан|размут|разбан|кик)(?:\s+(.*))?$", re.IGNORECASE
)


@dataclass
class ModerationContext:
    """Контекст для команды модерации."""

    user_id: int
    user_name: str
    duration: timedelta | None = None
    reason: str | None = None


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
        return await _resolve_username(first_arg, bot)

    return None, None


async def _resolve_username(
    username_arg: str, bot: Bot
) -> tuple[int | None, str | None]:
    """Получает user_id по @username."""
    try:
        chat = await bot.get_chat(username_arg)
        if chat.id:
            name = chat.full_name or chat.username or username_arg
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


def get_unban_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой разбана."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔓 Разбанить",
                    callback_data=f"unban:{user_id}",
                )
            ]
        ]
    )


def get_unmute_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой размута."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔊 Размутить",
                    callback_data=f"unmute:{user_id}",
                )
            ]
        ]
    )


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


# ==================== ТЕКСТОВЫЕ КОМАНДЫ (без слэша) ====================


def parse_text_command_args(
    args_text: str,
    has_reply: bool,
) -> tuple[str | None, timedelta | None, str | None]:
    """
    Парсит аргументы текстовой команды.

    Возвращает: (user_arg, duration, reason)
    user_arg может быть ID или @username
    """
    if not args_text:
        return None, None, None

    parts = args_text.split()
    if not parts:
        return None, None, None

    user_arg = None
    start_idx = 0

    # Если нет ответа, первый аргумент - пользователь
    if not has_reply:
        user_arg = parts[0]
        start_idx = 1

    remaining = parts[start_idx:]
    if not remaining:
        return user_arg, None, None

    # Первый оставшийся аргумент - время
    duration = parse_timedelta(remaining[0])
    if duration:
        reason = " ".join(remaining[1:]) if len(remaining) > 1 else None
    else:
        reason = " ".join(remaining) if remaining else None
        duration = None

    return user_arg, duration, reason


@router.message(F.text.regexp(TEXT_CMD_PATTERN))
async def text_moderation_command(message: types.Message, bot: Bot) -> None:
    """Обработчик текстовых команд модерации без слэша."""
    if message.chat.type == ChatType.PRIVATE or not message.text:
        return

    match = TEXT_CMD_PATTERN.match(message.text)
    if not match:
        return

    command = match.group(1).lower()
    args_text = match.group(2) or ""

    # Проверяем права
    error = await _check_text_cmd_permissions(message, bot)
    if error:
        await message.answer(error)
        return

    # Получаем контекст модерации
    ctx = await _build_moderation_context(message, args_text, bot)
    if not ctx:
        await _send_usage_hint(message, command)
        return

    # Проверяем целевого пользователя
    error = await check_target_user(
        message, bot, ctx.user_id, _get_action_verb(command)
    )
    if error:
        await message.answer(error)
        return

    # Выполняем команду
    await _dispatch_command(message, bot, command, ctx)


async def _check_text_cmd_permissions(
    message: types.Message, bot: Bot
) -> str | None:
    """Проверяет права для текстовой команды."""
    if not await is_user_admin(message.chat.id, message.from_user.id, bot):
        return "❌ У вас нет прав администратора."
    if not await can_bot_restrict(message.chat.id, bot):
        return "❌ У меня нет прав на модерацию пользователей."
    return None


async def _build_moderation_context(
    message: types.Message, args_text: str, bot: Bot
) -> ModerationContext | None:
    """Строит контекст модерации из сообщения."""
    has_reply = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
    )

    if has_reply:
        user = message.reply_to_message.from_user
        _, duration, reason = parse_text_command_args(args_text, True)
        return ModerationContext(user.id, user.full_name, duration, reason)

    user_arg, duration, reason = parse_text_command_args(args_text, False)
    if not user_arg:
        return None

    # Пробуем получить пользователя
    user_id = None
    user_name = None

    if user_arg.isdigit():
        user_id = int(user_arg)
        user_name = f"ID:{user_arg}"
    elif user_arg.startswith("@"):
        # Пробуем получить по username
        try:
            chat = await bot.get_chat(user_arg)
            if chat.id:
                user_id = chat.id
                user_name = chat.full_name or chat.username or user_arg
        except Exception:
            return None
    else:
        return None

    if not user_id:
        return None

    return ModerationContext(user_id, user_name, duration, reason)


async def _send_usage_hint(message: types.Message, command: str) -> None:
    """Отправляет подсказку по использованию команды."""
    cmd_examples = {
        "мут": "мут 1м ругался в чате",
        "бан": "бан 1д спам",
        "размут": "размут",
        "разбан": "разбан",
        "кик": "кик нарушение правил",
    }
    example = cmd_examples.get(command, "мут 1м причина")
    await message.answer(
        f"❌ Укажите пользователя.\nОтветьте на сообщение или: {example}"
    )


async def _dispatch_command(
    message: types.Message, bot: Bot, command: str, ctx: ModerationContext
) -> None:
    """Выполняет команду модерации."""
    handlers = {
        "мут": _execute_mute,
        "бан": _execute_ban,
        "размут": _execute_unmute,
        "разбан": _execute_unban,
        "кик": _execute_kick,
    }
    handler = handlers.get(command)
    if handler:
        await handler(message, bot, ctx)


def _get_action_verb(command: str) -> str:
    """Возвращает глагол действия для сообщений об ошибках."""
    verbs = {
        "мут": "замутить",
        "бан": "забанить",
        "размут": "размутить",
        "разбан": "разбанить",
        "кик": "кикнуть",
    }
    return verbs.get(command, "модерировать")


async def _execute_mute(
    message: types.Message,
    bot: Bot,
    ctx: ModerationContext,
) -> None:
    """Выполняет мут пользователя."""
    if ctx.duration and ctx.duration < timedelta(seconds=MIN_MUTE_SECONDS):
        await message.answer("❌ Минимальное время мута — 30 секунд.")
        return

    try:
        permissions = get_mute_permissions()
        if ctx.duration:
            until_date = datetime.now(UTC) + ctx.duration
            await bot.restrict_chat_member(
                message.chat.id,
                ctx.user_id,
                permissions=permissions,
                until_date=until_date,
            )
            action = "🔇 <b>Временный мут</b>"
        else:
            await bot.restrict_chat_member(
                message.chat.id, ctx.user_id, permissions=permissions
            )
            action = "🔇 <b>Мут</b>"

        response = build_action_message(
            action,
            ctx.user_name,
            ctx.duration,
            ctx.reason,
        )
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_unmute_keyboard(ctx.user_id),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при муте: {e}")


async def _execute_ban(
    message: types.Message,
    bot: Bot,
    ctx: ModerationContext,
) -> None:
    """Выполняет бан пользователя."""
    try:
        if ctx.duration:
            until_date = datetime.now(UTC) + ctx.duration
            await bot.ban_chat_member(
                message.chat.id, ctx.user_id, until_date=until_date
            )
            action = "🚫 <b>Временный бан</b>"
        else:
            await bot.ban_chat_member(message.chat.id, ctx.user_id)
            action = "🚫 <b>Бан</b>"

        response = build_action_message(
            action,
            ctx.user_name,
            ctx.duration,
            ctx.reason,
        )
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_unban_keyboard(ctx.user_id),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при бане: {e}")


async def _execute_unmute(
    message: types.Message,
    bot: Bot,
    ctx: ModerationContext,
) -> None:
    """Снимает мут с пользователя."""
    try:
        await bot.restrict_chat_member(
            message.chat.id, ctx.user_id, permissions=get_unmute_permissions()
        )
        await message.answer(
            f"🔊 <b>Мут снят</b>\n👤 Пользователь: {ctx.user_name}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при снятии мута: {e}")


async def _execute_unban(
    message: types.Message,
    bot: Bot,
    ctx: ModerationContext,
) -> None:
    """Разбанивает пользователя."""
    try:
        await bot.unban_chat_member(
            message.chat.id, ctx.user_id, only_if_banned=True
        )
        await message.answer(
            f"✅ <b>Разбан</b>\n👤 Пользователь: {ctx.user_name}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при разбане: {e}")


async def _execute_kick(
    message: types.Message,
    bot: Bot,
    ctx: ModerationContext,
) -> None:
    """Кикает пользователя."""
    try:
        await bot.ban_chat_member(message.chat.id, ctx.user_id)
        await bot.unban_chat_member(
            message.chat.id, ctx.user_id, only_if_banned=True
        )
        response = build_action_message(
            "👢 <b>Кик</b>",
            ctx.user_name,
            reason=ctx.reason,
        )
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при кике: {e}")


# ==================== CALLBACK HANDLERS (кнопки) ====================


@router.callback_query(F.data.startswith("unban:"))
async def callback_unban(callback: types.CallbackQuery, bot: Bot) -> None:
    """Обработчик кнопки разбана."""
    if not callback.message or not callback.from_user:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    chat_id = callback.message.chat.id

    # Проверяем права администратора
    if not await is_user_admin(chat_id, callback.from_user.id, bot):
        await callback.answer("❌ Только администраторы", show_alert=True)
        return

    # Получаем user_id из callback_data
    try:
        user_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    try:
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        await callback.answer("✅ Пользователь разбанен")
        # Редактируем сообщение, убирая кнопку
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

    # Проверяем права администратора
    if not await is_user_admin(chat_id, callback.from_user.id, bot):
        await callback.answer("❌ Только администраторы", show_alert=True)
        return

    # Получаем user_id из callback_data
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
        # Редактируем сообщение, убирая кнопку
        if callback.message.text:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <i>Мут снят</i>",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ==================== АНТИ-СПАМ ====================


def _clean_old_messages(chat_id: int, user_id: int) -> None:
    """Удаляет старые записи о сообщениях пользователя."""
    key = (chat_id, user_id)
    if key not in user_messages:
        return

    cutoff = datetime.now(UTC) - timedelta(seconds=SPAM_TIME_WINDOW)
    user_messages[key] = [ts for ts in user_messages[key] if ts > cutoff]


def _is_spam(chat_id: int, user_id: int) -> bool:
    """Проверяет, является ли активность пользователя спамом."""
    key = (chat_id, user_id)
    _clean_old_messages(chat_id, user_id)

    # Добавляем текущее сообщение
    user_messages[key].append(datetime.now(UTC))

    # Проверяем количество сообщений
    return len(user_messages[key]) > SPAM_MAX_MESSAGES


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def antispam_handler(message: types.Message, bot: Bot) -> None:
    """Обработчик анти-спама для всех сообщений в группах."""
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Пропускаем администраторов
    if await is_user_admin(chat_id, user_id, bot):
        return

    # Пропускаем если бот не может ограничивать
    if not await can_bot_restrict(chat_id, bot):
        return

    # Проверяем на спам
    if _is_spam(chat_id, user_id):
        try:
            # Мутим пользователя
            until_date = datetime.now(UTC) + SPAM_MUTE_DURATION
            await bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=get_mute_permissions(),
                until_date=until_date,
            )

            # Очищаем счётчик
            user_messages[(chat_id, user_id)] = []

            await message.answer(
                f"🔇 <b>Авто-мут за спам</b>\n"
                f"👤 Пользователь: {message.from_user.full_name}\n"
                f"⏱ Срок: {format_timedelta(SPAM_MUTE_DURATION)}",
                parse_mode="HTML",
                reply_markup=get_unmute_keyboard(user_id),
            )
        except Exception:
            pass  # Игнорируем ошибки анти-спама
