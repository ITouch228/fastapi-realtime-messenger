"""Атомарный распределённый presence для WebSocket-подключений.

Для каждого пользователя Redis хранит ZSET токенов соединений с временем
окончания аренды. Общий индекс пользователей содержит максимальный срок
аренды; все переходы выполняются одним Lua-скриптом без гонок между воркерами.
"""

from collections.abc import Awaitable
from typing import cast
from uuid import uuid4

from app.services.redis_client import get_redis

LEASE_SECONDS = 90
USERS_KEY = 'itmessage:presence:users'
VERSIONS_KEY = 'itmessage:presence:versions'

_JOIN = """
local now = tonumber(redis.call('TIME')[1])
local expires = now + tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local was_offline = redis.call('ZCARD', KEYS[1]) == 0
redis.call('ZADD', KEYS[1], expires, ARGV[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]) * 2)
redis.call('ZADD', KEYS[2], expires, ARGV[2])
if was_offline then
    return redis.call('HINCRBY', KEYS[3], ARGV[2], 1)
end
return 0
"""

_LEAVE = """
local now = tonumber(redis.call('TIME')[1])
local removed = redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
local latest = redis.call('ZREVRANGE', KEYS[1], 0, 0, 'WITHSCORES')
if #latest == 0 then
    redis.call('ZREM', KEYS[2], ARGV[2])
    if removed == 1 then
        return redis.call('HINCRBY', KEYS[3], ARGV[2], 1)
    end
    return 0
end
redis.call('ZADD', KEYS[2], latest[2], ARGV[2])
return 0
"""

_REFRESH = """
local now = tonumber(redis.call('TIME')[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if not redis.call('ZSCORE', KEYS[1], ARGV[1]) then
    return 0
end
local expires = now + tonumber(ARGV[3])
redis.call('ZADD', KEYS[1], expires, ARGV[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]) * 2)
redis.call('ZADD', KEYS[2], expires, ARGV[2])
return 1
"""

_ONLINE = """
local now = tonumber(redis.call('TIME')[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
return redis.call('ZRANGE', KEYS[1], 0, -1)
"""

_IS_ONLINE = """
local now = tonumber(redis.call('TIME')[1])
local expires = redis.call('ZSCORE', KEYS[1], ARGV[1])
return expires and tonumber(expires) > now and 1 or 0
"""


def new_connection_id() -> str:
    """Уникальный ключ одной вкладки во всех процессах приложения."""
    return uuid4().hex


def _user_key(user_id: int) -> str:
    return f'itmessage:presence:user:{user_id}'


async def join(user_id: int, connection_id: str) -> int:
    """Вернуть версию перехода offline → online, или 0 для дополнительной вкладки."""
    redis = await get_redis()
    command = redis.eval(
        _JOIN,
        3,
        _user_key(user_id),
        USERS_KEY,
        VERSIONS_KEY,
        connection_id,
        str(user_id),
        str(LEASE_SECONDS),
    )
    return int(await cast('Awaitable[int]', command))


async def leave(user_id: int, connection_id: str) -> int:
    """Вернуть версию перехода online → offline, иначе 0."""
    redis = await get_redis()
    command = redis.eval(
        _LEAVE,
        3,
        _user_key(user_id),
        USERS_KEY,
        VERSIONS_KEY,
        connection_id,
        str(user_id),
    )
    return int(await cast('Awaitable[int]', command))


async def refresh(user_id: int, connection_id: str) -> bool:
    """Продлить аренду существующего подключения, не воскрешая закрытое."""
    redis = await get_redis()
    command = redis.eval(
        _REFRESH,
        2,
        _user_key(user_id),
        USERS_KEY,
        connection_id,
        str(user_id),
        str(LEASE_SECONDS),
    )
    return bool(await cast('Awaitable[int]', command))


async def online_user_ids() -> set[int]:
    """Множество пользователей с неистёкшими арендами во всех воркерах."""
    redis = await get_redis()
    command = redis.eval(_ONLINE, 1, USERS_KEY)
    result = await cast('Awaitable[list[str]]', command)
    return {int(value) for value in result}


async def is_online(user_id: int) -> bool:
    """Глобальный онлайн-статус конкретного пользователя."""
    redis = await get_redis()
    command = redis.eval(_IS_ONLINE, 1, USERS_KEY, str(user_id))
    return bool(await cast('Awaitable[int]', command))
