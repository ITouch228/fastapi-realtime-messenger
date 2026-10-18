from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao import UserDAO
from app.exceptions import AppError, ConflictError, NotFoundError, UnauthorizedError
from app.schemas import UserInDB, UserResponse
from app.utils import get_logger

logger = get_logger(__name__)


class UserManager:
    """Сервис для работы с пользователями."""

    @staticmethod
    async def create(
        session: AsyncSession,
        username: str,
        email: str,
        hashed_password: str,
    ) -> UserInDB:
        try:
            user = await UserDAO.add(
                session=session,
                username=username,
                email=email,
                hashed_password=hashed_password,
            )
            return UserInDB.model_validate(user)
        except IntegrityError as e:
            constraint = getattr(e.orig, 'constraint_name', '') or ''
            if 'username' in constraint:
                raise ConflictError(detail='Пользователь с таким именем уже существует')
            if 'email' in constraint:
                raise ConflictError(detail='Пользователь с таким email уже существует')
            logger.exception('Неизвестная ошибка целостности при регистрации')
            raise AppError(detail='Внутренняя ошибка сервера')

    @staticmethod
    async def get(session: AsyncSession, user_id: int) -> UserResponse:
        user = await UserDAO.find_one_or_none(session=session, id=user_id)
        if user is None:
            raise NotFoundError('Пользователь не найден')

        return UserResponse.model_validate(user)

    @staticmethod
    async def get_by_login(session: AsyncSession, login: str) -> UserInDB | None:
        user = await UserDAO.find_by_login(session=session, login=login)
        if user is None:
            return None
        return UserInDB.model_validate(user)

    @staticmethod
    async def get_active(session: AsyncSession, user_id: int) -> UserResponse | None:
        user = await UserDAO.find_one_or_none(session=session, id=user_id)
        if user is None:
            raise NotFoundError('Пользователь не найден')

        if not user.is_active:
            raise UnauthorizedError('Пользователь не активен')

        return UserResponse.model_validate(user)

    @staticmethod
    async def search(
        session: AsyncSession, query: str, limit: int = 20
    ) -> list[UserResponse]:
        users = await UserDAO.search_by_username(
            session=session, query=query, limit=limit
        )

        return [UserResponse.model_validate(user) for user in users] if users else []

    @staticmethod
    async def set_last_seen(session: AsyncSession, user_id: int, when) -> None:
        await UserDAO.update_last_seen(session=session, user_id=user_id, when=when)

    @staticmethod
    async def get_last_seen_map(
        session: AsyncSession, user_ids: list[int]
    ) -> dict[int, datetime | None]:
        return await UserDAO.get_last_seen_map(session=session, user_ids=user_ids)
