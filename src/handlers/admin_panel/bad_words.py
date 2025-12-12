"""Управление запрещёнными словами."""

import contextlib
from pathlib import Path

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import update

from src.database.core import async_session
from src.database.models import Chat
from src.handlers.admin_panel.utils import get_admin_chat

router = Router(name="panel_bad_words")

# Путь к файлу со списком запрещённых слов
BAD_WORDS_FILE = (
    Path(__file__).parent.parent.parent.parent / "data" / "bad_words.txt"
)


class BadWordsStates(StatesGroup):
    """Состояния для управления запрещёнными словами."""

    waiting_word_to_add = State()
    waiting_word_to_remove = State()
    waiting_word_to_check = State()


def load_bad_words() -> set[str]:
    """Загружает список запрещённых слов из файла."""
    if not BAD_WORDS_FILE.exists():
        return set()
    with open(BAD_WORDS_FILE, encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}


def save_bad_words(words: set[str]) -> None:
    """Сохраняет список запрещённых слов в файл."""
    BAD_WORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BAD_WORDS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(words)))


def get_bad_words_keyboard(is_enabled: bool) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру управления запрещёнными словами."""
    toggle_text = "🔴 Выключить" if is_enabled else "🟢 Включить"
    buttons = [
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data="bad_words:toggle",
            )
        ],
        [
            InlineKeyboardButton(
                text="➕ Добавить слово",
                callback_data="bad_words:add",
            ),
            InlineKeyboardButton(
                text="➖ Удалить слово",
                callback_data="bad_words:remove",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔍 Проверить слово",
                callback_data="bad_words:check",
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="panel:filters",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "panel:bad_words")
async def callback_bad_words_menu(callback: types.CallbackQuery) -> None:
    """Меню управления запрещёнными словами."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    bad_words = load_bad_words()
    status = "🟢 Включено" if chat.bad_words_enabled else "🔴 Выключено"

    await callback.message.edit_text(
        "🤬 <b>Запрещённые слова</b>\n\n"
        f"Статус: {status}\n"
        f"Слов в списке: {len(bad_words)}\n\n"
        "При включении бот будет автоматически удалять "
        "сообщения, содержащие запрещённые слова.",
        parse_mode="HTML",
        reply_markup=get_bad_words_keyboard(chat.bad_words_enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "bad_words:toggle")
async def callback_bad_words_toggle(callback: types.CallbackQuery) -> None:
    """Переключение фильтрации запрещённых слов."""
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if not chat:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    new_value = not chat.bad_words_enabled

    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat.chat_id)
            .values(bad_words_enabled=new_value)
        )
        await session.commit()

    status_text = "включена" if new_value else "выключена"
    await callback.answer(f"🤬 Фильтрация {status_text}")

    # Обновляем меню
    bad_words = load_bad_words()
    status = "🟢 Включено" if new_value else "🔴 Выключено"

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            "🤬 <b>Запрещённые слова</b>\n\n"
            f"Статус: {status}\n"
            f"Слов в списке: {len(bad_words)}\n\n"
            "При включении бот будет автоматически удалять "
            "сообщения, содержащие запрещённые слова.",
            parse_mode="HTML",
            reply_markup=get_bad_words_keyboard(new_value),
        )


@router.callback_query(F.data == "bad_words:add")
async def callback_bad_words_add(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Начало добавления слова."""
    await state.set_state(BadWordsStates.waiting_word_to_add)

    await callback.message.edit_text(
        "➕ <b>Добавление слова</b>\n\n"
        "Введите слово, которое нужно добавить в список запрещённых:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="panel:bad_words",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(BadWordsStates.waiting_word_to_add))
async def process_add_bad_word(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка добавления слова."""
    if not message.text:
        await message.answer("❌ Введите слово")
        return

    word = message.text.strip().lower()
    bad_words = load_bad_words()

    if word in bad_words:
        await message.answer(
            f"⚠️ Слово «{word}» уже есть в списке.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="panel:bad_words",
                        )
                    ]
                ]
            ),
        )
    else:
        bad_words.add(word)
        save_bad_words(bad_words)
        await message.answer(
            f"✅ Слово «{word}» добавлено в список запрещённых.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="panel:bad_words",
                        )
                    ]
                ]
            ),
        )

    await state.clear()


