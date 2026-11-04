"""Интеграционные проверки Redis Pub/Sub и presence на независимых менеджерах.

Запуск: REDIS_INTEGRATION_TESTS=1 REDIS_INTEGRATION_URL=redis://localhost:6379/15
python -m unittest discover -s tests -p 'test_integration_*.py' -v
"""

import asyncio
import json
import os
import sys
import textwrap
import unittest
from unittest.mock import AsyncMock, patch

from redis.asyncio import Redis

from app.services import presence_registry
from app.services.websocket_manager import WS_EVENTS_CHANNEL, WebSocketManager

RUN_INTEGRATION = os.getenv('REDIS_INTEGRATION_TESTS') == '1'


@unittest.skipUnless(RUN_INTEGRATION, 'Требуется тестовый Redis')
class RedisMultiworkerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = os.getenv('REDIS_INTEGRATION_URL', 'redis://localhost:6379/15')
        self.redis = Redis.from_url(url, decode_responses=True)
        await self.redis.ping()
        await self.redis.flushdb()

    async def asyncTearDown(self):
        await self.redis.aclose()

    async def test_event_delivered_across_independent_managers(self):
        sender = WebSocketManager()
        recipient = WebSocketManager()
        got_message = asyncio.Event()

        async def on_send(payload):
            self.assertEqual(payload, {'type': 'new_message', 'message': 'hello'})
            got_message.set()

        socket = AsyncMock()
        socket.send_json.side_effect = on_send
        recipient.active_connections[1001] = [socket]

        with patch('app.services.websocket_manager.get_redis', return_value=self.redis):
            await sender.start()
            await recipient.start()
            try:
                await sender.send_to_users(
                    {'type': 'new_message', 'message': 'hello'}, [1001]
                )
                await asyncio.wait_for(got_message.wait(), timeout=3)
                socket.send_json.assert_awaited_once()
            finally:
                await sender.stop()
                await recipient.stop()

    async def test_delivery_to_four_separate_python_processes(self):
        """Каждый процесс имеет свою память и Redis Pub/Sub-подписку."""
        worker_code = textwrap.dedent(
            """
            import asyncio
            import json
            import os
            from unittest.mock import patch

            from redis.asyncio import Redis
            from app.services.websocket_manager import WebSocketManager

            class Socket:
                async def send_json(self, payload):
                    print(json.dumps(payload), flush=True)

            async def main():
                redis = Redis.from_url(
                    os.environ['REDIS_INTEGRATION_URL'],
                    decode_responses=True,
                )
                manager = WebSocketManager()
                user_id = int(os.environ['WS_TEST_USER_ID'])
                manager.active_connections[user_id] = [Socket()]
                with patch(
                    'app.services.websocket_manager.get_redis',
                    return_value=redis,
                ):
                    await manager.start()
                    print('READY', flush=True)
                    try:
                        await asyncio.sleep(10)
                    finally:
                        await manager.stop()
                        await redis.aclose()

            asyncio.run(main())
            """
        )
        processes = []
        ids = [2101, 2102, 2103, 2104]
        try:
            for user_id in ids:
                env = dict(os.environ, WS_TEST_USER_ID=str(user_id))
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    '-c',
                    worker_code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                processes.append(process)
            for process in processes:
                ready = await asyncio.wait_for(process.stdout.readline(), timeout=5)
                self.assertEqual(ready.strip(), b'READY')

            payload = {'type': 'new_message', 'message': 'four workers'}
            await self.redis.publish(
                WS_EVENTS_CHANNEL,
                json.dumps({'user_ids': ids, 'payload': payload}),
            )
            for process in processes:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=5)
                self.assertEqual(json.loads(line), payload)
        finally:
            for process in processes:
                if process.returncode is None:
                    process.terminate()
            await asyncio.gather(*(process.wait() for process in processes))

    async def test_two_workers_share_presence_and_last_tab_wins(self):
        first = WebSocketManager()
        second = WebSocketManager()
        tab_a = AsyncMock()
        tab_b = AsyncMock()
        user_id = 1099
        with patch.object(presence_registry, 'get_redis', return_value=self.redis):
            self.assertTrue(await first.connect(tab_a, user_id))
            self.assertFalse(await second.connect(tab_b, user_id))
            self.assertTrue(await first.is_online(user_id))
            self.assertIn(user_id, await second.online_user_ids())
            self.assertFalse(await first.disconnect(tab_a, user_id))
            self.assertTrue(await second.is_online(user_id))
            self.assertTrue(await second.disconnect(tab_b, user_id))
            self.assertFalse(await first.is_online(user_id))

    async def test_presence_versions_increase_only_on_global_transitions(self):
        """Версии назначаются атомарно Redis даже между разными воркерами."""
        user_id = 1199
        first = WebSocketManager()
        second = WebSocketManager()
        tab_a = AsyncMock()
        tab_b = AsyncMock()

        with patch.object(presence_registry, 'get_redis', return_value=self.redis):
            online_v1 = await first.connect(tab_a, user_id)
            self.assertGreater(online_v1, 0)
            self.assertEqual(await second.connect(tab_b, user_id), 0)
            self.assertEqual(await first.disconnect(tab_a, user_id), 0)
            offline_v2 = await second.disconnect(tab_b, user_id)
            self.assertEqual(offline_v2, online_v1 + 1)
            online_v3 = await first.connect(tab_a, user_id)
            self.assertEqual(online_v3, offline_v2 + 1)
            self.assertEqual(await first.disconnect(tab_a, user_id), online_v3 + 1)

    async def test_expired_lease_disappears_from_global_online_index(self):
        user_id = 1098
        await self.redis.zadd(presence_registry.USERS_KEY, {str(user_id): 1})
        with patch.object(presence_registry, 'get_redis', return_value=self.redis):
            self.assertFalse(await presence_registry.is_online(user_id))
            self.assertNotIn(user_id, await presence_registry.online_user_ids())


if __name__ == '__main__':
    unittest.main()
