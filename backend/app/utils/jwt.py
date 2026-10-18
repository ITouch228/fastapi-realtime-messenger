from datetime import UTC, datetime, timedelta

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


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
                'Несоответствие типа токена: ожидание %s, получено %s',
                token_type,
                token_type_claim,
            )
            return None

        if session_id is None:
            return None
        return str(session_id)
    except ExpiredSignatureError:
        logger.warning('Токен истёк')
        return None
    except JWTError:
        logger.exception('Ошибка JWT')
        return None
    except (ValueError, TypeError):
        logger.exception('Ошибка парсинга токена')
        return None