@router.callback_query(F.data == "bad_words:remove")
async def callback_bad_words_remove(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Начало удаления слова."""
    await state.set_state(BadWordsStates.waiting_word_to_remove)

    await callback.message.edit_text(
        "➖ <b>Удаление слова</b>\n\n"
        "Введите слово, которое нужно удалить из списка:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="panel:bad_words",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(BadWordsStates.waiting_word_to_remove))
async def process_remove_bad_word(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка удаления слова."""
    if not message.text:
        await message.answer("❌ Введите слово")
        return

    word = message.text.strip().lower()
    bad_words = load_bad_words()

    if word not in bad_words:
        await message.answer(
            f"⚠️ Слово «{word}» не найдено в списке.\n\nХотите добавить его?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Добавить",
                            callback_data=f"bad_words:add_direct:{word}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="panel:bad_words",
                        )
                    ],
                ]
            ),
        )
    else:
        bad_words.discard(word)
        save_bad_words(bad_words)
        await message.answer(
            f"✅ Слово «{word}» удалено из списка.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="panel:bad_words",
                        )
                    ]
                ]
            ),
        )

    await state.clear()


@router.callback_query(F.data.startswith("bad_words:add_direct:"))
async def callback_add_word_direct(callback: types.CallbackQuery) -> None:
    """Быстрое добавление слова."""
    word = callback.data.split(":", 2)[2]
    bad_words = load_bad_words()

    bad_words.add(word)
    save_bad_words(bad_words)

    await callback.answer(f"✅ Слово «{word}» добавлено")

    # Возвращаемся в меню
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if chat:
        status = "🟢 Включено" if chat.bad_words_enabled else "🔴 Выключено"
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                "🤬 <b>Запрещённые слова</b>\n\n"
                f"Статус: {status}\n"
                f"Слов в списке: {len(bad_words)}\n\n"
                "При включении бот будет автоматически удалять "
                "сообщения, содержащие запрещённые слова.",
                parse_mode="HTML",
                reply_markup=get_bad_words_keyboard(chat.bad_words_enabled),
            )


@router.callback_query(F.data == "bad_words:check")
async def callback_bad_words_check(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Начало проверки слова."""
    await state.set_state(BadWordsStates.waiting_word_to_check)

    await callback.message.edit_text(
        "🔍 <b>Проверка слова</b>\n\nВведите слово для проверки:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="panel:bad_words",
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.message(StateFilter(BadWordsStates.waiting_word_to_check))
async def process_check_bad_word(
    message: types.Message, state: FSMContext
) -> None:
    """Обработка проверки слова."""
    if not message.text:
        await message.answer("❌ Введите слово")
        return

    word = message.text.strip().lower()
    bad_words = load_bad_words()

    if word in bad_words:
        await message.answer(
            f"🔴 Слово «{word}» <b>есть</b> в списке запрещённых.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➖ Удалить",
                            callback_data=f"bad_words:remove_direct:{word}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="panel:bad_words",
                        )
                    ],
                ]
            ),
        )
    else:
        await message.answer(
            f"🟢 Слово «{word}» <b>не найдено</b> в списке.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Добавить",
                            callback_data=f"bad_words:add_direct:{word}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="◀️ Назад",
                            callback_data="panel:bad_words",
                        )
                    ],
                ]
            ),
        )

    await state.clear()


@router.callback_query(F.data.startswith("bad_words:remove_direct:"))
async def callback_remove_word_direct(callback: types.CallbackQuery) -> None:
    """Быстрое удаление слова."""
    word = callback.data.split(":", 2)[2]
    bad_words = load_bad_words()

    bad_words.discard(word)
    save_bad_words(bad_words)

    await callback.answer(f"✅ Слово «{word}» удалено")

    # Возвращаемся в меню
    user_id = callback.from_user.id
    chat = await get_admin_chat(user_id)

    if chat:
        status = "🟢 Включено" if chat.bad_words_enabled else "🔴 Выключено"
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                "🤬 <b>Запрещённые слова</b>\n\n"
                f"Статус: {status}\n"
                f"Слов в списке: {len(bad_words)}\n\n"
                "При включении бот будет автоматически удалять "
                "сообщения, содержащие запрещённые слова.",
                parse_mode="HTML",
                reply_markup=get_bad_words_keyboard(chat.bad_words_enabled),
            )
