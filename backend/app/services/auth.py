from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import UserDAO
from app.database import get_session
from app.schemas.user import UserInDB, UserResponse
from app.services.session_manager import SessionManager, get_session_manager
from app.utils.cookies import get_access_token_from_cookie
from app.utils.jwt import verify_token
from app.utils.logging_config import get_logger
from app.utils.security import DUMMY_PASSWORD_HASH, get_password_hash, verify_password

logger = get_logger(__name__)


async def authenticate_user(
    session: AsyncSession, login: str, password: str
) -> UserInDB | None:
    user = await UserDAO.find_by_username_or_email(session=session, login=login)

    if not user or not user.is_active:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return UserInDB.model_validate(user)


async def create_user(
    session: AsyncSession, username: str, email: str, password: str
) -> UserInDB:
    user_dict = {
        'username': username,
        'email': email,
        'hashed_password': get_password_hash(password),
    }
    user = await UserDAO.add(session=session, **user_dict)
    return UserInDB.model_validate(user)


async def get_current_user_from_cookie(
    session: AsyncSession = Depends(get_session),
    access: str = Depends(get_access_token_from_cookie),
    session_manager: SessionManager = Depends(get_session_manager),
) -> UserResponse | None:
    if not access:
        return None

    session_id = verify_token(access, token_type='access')
    if not session_id:
        return None

    user_id = await session_manager.get_user_id(session_id)
    if user_id is None:
        logger.warning('Сессия истекла или отозвана: session_id=%s', session_id)
        return None

    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if user is None:
        logger.warning('Пользователь %s не найден, но сессия валидна', user_id)
        return None

    if not user.is_active:
        logger.warning('Неактивный пользователь попытался доступ: user_id=%s', user_id)
        return None

    return UserResponse.model_validate(user)


async def get_current_user(
    current_user: UserResponse | None = Depends(get_current_user_from_cookie),
) -> UserResponse:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Не аутентифицирован',
        )

    return current_user
