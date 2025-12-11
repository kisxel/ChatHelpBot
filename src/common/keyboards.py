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
    closed_text = "🔓 Открыть чат" if chat.is_closed else "🔒 Закрыть чат"
    closed_action = "open" if chat.is_closed else "close"

    buttons = [
        [
            InlineKeyboardButton(
                text="💬 Реакция на команды",
                callback_data="settings:commands",
            )
        ],
        [
            InlineKeyboardButton(
                text="📜 Правила чата",
                callback_data="settings:rules",
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 Настроить канал",
                callback_data="settings:channel",
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


def get_commands_keyboard(chat: Chat) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру настроек реакции на команды."""
    mod_status = "✅" if chat.enable_moderation_cmds else "❌"
    report_status = "✅" if chat.enable_report_cmds else "❌"
    rules_status = "✅" if chat.enable_rules_cmds else "❌"

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{mod_status} Модерация (бан/мут/кик)",
                callback_data="settings:toggle_mod",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{report_status} Репорты (!admin/!репорт)",
                callback_data="settings:toggle_report",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{rules_status} Правила (!правила/!rules)",
                callback_data="settings:toggle_rules",
            )
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:settings")],
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


def get_channel_settings_keyboard(
    chat: Chat | None = None,
) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру настроек канала."""
    post_enabled = chat.channel_post_enabled if chat else True
    close_enabled = chat.close_chat_on_post if chat else False

    post_status = "✅" if post_enabled else "❌"
    close_status = "✅" if close_enabled else "❌"

    buttons = [
        [
            InlineKeyboardButton(
                text="📝 Изменить ID канала",
                callback_data="settings:channel_id",
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Текст под пост",
                callback_data="settings:channel_post_text",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{post_status} Автоответ на посты",
                callback_data="settings:toggle_post_enabled",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{close_status} Закрывать чат после поста",
                callback_data="settings:toggle_close_chat",
            )
        ],
        [
            InlineKeyboardButton(
                text="⏱ Длительность закрытия",
                callback_data="settings:close_duration",
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑 Удалить привязку канала",
                callback_data="settings:channel_remove",
            )
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="panel:settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
