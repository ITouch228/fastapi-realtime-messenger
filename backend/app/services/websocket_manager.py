import asyncio

from fastapi import WebSocket, WebSocketDisconnect


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
        """Отправить payload набору пользователей параллельно (батчем).

        Отправки идут одновременно, а не одна за другой: время рассылки
        больше не растёт линейно от числа получателей.
        """
        await asyncio.gather(
            *(self.send_personal_message(message, user_id) for user_id in user_ids)
        )

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
