from fastapi import WebSocket, WebSocketDisconnect

from app.utils import get_logger

logger = get_logger(__name__)


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

    async def send_personal_message(self, message: dict, user_id: int):
        conns = self.active_connections.get(user_id, [])
        dead = []
        for conn in conns:
            try:
                await conn.send_json(message)
            except (ConnectionError, WebSocketDisconnect):
                dead.append(conn)
            except Exception:
                # TODO: [SMELL] except Exception — ловит RuntimeError (сокет уже закрыт),
                # json.JSONEncodeError и прочее. Лучше (RuntimeError, OSError).
                # docs/architecture.md §5: 🟡 WSMGR except Exception
                logger.exception('Не удалось отправить WS-сообщение')
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
                    # TODO: [SMELL] except Exception — ловит RuntimeError/OSError,
                    # но может скрыть json.JSONEncodeError.
                    dead.append((connection, user_id))
        for conn, uid in dead:
            self.disconnect(conn, uid)


manager = WebSocketManager()
