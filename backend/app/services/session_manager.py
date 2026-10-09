import uuid

import redis.asyncio as aioredis

from app.config import settings
from app.services.redis_client import get_redis


class SessionManager:
    """Хранит сессии в Redis: ключ session_id, значение user_id."""

    def __init__(self, redis: aioredis.Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def generate_session_id() -> str:
        """Generate a random session id (UUID)."""
        return str(uuid.uuid4())

    async def create(self, user_id: int) -> str:
        """Create a new session, return session_id."""
        session_id = self.generate_session_id()
        await self._redis.set(session_id, str(user_id), ex=self._ttl_seconds)
        return session_id

    async def get_user_id(self, session_id: str) -> int | None:
        """Get user_id for a session_id, or None if expired/invalid."""
        raw = await self._redis.get(session_id)
        if raw is None:
            return None
        return int(raw)

    async def remove(self, session_id: str) -> None:
        """Remove session (invalidate session_id)."""
        await self._redis.delete(session_id)

    async def exists(self, session_id: str) -> bool:
        """Check if session_id exists in redis (active)."""
        return bool(await self._redis.exists(session_id))


async def get_session_manager() -> SessionManager:
    """FastAPI dependency: build SessionManager with the shared Redis client."""
    redis = await get_redis()
    return SessionManager(
        redis=redis,
        ttl_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
