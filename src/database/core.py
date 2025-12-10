import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import DB_NAME

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_NAME}")
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Миграции для существующих таблиц
    async with engine.begin() as conn:
        # Добавляем is_closed в chats если не существует
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN is_closed BOOLEAN DEFAULT 0"
                )
            )
