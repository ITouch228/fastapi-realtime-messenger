from fastapi import Depends
from jose import JWTError
from redis import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import AppError, NotFoundError, UnauthorizedError
from app.schemas import UserCreate, UserInDB, UserLogin, UserResponse
from app.services.session_manager import SessionManager, get_session_manager
from app.services.users import UserManager
from app.utils import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    get_access_token_from_cookie,
    get_logger,
    get_password_hash,
    verify_password,
    verify_token,
)

logger = get_logger(__name__)


class AuthManager:
    """Сервис для работы с аутенфикацией пользователей."""

    @staticmethod
    def _generate_tokens(session_id: str, user_id: int) -> tuple[str, str]:
        """Генерирует access/refresh токены; переводит ошибки в AppError."""
        try:
            access_token = create_access_token(session_id=session_id)
            refresh_token = create_refresh_token(session_id=session_id)
            return access_token, refresh_token
        except (JWTError, RedisError):
            logger.exception('Ошибка генерации токена для пользователя: %s', user_id)
            raise AppError(detail='Внутренняя ошибка сервера')

    @staticmethod
    async def create_session(
        session_manager: SessionManager, user_id: int
    ) -> tuple[str, str]:
        """Создаёт новую сессию и токены для пользователя."""
        session_id = await session_manager.create(user_id)
        return AuthManager._generate_tokens(session_id, user_id)

    @staticmethod
    async def revoke_session(
        session_manager: SessionManager, access_token: str | None
    ) -> None:
        """Отзывает сессию по access-токену (logout)."""
        if not access_token:
            return
        session_id = verify_token(access_token, token_type='access')
        if session_id:
            await session_manager.remove(session_id)

    @staticmethod
    async def rotate_session(
        session: AsyncSession,
        session_manager: SessionManager,
        refresh_token: str | None,
    ) -> tuple[str, str]:
        """
        Ротирует сессию по refresh-токену: проверяет, отзывает старую,
        создаёт новую и возвращает пару токенов. Бросает UnauthorizedError.
        """
        if not refresh_token:
            raise UnauthorizedError(detail='Не передан refresh токен')

        session_id = verify_token(refresh_token, token_type='refresh')
        if not session_id:
            raise UnauthorizedError(detail='Неверный refresh токен')

        user_id = await session_manager.get_user_id(session_id)
        if user_id is None:
            raise UnauthorizedError(detail='Сессия истекла')

        # get_active бросает NotFoundError/UnauthorizedError; при неактивном
        # или удалённом пользователе обязательно отзываем старую сессию
        try:
            await UserManager.get_active(session=session, user_id=user_id)
        except (NotFoundError, UnauthorizedError):
            await session_manager.remove(session_id)
            raise UnauthorizedError(detail='Пользователь не найден')

        await session_manager.remove(session_id)
        new_session_id = await session_manager.create(user_id)
        return AuthManager._generate_tokens(new_session_id, user_id)

    @staticmethod
    async def create_user(session: AsyncSession, user_data: UserCreate) -> UserInDB:
        logger.info(
            'Попытка регистрации нового пользователя: %s, %s',
            user_data.email,
            user_data.username,
        )
        user = await UserManager.create(
            session=session,
            username=user_data.username,
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
        )
        logger.info('Успешная регистрация пользователя: %s', user.id)
        return user

    @staticmethod
    async def authenticate_user(
        session: AsyncSession, user_data: UserLogin
    ) -> UserInDB:
        logger.info('Попытка входа пользователя с логином: %s', user_data.login)

        user = await UserManager.get_by_login(session=session, login=user_data.login)

        if not user or not user.is_active:
            verify_password(user_data.password, DUMMY_PASSWORD_HASH)
            logger.warning(
                'Попытка входа несуществующего пользователя: %s', user_data.login
            )
            raise UnauthorizedError(detail='Неверный пароль')

        if not verify_password(user_data.password, user.hashed_password):
            logger.warning(
                'Неверный пароль для пользователя с логином: %s', user_data.login
            )
            raise UnauthorizedError(detail='Неверный пароль')

        logger.info('Успешный вход пользователя: %s', user.id)
        return user

    @staticmethod
    async def get_current_user_from_cookie(
        session: AsyncSession = Depends(get_session),
        access: str = Depends(get_access_token_from_cookie),
        session_manager: SessionManager = Depends(get_session_manager),
    ) -> UserResponse | None:
        # TODO: [SMELL] Depends() внутри static method — анти-паттерн.
        # FastAPI обрабатывает это, но метод не может быть вызван напрямую
        # без DI-контейнера. Лучше вынести в отдельный dependency-функцию.
        # docs/architecture.md §5: 🟡 Depends внутри AuthManager
        if not access:
            return None

        session_id = verify_token(access, token_type='access')
        if not session_id:
            return None

        user_id = await session_manager.get_user_id(session_id)
        if user_id is None:
            logger.warning('Сессия истекла или отозвана: session_id=%s', session_id)
            return None

        return await UserManager.get_active(session=session, user_id=user_id)

    @staticmethod
    async def get_current_user(
        session: AsyncSession = Depends(get_session),
        access: str = Depends(get_access_token_from_cookie),
        session_manager: SessionManager = Depends(get_session_manager),
    ) -> UserResponse:
        current_user = await AuthManager.get_current_user_from_cookie(
            session=session, access=access, session_manager=session_manager
        )
        if current_user is None:
            raise UnauthorizedError('Не аутентифицирован')

        return current_user
