from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, Security, status
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dao.dao import ChatDAO, MessageDAO, UserDAO
from app.database import get_session
from app.deps import pwd_context
from app.schemas.user import UserInDB
from app.services.session_manager import SessionManager, get_session_manager
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

# Валидный bcrypt-хэш для выравнивания времени ответа при несуществующем/неактивном
# пользователе (защита от timing-атак). Пароль заведомо не совпадёт.
DUMMY_PASSWORD_HASH = '$2b$12$siY3fyd7Yxk4mCJ//ZnNpuCdTU86GWhVGg1qTgiz5shljZicyFoza'


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def ensure_can_access_file(
    file_id: int,
    current_user: UserInDB,
    session: AsyncSession,
) -> None:
    msgs = await MessageDAO.find_all_or_none(session=session, message_file_id=file_id)
    if not msgs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='File not found'
        )

    chats = [
        await ChatDAO.find_one_or_none(session=session, id=msg.chat_id) for msg in msgs
    ]
    chats = [chat for chat in chats if chat is not None]
    if not chats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='File not found'
        )

    if not any(current_user.id in (chat.users or []) for chat in chats):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='File not found'
        )


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> UserInDB | None:
    user = await UserDAO.find_one_or_none(session=session, username=username)
    if not user:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not user.is_active:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    user_in_db = UserInDB.model_validate(user)
    if not verify_password(password, user_in_db.hashed_password):
        return None
    return user_in_db


def create_access_token(session_id: str, expires_delta: timedelta | None = None) -> str:
    """Создаёт access-токен, где sub хранит session_id (ключ сессии в Redis)."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {'sub': session_id, 'exp': expire, 'type': 'access'}
    encoded_jwt = jwt.encode(
        to_encode, settings.PRIVATE_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(session_id: str) -> str:
    """Создаёт refresh-токен, где sub хранит session_id (ключ сессии в Redis)."""
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {'sub': session_id, 'exp': expire, 'type': 'refresh'}
    encode_jwt = jwt.encode(
        to_encode, settings.PRIVATE_KEY, algorithm=settings.ALGORITHM
    )
    return encode_jwt


def verify_token(token: str, token_type: str = 'access') -> str | None:
    """Декодирует JWT и возвращает session_id из sub, либо None при ошибке."""
    try:
        payload = jwt.decode(
            token, settings.PUBLIC_KEY, algorithms=[settings.ALGORITHM]
        )
        session_id = payload.get('sub')
        token_type_claim = payload.get('type')

        if token_type and token_type_claim != token_type:
            logger.warning(
                f'Token type mismatch: expected {token_type}, got {token_type_claim}'
            )
            return None

        if session_id is None:
            return None
        return str(session_id)
    except jwt.ExpiredSignatureError:
        logger.warning('Token has expired')
        return None
    except jwt.JWTError as e:
        logger.error(f'JWT Error: {str(e)}')
        return None
    except (ValueError, TypeError) as e:
        logger.error(f'Token parsing error: {str(e)}')
        return None


def get_token_from_access_cookie(
    access: str | None = Cookie(default=None, alias='access'),
):
    if not access:
        return None
    return access


async def get_current_user_from_cookie(
    session: AsyncSession = Depends(get_session),
    access: str = Security(get_token_from_access_cookie),
    session_manager: SessionManager = Depends(get_session_manager),
) -> UserInDB | None:
    if not access:
        return None

    # sub токена хранит session_id, user_id резолвим по значению ключа в Redis
    session_id = verify_token(access, token_type='access')
    if not session_id:
        return None

    user_id = await session_manager.get_user_id(session_id)
    if user_id is None:
        logger.warning(f'Session expired or revoked: session_id={session_id}')
        return None

    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if user is None:
        return None

    if not user.is_active:
        logger.warning(f'Inactive user attempted access: user_id={user_id}')
        return None

    return UserInDB.model_validate(user)


async def get_current_user(
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
) -> UserInDB:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Not authenticated',
        )

    return current_user
