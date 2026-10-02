from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, Security, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dao.dao import ChatDAO, MessageDAO, UserDAO
from app.database import get_session
from app.schemas.user import UserInDB
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


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
    if not chats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='File not found'
        )

    if not any(current_user.id in (chat.users or []) for chat in chats):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='File not found'
        )


def require_user(current_user: UserInDB | None) -> UserInDB:
    if current_user is None:
        raise HTTPException(status_code=401, detail='Not authenticated')
    return current_user


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> UserInDB | None:
    user = await UserDAO.find_one_or_none(session=session, username=username)
    if not user:
        verify_password(password, '$2b$12$dummy_hash_for_timing_attack_prevention')
        return None

    user_in_db = UserInDB.model_validate(user)
    if not verify_password(password, user_in_db.hashed_password):
        return None
    return user_in_db


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({'exp': expire, 'type': 'access'})
    encoded_jwt = jwt.encode(
        to_encode, settings.PRIVATE_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({'exp': expire, 'type': 'refresh'})
    encode_jwt = jwt.encode(
        to_encode, settings.PRIVATE_KEY, algorithm=settings.ALGORITHM
    )
    return encode_jwt


def verify_token(token: str, token_type: str = 'access'):
    try:
        payload = jwt.decode(
            token, settings.PUBLIC_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get('sub')
        token_type_claim = payload.get('type')

        # Проверяем тип токена, если указан
        if token_type and token_type_claim != token_type:
            logger.warning(
                f'Token type mismatch: expected {token_type}, got {token_type_claim}'
            )
            return False

        if user_id is None:
            return False
        return int(user_id)
    except jwt.ExpiredSignatureError:
        logger.warning('Token has expired')
        return False
    except jwt.JWTError as e:
        logger.error(f'JWT Error: {str(e)}')
        return False
    except (ValueError, TypeError) as e:
        logger.error(f'Token parsing error: {str(e)}')
        return False


def get_token_from_access_cookie(
    access: str | None = Cookie(default=None, alias='access'),
):
    if not access:
        return None
    return access


async def get_current_user_from_cookie(
    session: AsyncSession = Depends(get_session),
    access: str = Security(get_token_from_access_cookie),
) -> UserInDB | None:
    if not access:
        return None

    user_id = verify_token(access, token_type='access')
    if not user_id:
        return None

    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if user is None:
        return None

    return UserInDB.model_validate(user)
