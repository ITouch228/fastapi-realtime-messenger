"""Session manager: maps refresh tokens → user_id in Redis."""

import uuid

from app.config import settings
from app.services.redis_client import get_redis


def generate_refresh_key() -> str:
    """Generate a random refresh key (UUID)."""
    return str(uuid.uuid4())


async def create_session(user_id: int) -> str:
    """Create a new session, return refresh key."""
    key = generate_refresh_key()
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400  # seconds
    redis = await get_redis()
    await redis.set(key, str(user_id), ex=ttl)
    return key


async def get_session_user_id(refresh_key: str) -> int | None:
    """Get user_id for a refresh key, or None if expired/invalid."""
    redis = await get_redis()
    raw = await redis.get(refresh_key)
    if raw is None:
        return None
    return int(raw)


async def remove_session(refresh_key: str) -> None:
    """Remove session (invalidate refresh key)."""
    redis = await get_redis()
    await redis.delete(refresh_key)


async def verify_session(session_id: str) -> bool:
    """Check if session_id exists in redis (active)."""
    redis = await get_redis()
    result = await redis.exists(session_id)
    return bool(result)
