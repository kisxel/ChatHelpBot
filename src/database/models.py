from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.core import Base


class Chat(Base):
    """Модель для хранения информации об активированных чатах."""

    __tablename__ = "chats"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_by: Mapped[int] = mapped_column(BigInteger)
    activated_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now()
    )
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_on_filter: Mapped[bool] = mapped_column(Boolean, default=False)
    # Настройки команд
    enable_moderation_cmds: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_report_cmds: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_rules_cmds: Mapped[bool] = mapped_column(Boolean, default=True)
    # Привязанный канал для автоответа на посты (хранится полный ID с -100)
    linked_channel_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    # Текст сообщения для ответа на пост канала
    channel_post_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # Медиа для ответа на пост (file_id фото/видео/гиф)
    channel_post_media_id: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    # Тип медиа: photo, video, animation (gif)
    channel_post_media_type: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    # Кнопки-ссылки в формате JSON: [{"text": "...", "url": "..."}, ...]
    channel_post_buttons: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # Текст правил чата (для команды !правила)
    chat_rules_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # Включен ли автоответ на посты канала
    channel_post_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Закрывать ли чат после поста (антибот)
    close_chat_on_post: Mapped[bool] = mapped_column(Boolean, default=False)
    # На сколько секунд закрывать чат после поста
    close_chat_duration: Mapped[int] = mapped_column(Integer, default=10)


class Warn(Base):
    """Варны пользователей."""

    __tablename__ = "warns"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, index=True, nullable=True
    )
    username: Mapped[str | None] = mapped_column(
        String, index=True, nullable=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    warned_at: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    warned_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ChatSettings(Base):
    __tablename__ = "chat_settings"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    banned_words: Mapped[str] = mapped_column(String, default="")


class UserFilter(Base):
    """Фильтры сообщений для конкретного пользователя в чате."""

    __tablename__ = "user_filters"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    # Тип фильтра: 'block' - удалять содержащие, 'allow' - удалять НЕ содержащие
    filter_type: Mapped[str] = mapped_column(String, default="block")
    # Паттерн для фильтрации (через запятую если несколько)
    pattern: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Уведомлять ли админа при удалении по этому фильтру
    notify: Mapped[bool] = mapped_column(Boolean, default=False)


class MessageStats(Base):
    """Статистика сообщений в чате по дням."""

    __tablename__ = "message_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    date: Mapped[str] = mapped_column(String)  # Формат: YYYY-MM-DD
    message_count: Mapped[int] = mapped_column(Integer, default=0)
