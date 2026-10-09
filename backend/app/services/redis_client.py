"""Redis client for session storage."""

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get (or create) async Redis connection."""
    global _client, _pool

    if _client is not None:
        return _client

    _pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    _client = aioredis.Redis(connection_pool=_pool)
    return _client


async def close_redis():
    """Close Redis connection pool."""
    global _client, _pool

    if _client is not None:
        await _client.close()
        _client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
