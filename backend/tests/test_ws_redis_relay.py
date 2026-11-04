"""Проверки межпроцессной маршрутизации WebSocket через Redis."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from redis.exceptions import RedisError

from app.services.websocket_manager import WS_EVENTS_CHANNEL, WebSocketManager


class RedisRelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_one_event_to_unique_recipients(self):
        manager = WebSocketManager()
        redis = AsyncMock()
        with patch('app.services.websocket_manager.get_redis', return_value=redis):
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

    async def test_redis_failure_does_not_fail_committed_http_operation(self):
        manager = WebSocketManager()
        redis = AsyncMock()
        redis.publish.side_effect = RedisError('unavailable')
        with patch('app.services.websocket_manager.get_redis', return_value=redis):
            await manager.send_to_users({'type': 'new_message'}, [5])

    async def test_failure_to_get_redis_does_not_fail_http_after_commit(self):
        manager = WebSocketManager()
        with patch(
            'app.services.websocket_manager.get_redis',
            side_effect=RedisError('unavailable'),
        ):
            await manager.send_to_users({'type': 'new_message'}, [5])

    async def test_subscription_recovers_after_reconnect_error(self):
        manager = WebSocketManager()
        received = asyncio.Event()

        class BrokenSubscription:
            async def listen(self):
                raise RedisError('connection lost')
                yield None

            async def aclose(self):
                return None

        class WorkingSubscription:
            async def listen(self):
                yield {
                    'type': 'message',
                    'data': json.dumps(
                        {'user_ids': [7], 'payload': {'type': 'new_message'}}
                    ),
                }
                await asyncio.Event().wait()

            async def aclose(self):
                return None

        first = BrokenSubscription()
        second = WorkingSubscription()
        redis = MagicMock()
        redis.pubsub.return_value = second
        second.subscribe = AsyncMock()
        manager._pubsub = first

        async def deliver(envelope):
            self.assertEqual(envelope['user_ids'], [7])
            received.set()

        manager._deliver_event = deliver
        with (
            patch('app.services.websocket_manager.get_redis', return_value=redis),
            patch('app.services.websocket_manager.asyncio.sleep', new_callable=AsyncMock),
        ):
            task = asyncio.create_task(manager._listen())
            try:
                await asyncio.wait_for(received.wait(), timeout=2)
                second.subscribe.assert_awaited_once_with(WS_EVENTS_CHANNEL)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def test_empty_recipients_do_not_publish(self):
        manager = WebSocketManager()
        with patch('app.services.websocket_manager.get_redis') as get_redis:
            await manager.send_to_users({'type': 'new_message'}, [])
        get_redis.assert_not_called()


if __name__ == '__main__':
    unittest.main()
