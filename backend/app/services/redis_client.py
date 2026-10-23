import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def init_redis() -> None:
    """Создаёт пул и клиент Redis. Вызывается один раз при старте (lifespan)."""
    global _client, _pool  # noqa: PLW0603

    if _client is not None:
        return

    _pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    _client = aioredis.Redis(connection_pool=_pool)


async def get_redis() -> aioredis.Redis:
    """Возвращает инициализированный клиент Redis.

    Инициализация выполняется один раз в lifespan через init_redis(), поэтому
    здесь нет ленивой инициализации и блокировки. Если клиент не создан — это
    ошибка конфигурации запуска, а не рантайм-состояние.
    """
    if _client is None:
        raise RuntimeError(
            'Redis не инициализирован: init_redis() не вызван в lifespan'
        )
    return _client


async def close_redis() -> None:
    """Закрывает клиент и пул Redis. Вызывается при остановке (lifespan)."""
    global _client, _pool  # noqa: PLW0603

    if _client is not None:
        await _client.close()
        _client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
