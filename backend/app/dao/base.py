from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base


class BaseDAO[ModelT: Base]:
    """Обобщённый DAO: базовые add/находка по фильтру для ORM-модели."""

    model: type[ModelT]

    @classmethod
    async def add(cls, session: AsyncSession, **values: Any) -> ModelT:
        """Вставить строку, вернуть объект со сгенерированными колонками (id, *_at)."""
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
        """Первая строка по равенству колонок из filter_by, либо None."""
        stmt = select(cls.model).filter_by(**filter_by)
        result = await session.execute(stmt)
        return cast(ModelT | None, result.scalar_one_or_none())
