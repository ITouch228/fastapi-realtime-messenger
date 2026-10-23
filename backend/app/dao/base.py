from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base


class BaseDAO[ModelT: Base]:
    model: type[ModelT]

    @classmethod
    async def add(cls, session: AsyncSession, **values: Any) -> ModelT:
        instance: ModelT = cls.model(**values)
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
