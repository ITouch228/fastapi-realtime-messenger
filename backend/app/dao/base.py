from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


class BaseDAO:
    model: ClassVar[Any]

    @classmethod
    async def add(cls, session: AsyncSession, **values) -> Any | None:
        try:
            new_instance = cls.model(**values)
            session.add(new_instance)
            await session.commit()
            await session.refresh(new_instance)
            return new_instance
        except SQLAlchemyError as e:
            await session.rollback()
            raise e

    @classmethod
    async def find_one_or_none(cls, session: AsyncSession, **filter_by) -> Any | None:
        try:
            query = select(cls.model).filter_by(**filter_by)
            result = await session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await session.rollback()
            raise e

    @classmethod
    async def find_all_or_none(cls, session: AsyncSession, **filter_by) -> Any | None:
        try:
            query = select(cls.model).filter_by(**filter_by)
            result = await session.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
