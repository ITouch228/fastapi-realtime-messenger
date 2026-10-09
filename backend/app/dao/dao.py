from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, desc, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.base import BaseDAO
from app.models.chat import Chat
from app.models.file import File
from app.models.message import Message
from app.models.user import User


class UserDAO(BaseDAO):
    model = User

    @classmethod
    async def seach_users_by_query(
        cls, session: AsyncSession, query: str
    ) -> Any | None:
        try:
            # Security: Use SQLAlchemy's parameterized queries to prevent SQL injection
            search_pattern = f'%{query}%'
            stmt = select(cls.model).filter(cls.model.username.ilike(search_pattern))
            result = await session.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError as e:
            await session.rollback()
            raise e


class ChatDAO(BaseDAO):
    model = Chat

    @classmethod
    async def get_all_user_chats(
        cls, session: AsyncSession, user_id: int
    ) -> Sequence[Chat] | None:
        query = (
            select(Chat)
            .where(Chat.users.contains([user_id]))
            .order_by(Chat.id.desc())
            .limit(100)
        )
        result = await session.execute(query)
        return result.scalars().all()

    @classmethod
    async def search_chats(
        cls, session: AsyncSession, current_user_id: int, user_id: int
    ) -> Sequence[Chat] | None:
        query = (
            select(Chat)
            .where(
                Chat.users.contains([current_user_id]),
                Chat.users.contains([user_id]),
            )
            .order_by(Chat.id.desc())
            .limit(100)
        )
        result = await session.execute(query)
        return result.scalars().all()

    @classmethod
    async def delete_chat(cls, session: AsyncSession, chat_id: int):
        try:
            query = delete(cls.model).filter_by(id=chat_id)
            await session.execute(query)
            await session.commit()
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            raise e


class MessageDAO(BaseDAO):
    model = Message

    @classmethod
    async def find_all_or_none(
        cls,
        session: AsyncSession,
        order_by: str | None = None,
        limit: int | None = None,
        **filter_by,
    ) -> list | None:
        query = select(cls.model).filter_by(**filter_by)

        if order_by:
            # Security: Validate the order_by parameter to prevent SQL injection
            allowed_fields = [column.name for column in cls.model.__table__.columns]
            if ' desc' in order_by:
                field_name = order_by[:-5].strip()
                if field_name in allowed_fields:
                    query = query.order_by(desc(getattr(cls.model, field_name)))
            else:
                field_name = order_by.strip()
                if field_name in allowed_fields:
                    query = query.order_by(getattr(cls.model, field_name))

        if limit:
            # Security: Validate limit parameter
            if limit < 0 or limit > 100:  # Set reasonable upper limit
                limit = 1000
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def delete_message(cls, session: AsyncSession, message_id: int) -> bool:
        try:
            query = (
                update(cls.model)
                .where(cls.model.id == message_id)
                .values(message_text='Удалено', message_file_id=None)
            )
            await session.execute(query)
            await session.commit()
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            raise e


class FileDAO(BaseDAO):
    model = File
