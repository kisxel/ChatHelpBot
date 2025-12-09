from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
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


class Warn(Base):
    __tablename__ = "warns"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(String, nullable=True)


class ChatSettings(Base):
    __tablename__ = "chat_settings"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    banned_words: Mapped[str] = mapped_column(String, default="")
