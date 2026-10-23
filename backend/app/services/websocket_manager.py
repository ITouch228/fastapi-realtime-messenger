from fastapi import WebSocket, WebSocketDisconnect


class WebSocketManager:
    """Класс для управления активными websocket подключениями"""

    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int) -> bool:
        await websocket.accept()
        was_offline = user_id not in self.active_connections
        self.active_connections.setdefault(user_id, []).append(websocket)
        return was_offline

    def disconnect(self, websocket: WebSocket, user_id: int) -> bool:
        conns = self.active_connections.get(user_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active_connections.pop(user_id, None)
                return True
        return False

    def is_online(self, user_id: int) -> bool:
        return bool(self.active_connections.get(user_id))

    async def send_personal_message(self, message: dict, user_id: int) -> None:
        conns = self.active_connections.get(user_id, [])
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
            self.disconnect(conn, user_id)

    async def broadcast(
        self, message: dict, exclude_user_ids: list[int] | None = None
    ) -> None:
        if exclude_user_ids is None:
            exclude_user_ids = []
        dead: list[tuple[WebSocket, int]] = []
        for user_id, connections in list(self.active_connections.items()):
            if user_id in exclude_user_ids:
                continue
            for connection in list(connections):
                if connection is None:
                    continue
                try:
                    await connection.send_json(message)
                except (WebSocketDisconnect, OSError, RuntimeError):
                    dead.append((connection, user_id))
        for conn, uid in dead:
            self.disconnect(conn, uid)


manager = WebSocketManager()
