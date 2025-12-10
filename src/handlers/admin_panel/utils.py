"""Общие функции панели управления."""

from sqlalchemy import select, update

from src.database.core import async_session
from src.database.models import Chat


async def get_admin_chat(user_id: int) -> Chat | None:
    """Получает чат, где пользователь является админом (активатором)."""
    async with async_session() as session:
        result = await session.execute(
            select(Chat).where(Chat.activated_by == user_id, Chat.is_active)
        )
        return result.scalar_one_or_none()


async def deactivate_chat(chat_id: int) -> None:
    """Деактивирует чат."""
    async with async_session() as session:
        await session.execute(
            update(Chat).where(Chat.chat_id == chat_id).values(is_active=False)
        )
        await session.commit()


async def toggle_chat_closed(chat_id: int, closed: bool) -> None:
    """Открывает или закрывает чат."""
    async with async_session() as session:
        await session.execute(
            update(Chat)
            .where(Chat.chat_id == chat_id)
            .values(is_closed=closed)
        )
        await session.commit()
