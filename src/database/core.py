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

        # Добавляем linked_channel_id в chats если не существует
        with contextlib.suppress(Exception):
            await conn.execute(
                text("ALTER TABLE chats ADD COLUMN linked_channel_id BIGINT")
            )

        # Переименовываем channel_rules_text в channel_post_text
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats RENAME COLUMN channel_rules_text "
                    "TO channel_post_text"
                )
            )

        # Добавляем channel_post_text если не существует (для новых БД)
        with contextlib.suppress(Exception):
            await conn.execute(
                text("ALTER TABLE chats ADD COLUMN channel_post_text TEXT")
            )

        # Добавляем chat_rules_text - правила чата
        with contextlib.suppress(Exception):
            await conn.execute(
                text("ALTER TABLE chats ADD COLUMN chat_rules_text TEXT")
            )

        # Добавляем channel_post_enabled - вкл/выкл автоответа
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN channel_post_enabled "
                    "BOOLEAN DEFAULT 1"
                )
            )

        # Добавляем close_chat_on_post - закрывать ли чат после поста
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN close_chat_on_post "
                    "BOOLEAN DEFAULT 0"
                )
            )

        # Добавляем close_chat_duration - длительность закрытия
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN close_chat_duration "
                    "INTEGER DEFAULT 10"
                )
            )

        # Добавляем channel_post_media_id - ID медиа для поста
        with contextlib.suppress(Exception):
            await conn.execute(
                text("ALTER TABLE chats ADD COLUMN channel_post_media_id TEXT")
            )

        # Добавляем channel_post_media_type - тип медиа
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN channel_post_media_type TEXT"
                )
            )

        # Добавляем channel_post_buttons - кнопки в JSON
        with contextlib.suppress(Exception):
            await conn.execute(
                text("ALTER TABLE chats ADD COLUMN channel_post_buttons TEXT")
            )

        # Добавляем enable_rules_cmds - вкл/выкл команды правил
        with contextlib.suppress(Exception):
            await conn.execute(
                text(
                    "ALTER TABLE chats ADD COLUMN enable_rules_cmds "
                    "BOOLEAN DEFAULT 1"
                )
            )
