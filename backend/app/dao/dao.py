from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.base import BaseDAO
from app.models import Chat, File, Message, User
from app.utils import is_email


class UserDAO(BaseDAO[User]):
    model = User

    @classmethod
    async def find_by_login(cls, session: AsyncSession, login: str) -> User | None:
        login = login.strip()

        if is_email(login):
            stmt = select(cls.model).where(cls.model.email == login.lower())
        else:
            stmt = select(cls.model).where(cls.model.username == login)

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def search_by_username(
        cls, session: AsyncSession, query: str, limit: int = 20
    ) -> Sequence[User]:
        pattern = f'%{query}%'
        stmt = (
            select(cls.model)
            .where(cls.model.username.ilike(pattern))
            .order_by(cls.model.username)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update_last_seen(
        cls, session: AsyncSession, user_id: int, when: Any
    ) -> None:
        stmt = (
            update(cls.model).where(cls.model.id == user_id).values(last_seen_at=when)
        )
        await session.execute(stmt)

    @classmethod
    async def get_last_seen_map(
        cls, session: AsyncSession, user_ids: list[int]
    ) -> dict[int, Any]:
        if not user_ids:
            return {}
        stmt = select(cls.model.id, cls.model.last_seen_at).where(
            cls.model.id.in_(user_ids)
        )
        result = await session.execute(stmt)
        return {row.id: row.last_seen_at for row in result.all()}


class ChatDAO(BaseDAO[Chat]):
    model = Chat

    @classmethod
    async def find_by_user(
        cls, session: AsyncSession, user_id: int, limit: int = 100
    ) -> Sequence[Chat]:
        stmt = (
            select(cls.model)
            .where(Chat.users.contains([user_id]))
            .order_by(Chat.updated_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def find_by_ids_and_user(
        cls, session: AsyncSession, chat_ids: list[int], user_id: int
    ) -> list[Chat]:
        stmt = select(Chat).where(
            Chat.id.in_(chat_ids),
            Chat.users.contains([user_id]),
        )
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def find_between_users(
        cls, session: AsyncSession, user_a_id: int, user_b_id: int
    ) -> Chat | None:
        stmt = (
            select(cls.model)
            .where(
                Chat.users.contains([user_a_id, user_b_id]),
                func.cardinality(Chat.users) == 2,
            )
            .order_by(Chat.updated_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def delete(cls, session: AsyncSession, chat_id: int) -> int:
        stmt = delete(cls.model).where(cls.model.id == chat_id)
        result = await session.execute(stmt)
        return result.rowcount

    @classmethod
    async def get_peers(cls, session: AsyncSession, user_id: int) -> list[int]:
        stmt = (
            select(func.unnest(cls.model.users))
            .where(Chat.users.contains([user_id]))
            .distinct()
        )
        result = await session.execute(stmt)
        return [uid for uid in result.scalars().all() if uid != user_id]


class MessageDAO(BaseDAO[Message]):
    model = Message

    @classmethod
    async def list_chat_ids_by_file(
        cls, session: AsyncSession, file_id: int
    ) -> list[int]:
        stmt = (
            select(Message.chat_id).where(Message.message_file_id == file_id).distinct()
        )
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def find_by_chat_with_chat(
        cls, session: AsyncSession, chat_id: int
    ) -> list[tuple[Chat, Message | None]]:
        """Чат и его сообщения одним запросом (chat + messages)."""
        stmt = (
            select(Chat, cls.model)
            .outerjoin(cls.model, cls.model.chat_id == Chat.id)
            .where(Chat.id == chat_id)
            .order_by(cls.model.id)
        )
        result = await session.execute(stmt)
        rows: list[tuple[Chat, Message | None]] = []
        for chat, message in result.all():
            rows.append((chat, message))
        return rows

    @classmethod
    async def find_with_chat_users(
        cls, session: AsyncSession, message_id: int
    ) -> tuple[Message, list[int]] | None:
        """Сообщение вместе с участниками чата одним запросом (message + chat)."""
        stmt = (
            select(cls.model, Chat.users)
            .join(Chat, Chat.id == cls.model.chat_id)
            .where(cls.model.id == message_id)
        )
        row = (await session.execute(stmt)).one_or_none()
        if row is None:
            return None
        message, users = row
        return message, users

    @classmethod
    async def soft_delete_message(cls, session: AsyncSession, message_id: int) -> int:
        stmt = (
            update(cls.model)
            .where(cls.model.id == message_id)
            .values(message_text=None, message_file_id=None, is_deleted=True)
        )
        result = await session.execute(stmt)
        return result.rowcount

    @classmethod
    async def get_last_messages_for_chats(
        cls, session: AsyncSession, chat_ids: list[int]
    ) -> dict[int, tuple[str | None, Any, bool]]:
        if not chat_ids:
            return {}

        row_num = (
            func.row_number()
            .over(
                partition_by=cls.model.chat_id,
                order_by=cls.model.sent_at.desc(),
            )
            .label('row_num')
        )

        subq = (
            select(
                cls.model.chat_id,
                cls.model.message_text,
                cls.model.sent_at,
                cls.model.is_deleted,
                row_num,
            )
            .where(cls.model.chat_id.in_(chat_ids))
            .subquery()
        )

        stmt = select(
            subq.c.chat_id,
            subq.c.message_text,
            subq.c.sent_at,
            subq.c.is_deleted,
        ).where(subq.c.row_num == 1)

        result = await session.execute(stmt)
        return {
            row.chat_id: (row.message_text, row.sent_at, row.is_deleted)
            for row in result.all()
        }


class FileDAO(BaseDAO[File]):
    model = File

    @classmethod
    async def find_by_ids(
        cls, session: AsyncSession, file_ids: list[int]
    ) -> Sequence[File]:
        if not file_ids:
            return []
        stmt = select(cls.model).where(cls.model.id.in_(file_ids))
        result = await session.execute(stmt)
        return result.scalars().all()
