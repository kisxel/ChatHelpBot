"""Команды предупреждений (варнов)."""

import re
from dataclasses import dataclass

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, func, or_, select, update

from src.common.permissions import can_bot_restrict, is_user_admin
from src.database.core import async_session
from src.database.models import Warn
from src.handlers.moderation.utils import are_moderation_cmds_enabled

router = Router(name="warns")

# Максимум варнов до бана
MAX_WARNS = 3

# Для сравнения в callback_data
MIN_PARTS_CALLBACK = 3

# Паттерн для команд варна
WARN_CMD_PATTERN = re.compile(
    r"^[!/](warn|варн|unwarn|снятьварн|warns|варны)(?:\s+(.*))?$",
    re.IGNORECASE,
)


@dataclass
class WarnTarget:
    """Данные целевого пользователя для варна."""

    user_id: int | None
    username: str | None
    user_name: str


async def find_and_merge_user_data(
    session: async_session,
    chat_id: int,
    user_id: int | None,
    username: str | None,
) -> tuple[int | None, str | None]:
    """
    Ищет в БД существующие записи пользователя и возвращает полные данные.
    Если есть только username - ищет user_id в других записях.
    Если есть только user_id - ищет username в других записях.
    Также обновляет все существующие записи чтобы у них были оба поля.
    """
    found_user_id = user_id
    found_username = username

    # Если есть только username - ищем user_id в БД
    if username and not user_id:
        result = await session.execute(
            select(Warn.user_id)
            .where(
                Warn.chat_id == chat_id,
                Warn.username == username,
                Warn.user_id.isnot(None),
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            found_user_id = row

    # Если есть только user_id - ищем username в БД
    if user_id and not username:
        result = await session.execute(
            select(Warn.username)
            .where(
                Warn.chat_id == chat_id,
                Warn.user_id == user_id,
                Warn.username.isnot(None),
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            found_username = row

    # Если нашли оба идентификатора - обновляем ВСЕ записи этого пользователя
    if found_user_id and found_username:
        await session.execute(
            update(Warn)
            .where(
                Warn.chat_id == chat_id,
                or_(
                    Warn.user_id == found_user_id,
                    Warn.username == found_username,
                ),
            )
            .values(user_id=found_user_id, username=found_username)
        )

    return found_user_id, found_username


async def enrich_user_data_via_api(
    bot: Bot, user_id: int | None, username: str | None
) -> tuple[int | None, str | None]:
    """
    Пытается получить полные данные пользователя через Telegram API.
    Возвращает (user_id, username) - обогащённые данные.
    """
    # Если уже есть оба - ничего не делаем
    if user_id and username:
        return user_id, username

    # Пробуем получить через API
    try:
        if username and not user_id:
            chat = await bot.get_chat(f"@{username}")
            if chat and chat.id:
                return chat.id, username
        elif user_id and not username:
            chat = await bot.get_chat(user_id)
            if chat and chat.username:
                return user_id, chat.username.lower()
    except Exception:
        pass

    return user_id, username


async def get_user_warns_count(
    chat_id: int, user_id: int | None = None, username: str | None = None
) -> int:
    """Получает количество варнов пользователя по user_id ИЛИ username."""
    username_lower = username.lower() if username else None

    async with async_session() as session:
        # Ищем и объединяем данные пользователя
        merged_user_id, merged_username = await find_and_merge_user_data(
            session, chat_id, user_id, username_lower
        )
        await session.commit()

        # Считаем по найденным данным
        if merged_user_id:
            result = await session.execute(
                select(func.count(Warn.id)).where(
                    Warn.chat_id == chat_id, Warn.user_id == merged_user_id
                )
            )
        elif merged_username:
            result = await session.execute(
                select(func.count(Warn.id)).where(
                    Warn.chat_id == chat_id, Warn.username == merged_username
                )
            )
        else:
            return 0

        return result.scalar() or 0


async def add_warn(
    chat_id: int,
    user_id: int | None,
    username: str | None,
    reason: str | None,
    warned_by: int,
    bot: Bot | None = None,
) -> int:
    """Добавляет варн пользователю. Возвращает общее количество варнов."""
    username_lower = username.lower() if username else None

    # Сначала пробуем обогатить данные через Telegram API
    enriched_user_id, enriched_username = user_id, username_lower
    if bot:
        enriched_user_id, enriched_username = await enrich_user_data_via_api(
            bot, user_id, username_lower
        )

    async with async_session() as session:
        # Ищем и объединяем данные пользователя из существующих записей
        merged_user_id, merged_username = await find_and_merge_user_data(
            session, chat_id, enriched_user_id, enriched_username
        )

        # Используем объединённые данные для нового варна
        final_user_id = merged_user_id or enriched_user_id
        final_username = merged_username or enriched_username

        # Добавляем новый варн с полными данными
        warn = Warn(
            chat_id=chat_id,
            user_id=final_user_id,
            username=final_username,
            reason=reason,
            warned_by=warned_by,
        )
        session.add(warn)
        await session.commit()

    return await get_user_warns_count(chat_id, final_user_id, final_username)


async def remove_user_warns(
    chat_id: int, user_id: int | None = None, username: str | None = None
) -> int:
    """Удаляет все варны пользователя. Возвращает количество удалённых."""
    username_lower = username.lower() if username else None

    async with async_session() as session:
        # Ищем и объединяем данные пользователя
        merged_user_id, merged_username = await find_and_merge_user_data(
            session, chat_id, user_id, username_lower
        )

        # Строим условия для удаления по объединённым данным
        if merged_user_id:
            condition = Warn.user_id == merged_user_id
        elif merged_username:
            condition = Warn.username == merged_username
        elif user_id:
            condition = Warn.user_id == user_id
        elif username_lower:
            condition = Warn.username == username_lower
        else:
            return 0

        # Считаем
        result = await session.execute(
            select(func.count(Warn.id)).where(
                Warn.chat_id == chat_id, condition
            )
        )
        count = result.scalar() or 0

        # Удаляем
        await session.execute(
            delete(Warn).where(Warn.chat_id == chat_id, condition)
        )
        await session.commit()

    return count


def extract_username(user: types.User) -> str | None:
    """Извлекает username из пользователя."""
    return user.username.lower() if user.username else None


async def get_target_from_reply(
    message: types.Message,
) -> tuple[int | None, str | None, str | None]:
    """Получает user_id, username и имя из реплая."""
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, extract_username(user), user.full_name
    return None, None, None


async def get_target_from_args(
    args: str | None, bot: Bot
) -> tuple[int | None, str | None, str | None]:
    """Получает user_id, username и имя из аргументов команды."""
    if not args:
        return None, None, None

    parts = args.split(maxsplit=1)
    first_arg = parts[0]

    # Проверяем @username
    if first_arg.startswith("@"):
        username = first_arg.lstrip("@").lower()
        # Пробуем получить user_id через API
        try:
            chat = await bot.get_chat(first_arg)
            if chat.id:
                name = chat.full_name or chat.username or first_arg
                return chat.id, username, name
        except Exception:
            pass
        # Даже если API не сработал, возвращаем username
        return None, username, first_arg

    # Проверяем ID
    if first_arg.isdigit():
        return int(first_arg), None, f"ID:{first_arg}"

    return None, None, None


def parse_reason_from_args(args: str | None, has_target: bool) -> str | None:
    """Извлекает причину из аргументов."""
    if not args:
        return None

    parts = args.split(maxsplit=1)

    # Если есть цель (@username или ID), причина во второй части
    if has_target and len(parts) > 1:
        return parts[1].strip()

    # Если цель из реплая, вся строка - причина
    if not has_target:
        return args.strip()

    return None


async def check_warn_target(
    message: types.Message, bot: Bot, user_id: int | None, username: str | None
) -> str | None:
    """Проверяет целевого пользователя для варна."""
    if user_id:
        if user_id == message.from_user.id:
            return "❌ Вы не можете выдать варн себе."
        if user_id == bot.id:
            return "❌ Вы не можете выдать варн мне."
        if await is_user_admin(message.chat.id, user_id, bot):
            return "❌ Нельзя выдать варн администратору."
    return None


async def try_ban_for_warns(
    message: types.Message,
    bot: Bot,
    target: WarnTarget,
    warn_count: int,
) -> bool:
    """Пытается забанить пользователя за варны."""
    if warn_count < MAX_WARNS or not target.user_id:
        return False

    if not await can_bot_restrict(message.chat.id, bot):
        return False

    try:
        await bot.ban_chat_member(message.chat.id, target.user_id)

        # Кнопка разбана (только для админов, проверка в callback)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔓 Разбанить",
                        callback_data=f"unban:{target.user_id}",
                    )
                ]
            ]
        )

        await message.answer(
            f"🚫 <b>Бан по варнам</b>\n"
            f"👤 Пользователь: {target.user_name}\n"
            f"⚠️ Варнов: {warn_count}/{MAX_WARNS}\n"
            f"📝 Причина: достигнут лимит предупреждений",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        await remove_user_warns(
            message.chat.id, target.user_id, target.username
        )
        return True
    except Exception as e:
        await message.answer(f"❌ Ошибка при бане: {e}")
        return True


async def send_warn_message(
    message: types.Message,
    user_name: str,
    warn_count: int,
    reason: str | None,
) -> None:
    """Отправляет сообщение о варне."""
    text = (
        f"⚠️ <b>Предупреждение</b>\n"
        f"👤 Пользователь: {user_name}\n"
        f"📊 Варнов: {warn_count}/{MAX_WARNS}"
    )
    if reason:
        text += f"\n📝 Причина: {reason}"
    if warn_count == MAX_WARNS - 1:
        text += "\n\n⚡ <i>Следующий варн — бан!</i>"
    await message.answer(text, parse_mode="HTML")


# ==================== КОМАНДЫ ====================


@router.message(Command("warn"))
async def cmd_warn(message: types.Message, bot: Bot) -> None:
    """Выдать предупреждение: /warn [@user] [причина]."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах."
        )
        return

    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    if not await is_user_admin(message.chat.id, message.from_user.id, bot):
        await message.answer("❌ У вас нет прав администратора.")
        return

    # Получаем аргументы (всё после /warn)
    args = (
        message.text.split(maxsplit=1)[1]
        if len(message.text.split()) > 1
        else None
    )

    # Сначала пробуем из реплая
    user_id, username, user_name = await get_target_from_reply(message)

    if user_id or username:
        # Цель из реплая, args - это причина
        reason = args
    else:
        # Пробуем из аргументов
        user_id, username, user_name = await get_target_from_args(args, bot)
        if not user_id and not username:
            await message.answer(
                "❌ Укажите пользователя.\n"
                "Ответьте на сообщение или: /warn @username причина"
            )
            return
        reason = parse_reason_from_args(args, True)

    # Проверяем цель
    error = await check_warn_target(message, bot, user_id, username)
    if error:
        await message.answer(error)
        return

    # Выдаём варн
    warn_count = await add_warn(
        message.chat.id, user_id, username, reason, message.from_user.id, bot
    )

    target = WarnTarget(user_id, username, user_name)
    if await try_ban_for_warns(message, bot, target, warn_count):
        return

    await send_warn_message(message, user_name, warn_count, reason)


@router.message(Command("unwarn"))
async def cmd_unwarn(message: types.Message, bot: Bot) -> None:
    """Снять все варны с пользователя: /unwarn [@user]."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах."
        )
        return

    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    if not await is_user_admin(message.chat.id, message.from_user.id, bot):
        await message.answer("❌ У вас нет прав администратора.")
        return

    args = (
        message.text.split(maxsplit=1)[1]
        if len(message.text.split()) > 1
        else None
    )

    user_id, username, user_name = await get_target_from_reply(message)
    if not user_id and not username:
        user_id, username, user_name = await get_target_from_args(args, bot)

    if not user_id and not username:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или: /unwarn @username"
        )
        return

    removed = await remove_user_warns(message.chat.id, user_id, username)

    if removed > 0:
        await message.answer(
            f"✅ <b>Варны сняты</b>\n"
            f"👤 Пользователь: {user_name}\n"
            f"🗑 Удалено варнов: {removed}",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"ℹ️ У пользователя {user_name} нет варнов.")


