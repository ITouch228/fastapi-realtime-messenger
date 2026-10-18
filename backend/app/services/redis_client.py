import asyncio

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_client: aioredis.Redis | None = None
_lock = asyncio.Lock()


async def get_redis() -> aioredis.Redis:
    """Получение клиента Redis (ленивая инициализация одного пула)."""
    global _client, _pool  # noqa: PLW0603

    # Быстрый путь без блокировки для уже инициализированного клиента.
    if _client is not None:
        return _client

    # Медленный путь: один победитель создаёт пул, остальные ждут на локе.
    async with _lock:
        # Повторная проверка под локом — другие задачи могли инициализировать
        # клиент, пока эта задача ждала блокировку.
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
    """Закрытие клиента Redis."""
    global _client, _pool  # noqa: PLW0603

    async with _lock:
        if _client is not None:
            await _client.close()
            _client = None
        if _pool is not None:
            await _pool.aclose()
            _pool = None
