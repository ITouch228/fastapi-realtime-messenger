import asyncio
import json
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

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
        """Каждый воркер получает события и доставляет своим вкладкам."""
        while True:
            try:
                pubsub = self._pubsub
                if pubsub is None:
                    raise RuntimeError('Подписка Redis не инициализирована')
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
                logger.exception('Redis Pub/Sub недоступен, повтор через 1 секунду')
                await asyncio.sleep(1)
                redis = await get_redis()
                replacement = redis.pubsub()
                try:
                    await replacement.subscribe(WS_EVENTS_CHANNEL)
                except (RedisError, OSError):
                    await replacement.aclose()
                    continue
                old = self._pubsub
                self._pubsub = replacement
                if old is not None:
                    await old.aclose()

    async def _deliver_event(self, envelope: dict) -> None:
        """Обработать событие из Redis без повторной публикации."""
        recipients = envelope['user_ids']
        message = envelope['payload']
        await asyncio.gather(
            *(self.send_personal_message(message, user_id) for user_id in recipients)
        )

    async def connect(self, websocket: WebSocket, user_id: int) -> bool:
        """Принять соединение. True, если у пользователя не было других вкладок."""
        await websocket.accept()
        async with self._lock:
            was_offline = user_id not in self.active_connections
            self.active_connections.setdefault(user_id, []).append(websocket)
            return was_offline

    def _detach(self, websocket: WebSocket, user_id: int) -> bool:
        """Убрать сокет из реестра. True, если это была последняя вкладка.

        Вызывать только под self._lock.
        """
        conns = self.active_connections.get(user_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active_connections.pop(user_id, None)
                return True
        return False

    async def disconnect(self, websocket: WebSocket, user_id: int) -> bool:
        """Отвязать сокет. True, если пользователь ушёл в офлайн (вкладок больше нет)."""
        async with self._lock:
            return self._detach(websocket, user_id)

    def is_online(self, user_id: int) -> bool:
        """Есть ли у пользователя активное WS-соединение.

        Чтение без await — в asyncio другая задача не может вклиниться
        в середину, поэтому снимок согласован и блокировка не нужна.
        """
        return bool(self.active_connections.get(user_id))

    async def online_user_ids(self) -> set[int]:
        """Снимок id всех подключённых пользователей (для батч-проверок)."""
        async with self._lock:
            return {
                user_id for user_id, conns in self.active_connections.items() if conns
            }

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
        if dead:
            async with self._lock:
                for conn in dead:
                    self._detach(conn, user_id)

    async def send_to_users(self, message: dict, user_ids: list[int]) -> None:
        """Передать событие всем воркерам через Redis Pub/Sub.

        Каждый воркер доставит его локальным вкладкам адресатов. При сбое
        публикации исключение пробрасывается вызывающему коду.
        """
        recipients = sorted(set(user_ids))
        if not recipients:
            return
        redis = await get_redis()
        envelope = {'user_ids': recipients, 'payload': message}
        await redis.publish(WS_EVENTS_CHANNEL, json.dumps(envelope))

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
