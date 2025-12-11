"""Текстовые команды модерации без слэша: мут, бан, кик и т.д."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from sqlalchemy import select

from src.common.keyboards import get_unban_keyboard, get_unmute_keyboard
from src.common.permissions import can_bot_restrict, is_user_admin
from src.database.core import async_session
from src.database.models import Chat
from src.handlers.moderation.utils import (
    MIN_MUTE_SECONDS,
    are_moderation_cmds_enabled,
    build_action_message,
    check_target_user,
    get_mute_permissions,
    get_unmute_permissions,
)
from src.utils import parse_timedelta

router = Router(name="text_commands")

# Регулярное выражение для команд модерации (в начале строки)
# Поддержка: мут, !мут, mute, !mute, анмут, unmute, бан, ban, кик, kick и т.д.
TEXT_CMD_PATTERN = re.compile(
    r"^!?(мут|mute|размут|анмут|unmute|бан|ban|разбан|анбан|unban|кик|kick)(?:\s+(.*))?$",
    re.IGNORECASE,
)

# Максимальный размер кэша username
MAX_USERNAME_CACHE_SIZE = 10000


class LRUUsernameCache(dict):
    """LRU кэш для username с ограничением размера."""

    def __init__(self, maxsize: int = MAX_USERNAME_CACHE_SIZE) -> None:
        super().__init__()
        self.maxsize = maxsize
        self._order: list = []

    def __setitem__(self, key: tuple, value: tuple) -> None:
        if key in self:
            self._order.remove(key)
        super().__setitem__(key, value)
        self._order.append(key)
        while len(self) > self.maxsize:
            oldest = self._order.pop(0)
            super().__delitem__(oldest)

    def __getitem__(self, key: tuple) -> tuple:
        if key in self._order:
            self._order.remove(key)
            self._order.append(key)
        return super().__getitem__(key)


# Кэш username -> (user_id, full_name)
username_cache: LRUUsernameCache = LRUUsernameCache()


def cache_user(chat_id: int, user: types.User) -> None:
    """Кэширует username пользователя."""
    if user.username:
        key = (chat_id, user.username.lower())
        username_cache[key] = (user.id, user.full_name)


def get_cached_user(
    chat_id: int, username: str
) -> tuple[int | None, str | None]:
    """Получает user_id из кэша по username."""
    clean_username = username.lstrip("@").lower()
    key = (chat_id, clean_username)
    if key in username_cache:
        user_id, full_name = username_cache[key]
        return user_id, full_name
    return None, None


@dataclass
class ModerationContext:
    """Контекст для команды модерации."""

    user_id: int
    user_name: str
    duration: timedelta | None = None
    reason: str | None = None


def parse_text_command_args(
    args_text: str,
    has_reply: bool,
) -> tuple[str | None, timedelta | None, str | None]:
    """Парсит аргументы текстовой команды."""
    if not args_text:
        return None, None, None

    parts = args_text.split()
    if not parts:
        return None, None, None

    user_arg = None
    start_idx = 0

    if not has_reply:
        user_arg = parts[0]
        start_idx = 1

    remaining = parts[start_idx:]
    if not remaining:
        return user_arg, None, None

    duration = parse_timedelta(remaining[0])
    if duration:
        reason = " ".join(remaining[1:]) if len(remaining) > 1 else None
    else:
        reason = " ".join(remaining) if remaining else None
        duration = None

    return user_arg, duration, reason


async def resolve_user_arg(
    user_arg: str, message: types.Message, bot: Bot
) -> tuple[int | None, str | None]:
    """Разрешает аргумент пользователя в user_id и имя."""
    if user_arg.isdigit():
        return int(user_arg), f"ID:{user_arg}"

    if user_arg.startswith("@"):
        chat_id = message.chat.id

        # 1. Проверяем кэш
        cached_id, cached_name = get_cached_user(chat_id, user_arg)
        if cached_id:
            return cached_id, cached_name

        # 2. Ищем в entities
        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention" and entity.user:
                    return entity.user.id, entity.user.full_name

        # 3. Пробуем через API
        try:
            chat = await bot.get_chat(user_arg)
            if chat.id:
                name = chat.full_name or chat.username or user_arg
                username_cache[(chat_id, user_arg.lstrip("@").lower())] = (
                    chat.id,
                    name,
                )
                return chat.id, name
        except Exception:
            pass

    return None, None


async def build_moderation_context(
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

    user_id, user_name = await resolve_user_arg(user_arg, message, bot)
    if not user_id:
        return None

    return ModerationContext(user_id, user_name, duration, reason)


def get_action_verb(command: str) -> str:
    """Возвращает глагол действия для сообщений об ошибках."""
    verbs = {
        "мут": "замутить",
        "mute": "замутить",
        "бан": "забанить",
        "ban": "забанить",
        "размут": "размутить",
        "анмут": "размутить",
        "unmute": "размутить",
        "разбан": "разбанить",
        "анбан": "разбанить",
        "unban": "разбанить",
        "кик": "кикнуть",
        "kick": "кикнуть",
    }
    return verbs.get(command, "модерировать")


async def check_text_cmd_permissions(
    message: types.Message, bot: Bot
) -> str | None:
    """Проверяет права для текстовой команды. Возвращает ошибку или None."""
    if not await is_user_admin(message.chat.id, message.from_user.id, bot):
        return "❌ У вас нет прав администратора."
    if not await can_bot_restrict(message.chat.id, bot):
        return "❌ У меня нет прав на модерацию пользователей."
    return None


@router.message(F.text.regexp(TEXT_CMD_PATTERN))
async def text_moderation_command(message: types.Message, bot: Bot) -> None:
    """Обработчик текстовых команд модерации без слэша."""
    if message.chat.type == ChatType.PRIVATE or not message.text:
        return

    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    match = TEXT_CMD_PATTERN.match(message.text)
    if not match:
        return

    command = match.group(1).lower()
    args_text = match.group(2) or ""

    # Проверяем права
    error = await check_text_cmd_permissions(message, bot)
    if error:
        await message.answer(error)
        return

    # Получаем контекст модерации
    ctx = await build_moderation_context(message, args_text, bot)
    if not ctx:
        cmd_examples = {
            "мут": "мут @user 1м причина",
            "mute": "mute @user 1m reason",
            "бан": "бан @user 1д причина",
            "ban": "ban @user 1d reason",
            "размут": "размут @user",
            "анмут": "анмут @user",
            "unmute": "unmute @user",
            "разбан": "разбан @user",
            "анбан": "анбан @user",
            "unban": "unban @user",
            "кик": "кик @user причина",
            "kick": "kick @user reason",
        }
        example = cmd_examples.get(command, "мут @user 1м причина")
        await message.answer(
            f"❌ Укажите пользователя.\nОтветьте на сообщение или: {example}"
        )
        return

    # Проверяем целевого пользователя
    error = await check_target_user(
        message, bot, ctx.user_id, get_action_verb(command)
    )
    if error:
        await message.answer(error)
        return

    # Маппинг команд на обработчики
    handlers = {
        # Мут
        "мут": execute_mute,
        "mute": execute_mute,
        # Размут
        "размут": execute_unmute,
        "анмут": execute_unmute,
        "unmute": execute_unmute,
        # Бан
        "бан": execute_ban,
        "ban": execute_ban,
        # Разбан
        "разбан": execute_unban,
        "анбан": execute_unban,
        "unban": execute_unban,
        # Кик
        "кик": execute_kick,
        "kick": execute_kick,
    }
    handler = handlers.get(command)
    if handler:
        await handler(message, bot, ctx)


async def execute_mute(
    message: types.Message, bot: Bot, ctx: ModerationContext
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
            action, ctx.user_name, ctx.duration, ctx.reason
        )
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_unmute_keyboard(ctx.user_id),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при муте: {e}")


async def execute_ban(
    message: types.Message, bot: Bot, ctx: ModerationContext
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
            action, ctx.user_name, ctx.duration, ctx.reason
        )
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=get_unban_keyboard(ctx.user_id),
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при бане: {e}")


async def execute_unmute(
    message: types.Message, bot: Bot, ctx: ModerationContext
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


async def execute_unban(
    message: types.Message, bot: Bot, ctx: ModerationContext
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


async def execute_kick(
    message: types.Message, bot: Bot, ctx: ModerationContext
) -> None:
    """Кикает пользователя."""
    try:
        await bot.ban_chat_member(message.chat.id, ctx.user_id)
        await bot.unban_chat_member(
            message.chat.id, ctx.user_id, only_if_banned=True
        )
        response = build_action_message(
            "👢 <b>Кик</b>", ctx.user_name, reason=ctx.reason
        )
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка при кике: {e}")


# Регулярное выражение для команды правил (только с !)
RULES_CMD_PATTERN = re.compile(r"^!(правила|rules)$", re.IGNORECASE)


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.regexp(RULES_CMD_PATTERN),
)
async def handle_rules_command(message: types.Message) -> None:
    """Обработка команды !правила (!rules)."""
    chat_id = message.chat.id

    # Получаем правила из БД
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.chat_id == chat_id, Chat.is_active)
        )
        chat = result.scalar_one_or_none()

    if not chat or not chat.chat_rules_text:
        await message.answer("📜 Правила чата не заданы.")
        return

    await message.answer(
        f"📜 <b>Правила чата</b>\n\n{chat.chat_rules_text}",
        parse_mode="HTML",
    )
