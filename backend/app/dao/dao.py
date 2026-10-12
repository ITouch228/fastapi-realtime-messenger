from collections.abc import Sequence
from typing import Any, Literal

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.base import BaseDAO
from app.models.chat import Chat
from app.models.file import File
from app.models.message import Message
from app.models.user import User


class UserDAO(BaseDAO[User]):
    model = User

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
    async def find_by_username_or_email(
        cls, session: AsyncSession, login: str
    ) -> User | None:
        stmt = select(cls.model).where(
            or_(cls.model.username == login, cls.model.email == login.lower())
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


class ChatDAO(BaseDAO[Chat]):
    model = Chat

    @classmethod
    async def find_by_ids_with_user(
        cls, session: AsyncSession, chat_ids: list[int], user_id: int
    ) -> list[Chat]:
        stmt = select(Chat).where(
            Chat.id.in_(chat_ids),
            Chat.users.contains([user_id]),
        )
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def get_user_chats(
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
    async def delete_chat(cls, session: AsyncSession, chat_id: int) -> int:
        stmt = delete(cls.model).where(cls.model.id == chat_id)
        result = await session.execute(stmt)
        return result.rowcount


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
    async def list_messages(
        cls,
        session: AsyncSession,
        order_by: Literal['id', 'created_at', 'updated_at', 'sent_at'] = 'id',
        descending: bool = False,
        limit: int = 100,
        offset: int = 0,
        **filter_by: Any,
    ) -> Sequence[Message]:
        field = getattr(cls.model, order_by)
        stmt = (
            select(cls.model)
            .filter_by(**filter_by)
            .order_by(field.desc() if descending else field.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def soft_delete_message(cls, session: AsyncSession, message_id: int) -> int:
        stmt = (
            update(cls.model)
            .where(cls.model.id == message_id)
            .values(message_text=None, message_file_id=None, is_deleted=True)
        )
        result = await session.execute(stmt)
        return result.rowcount


class FileDAO(BaseDAO[File]):
    model = File
