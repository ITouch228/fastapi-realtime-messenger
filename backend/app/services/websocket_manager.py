import asyncio
import json
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

from app.services import presence_registry
from app.services.redis_client import get_redis
from app.utils import get_logger

logger = get_logger(__name__)

WS_EVENTS_CHANNEL = 'itmessage:ws:events'


class WebSocketManager:
    """Управление активными websocket-подключениями.

    active_connections мутируется из разных задач (ws-циклы, HTTP-роуты,
    presence-рассылки), поэтому все изменения идут под asyncio.Lock.
    Без неё was_offline/went_offline считались бы по «рваным» данным:
    параллельные connect/disconnect одного пользователя могли дать
    и ложный приход в сеть, и ложный уход.

    Блокировка НЕ удерживается во время send_json — отправка медленным
    клиентам не стопорит остальные соединения и не приводит к взаимным
    блокировкам (disconnect из того же кода ждал бы тот же лок).
    """

    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = {}
        self._connection_ids: dict[int, str] = {}
        self._lock = asyncio.Lock()
        self._subscriber: asyncio.Task[None] | None = None
        self._pubsub: PubSub | None = None

    async def start(self) -> None:
        """Подписаться до приёма HTTP/WS, чтобы не терять первые события."""
        if self._subscriber is not None:
            return
        redis = await get_redis()
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(WS_EVENTS_CHANNEL)
        except Exception:
            await pubsub.aclose()
            raise
        self._pubsub = pubsub
        self._subscriber = asyncio.create_task(self._listen(), name='ws-redis-relay')

    async def stop(self) -> None:
        """Остановить подписку до закрытия Redis-пула."""
        task = self._subscriber
        self._subscriber = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._pubsub is not None:
            await self._pubsub.aclose()
            self._pubsub = None

    async def _listen(self) -> None:
        """Переподключать Pub/Sub при сетевом сбое или закрытии подписки."""
        while True:
            try:
                pubsub = self._pubsub
                if pubsub is None:
                    return
                async for event in pubsub.listen():
                    if event['type'] != 'message':
                        continue
                    try:
                        envelope = json.loads(event['data'])
                        await self._deliver_event(envelope)
                    except (ValueError, TypeError, KeyError):
                        logger.exception('Некорректное WebSocket-событие Redis')
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError):
                logger.exception('Потеряна подписка WebSocket Redis Pub/Sub')

            # Ошибка может произойти на любом этапе восстановления, включая
            # получение клиента и закрытие старой подписки. Не допускаем
            # завершения фоновой задачи из-за повторного сбоя Redis.
            await asyncio.sleep(1)
            replacement = None
            try:
                redis = await get_redis()
                replacement = redis.pubsub()
                await replacement.subscribe(WS_EVENTS_CHANNEL)
            except asyncio.CancelledError:
                if replacement is not None:
                    await replacement.aclose()
                raise
            except (RedisError, OSError, RuntimeError):
                logger.exception('Повторная подписка Redis недоступна')
                if replacement is not None:
                    try:
                        await replacement.aclose()
                    except (RedisError, OSError):
                        logger.warning('Не удалось закрыть неактивную подписку Redis')
                continue

            old = self._pubsub
            self._pubsub = replacement
            if old is not None:
                try:
                    await old.aclose()
                except (RedisError, OSError):
                    logger.warning('Не удалось закрыть старую подписку Redis')

    async def _deliver_event(self, envelope: dict) -> None:
        """Обработать событие из Redis без повторной публикации."""
        recipients = envelope['user_ids']
        message = envelope['payload']
        await asyncio.gather(
            *(self.send_personal_message(message, user_id) for user_id in recipients)
        )

    async def connect(self, websocket: WebSocket, user_id: int) -> int:
        """Создать аренду Redis; вернуть версию глобального перехода или 0."""
        await websocket.accept()
        token = presence_registry.new_connection_id()
        version = await presence_registry.join(user_id, token)
        async with self._lock:
            self.active_connections.setdefault(user_id, []).append(websocket)
            self._connection_ids[id(websocket)] = token
        return version

    def _detach(self, websocket: WebSocket, user_id: int) -> str | None:
        """Отвязать локальный сокет и вернуть Redis-токен (под локом)."""
        token = self._connection_ids.pop(id(websocket), None)
        conns = self.active_connections.get(user_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active_connections.pop(user_id, None)
        return token

    async def disconnect(self, websocket: WebSocket, user_id: int) -> int:
        """Снять аренду; вернуть версию offline при последней вкладке."""
        async with self._lock:
            token = self._detach(websocket, user_id)
        if token is None:
            return False
        return await presence_registry.leave(user_id, token)

    async def touch(self, websocket: WebSocket, user_id: int) -> bool:
        """Продлить TTL вкладки во время входящих сообщений и ping."""
        async with self._lock:
            token = self._connection_ids.get(id(websocket))
        if token is None:
            return False
        return await presence_registry.refresh(user_id, token)

    async def is_online(self, user_id: int) -> bool:
        """Глобальный онлайн-статус с Redis TTL."""
        return await presence_registry.is_online(user_id)

    async def online_user_ids(self) -> set[int]:
        """Снимок статусов всех процессов, а не только текущего воркера."""
        return await presence_registry.online_user_ids()

    async def send_personal_message(self, message: dict, user_id: int) -> None:
        """Отправить payload всем вкладкам пользователя; мёртвые сокеты отвязать."""
        async with self._lock:
            conns = list(self.active_connections.get(user_id, ()))
        dead = []
        for conn in conns:
            if conn is None:
                continue
            try:
                await conn.send_json(message)
            except (WebSocketDisconnect, OSError, RuntimeError):
                # Сокет уже закрыт — штатная ситуация, помечаем на отключение
                dead.append(conn)
            # Прочие ошибки (например, TypeError при невалидном payload)
            # пробрасываются: это баг в коде вызывающего, а не обрыв связи
        for conn in dead:
            try:
                await self.disconnect(conn, user_id)
            except (RedisError, OSError):
                # Сокет уже удалён из локального реестра; оставшаяся
                # Redis-аренда истечёт по TTL после восстановления сервиса.
                logger.warning(
                    'Не удалось снять аренду отключённой вкладки user_id=%s',
                    user_id,
                )

    async def send_to_users(self, message: dict, user_ids: list[int]) -> None:
        """Передать событие всем воркерам через Redis Pub/Sub.

        Каждый воркер доставит его локальным вкладкам адресатов. При сбое
        публикации ошибка логируется: коммит в БД уже мог завершиться.
        """
        recipients = sorted(set(user_ids))
        if not recipients:
            return
        envelope = {'user_ids': recipients, 'payload': message}
        try:
            redis = await get_redis()
            await redis.publish(WS_EVENTS_CHANNEL, json.dumps(envelope))
        except (RedisError, OSError):
            # Сообщение уже может быть зафиксировано в PostgreSQL.
            # Ошибка Pub/Sub не должна вынуждать клиента повторно отправлять его.
            logger.exception('Не удалось опубликовать WebSocket-событие в Redis')

    async def broadcast(
        self, message: dict, exclude_user_ids: list[int] | None = None
    ) -> None:
        """Отправить payload всем подключённым, кроме указанных id."""
        excluded = set(exclude_user_ids or ())
        async with self._lock:
            targets = [
                user_id
                for user_id, conns in self.active_connections.items()
                if conns and user_id not in excluded
            ]
        await self.send_to_users(message, targets)


manager = WebSocketManager()