@router.message(Command("warns"))
async def cmd_warns(message: types.Message, bot: Bot) -> None:
    """Проверить варны пользователя: /warns [@user]."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "❌ Эта команда работает только в групповых чатах."
        )
        return

    args = (
        message.text.split(maxsplit=1)[1]
        if len(message.text.split()) > 1
        else None
    )

    user_id, username, user_name = await get_target_from_reply(message)
    if not user_id and not username:
        user_id, username, user_name = await get_target_from_args(args, bot)

    # Если не указан - показываем свои варны
    if not user_id and not username:
        user_id = message.from_user.id
        username = extract_username(message.from_user)
        user_name = message.from_user.full_name

    warn_count = await get_user_warns_count(message.chat.id, user_id, username)

    await message.answer(
        f"📊 <b>Варны пользователя</b>\n"
        f"👤 {user_name}\n"
        f"⚠️ Варнов: {warn_count}/{MAX_WARNS}",
        parse_mode="HTML",
    )


# ==================== ТЕКСТОВЫЕ КОМАНДЫ ====================


async def handle_text_warns_check(
    message: types.Message, bot: Bot, args: str | None
) -> None:
    """Обработка команды проверки варнов."""
    user_id, username, user_name = await get_target_from_reply(message)
    if not user_id and not username:
        user_id, username, user_name = await get_target_from_args(args, bot)

    if not user_id and not username:
        user_id = message.from_user.id
        username = extract_username(message.from_user)
        user_name = message.from_user.full_name

    warn_count = await get_user_warns_count(message.chat.id, user_id, username)
    await message.answer(
        f"📊 <b>Варны пользователя</b>\n"
        f"👤 {user_name}\n"
        f"⚠️ Варнов: {warn_count}/{MAX_WARNS}",
        parse_mode="HTML",
    )


async def handle_text_unwarn(
    message: types.Message,
    user_id: int | None,
    username: str | None,
    user_name: str,
) -> None:
    """Обработка команды снятия варнов."""
    removed = await remove_user_warns(message.chat.id, user_id, username)
    if removed > 0:
        await message.answer(
            f"✅ <b>Варны сняты</b>\n"
            f"👤 Пользователь: {user_name}\n"
            f"🗑 Удалено варнов: {removed}",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"ℹ️ У пользователя {user_name} нет варнов.")


async def handle_text_warn(
    message: types.Message,
    bot: Bot,
    target: WarnTarget,
    reason: str | None,
) -> None:
    """Обработка команды выдачи варна."""
    error = await check_warn_target(
        message, bot, target.user_id, target.username
    )
    if error:
        await message.answer(error)
        return

    warn_count = await add_warn(
        message.chat.id,
        target.user_id,
        target.username,
        reason,
        message.from_user.id,
        bot,
    )

    if await try_ban_for_warns(message, bot, target, warn_count):
        return

    await send_warn_message(message, target.user_name, warn_count, reason)


@router.message(F.text.regexp(WARN_CMD_PATTERN))
async def text_warn_command(message: types.Message, bot: Bot) -> None:
    """Обработчик текстовых команд варнов: !варн, !warn и т.д."""
    if message.chat.type == ChatType.PRIVATE or not message.text:
        return

    if not await are_moderation_cmds_enabled(message.chat.id):
        return

    match = WARN_CMD_PATTERN.match(message.text)
    if not match:
        return

    command = match.group(1).lower()
    args = match.group(2)

    # Команда проверки варнов - не требует прав админа
    if command in ("warns", "варны"):
        await handle_text_warns_check(message, bot, args)
        return

    # Остальные команды требуют прав админа
    if not await is_user_admin(message.chat.id, message.from_user.id, bot):
        await message.answer("❌ У вас нет прав администратора.")
        return

    # Получаем цель
    user_id, username, user_name = await get_target_from_reply(message)
    reason = args if (user_id or username) else None

    if not user_id and not username:
        user_id, username, user_name = await get_target_from_args(args, bot)
        reason = (
            parse_reason_from_args(args, True)
            if (user_id or username)
            else None
        )

    if not user_id and not username:
        await message.answer(
            "❌ Укажите пользователя.\n"
            "Ответьте на сообщение или: !варн @username причина"
        )
        return

    if command in ("unwarn", "снятьварн"):
        await handle_text_unwarn(message, user_id, username, user_name)
    elif command in ("warn", "варн"):
        target = WarnTarget(user_id, username, user_name)
        await handle_text_warn(message, bot, target, reason)
