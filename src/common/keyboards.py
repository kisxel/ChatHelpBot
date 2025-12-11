"""Общие клавиатуры для бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.models import Chat


def get_panel_keyboard(chat: Chat) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру главной панели управления."""
    buttons = [
        [
            InlineKeyboardButton(
                text="⚙️ Настройки",
                callback_data="panel:settings",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚠️ Варны",
                callback_data="panel:warns",
            ),
            InlineKeyboardButton(
                text="🔍 Фильтры",
                callback_data="panel:filters",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="panel:stats",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="panel:refresh",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_filters_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру управления фильтрами."""
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить фильтр",
                callback_data="panel:filter_add",
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Список фильтров",
                callback_data="panel:filter_list",
            )
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(chat: Chat) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру настроек."""
    mod_status = "✅" if chat.enable_moderation_cmds else "❌"
    report_status = "✅" if chat.enable_report_cmds else "❌"
    closed_text = "🔓 Открыть чат" if chat.is_closed else "🔒 Закрыть чат"
    closed_action = "open" if chat.is_closed else "close"

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{mod_status} Команды модерации (бан/мут/кик)",
                callback_data="settings:toggle_mod",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{report_status} Команды репортов (админ/репорт)",
                callback_data="settings:toggle_report",
            )
        ],
        [
            InlineKeyboardButton(
                text=closed_text,
                callback_data=f"panel:toggle:{closed_action}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🚪 Деактивировать бота",
                callback_data="panel:deactivate",
            )
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
