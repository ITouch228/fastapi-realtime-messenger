from fastapi import WebSocket


class ConnectionManager:
    """Класс для управления активными подключениями"""

    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        conns = self.active_connections.get(user_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active_connections.pop(user_id, None)

    async def send_personal_message(self, message: dict, user_id: int):
        conns = self.active_connections.get(user_id, [])
        dead = []
        for conn in conns:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn, user_id)

    async def broadcast(self, message: dict, exclude_user_ids: list | None = None):
        if exclude_user_ids is None:
            exclude_user_ids = []
        dead: list[tuple[WebSocket, int]] = []
        for user_id, connections in self.active_connections.items():
            if user_id in exclude_user_ids:
                continue
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead.append((connection, user_id))
        for conn, uid in dead:
            self.disconnect(conn, uid)


manager = ConnectionManager()
