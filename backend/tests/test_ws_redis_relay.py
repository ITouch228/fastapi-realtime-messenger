"""Проверки межпроцессной маршрутизации WebSocket через Redis."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services.websocket_manager import WS_EVENTS_CHANNEL, WebSocketManager


class RedisRelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_one_event_to_unique_recipients(self):
        manager = WebSocketManager()
        redis = AsyncMock()
        with patch(
            'app.services.websocket_manager.get_redis', return_value=redis
        ):
            await manager.send_to_users({'type': 'new_message'}, [3, 2, 3])
        args = redis.publish.await_args.args
        self.assertEqual(args[0], WS_EVENTS_CHANNEL)
        self.assertEqual(
            json.loads(args[1]),
            {'user_ids': [2, 3], 'payload': {'type': 'new_message'}},
        )

    async def test_recipient_worker_delivers_to_local_sockets(self):
        manager = WebSocketManager()
        socket = AsyncMock()
        manager.active_connections = {2: [socket]}
        await manager._deliver_event(
            {'user_ids': [2, 3], 'payload': {'type': 'new_message'}}
        )
        socket.send_json.assert_awaited_once_with({'type': 'new_message'})

    async def test_empty_recipients_do_not_publish(self):
        manager = WebSocketManager()
        with patch('app.services.websocket_manager.get_redis') as get_redis:
            await manager.send_to_users({'type': 'new_message'}, [])
        get_redis.assert_not_called()


if __name__ == '__main__':
    unittest.main()
