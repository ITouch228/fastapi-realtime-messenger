from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

ModelT = TypeVar('ModelT', bound=Base)


class BaseDAO(Generic[ModelT]):
    model: type[ModelT]

    @classmethod
    async def add(cls, session: AsyncSession, **values: Any) -> ModelT:
        instance = cls.model(**values)
        session.add(instance)
        await session.flush()
        await session.refresh(instance)
        return instance

    @classmethod
    async def find_one_or_none(
        cls,
        session: AsyncSession,
        **filter_by: Any,
    ) -> ModelT | None:
        stmt = select(cls.model).filter_by(**filter_by)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def find_all(
        cls,
        session: AsyncSession,
        limit: int | None = None,
        offset: int = 0,
        **filter_by: Any,
    ) -> Sequence[ModelT]:
        stmt = select(cls.model).filter_by(**filter_by).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()
