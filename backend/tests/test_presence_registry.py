"""Проверки контрактов общего presence, используемого всеми воркерами."""

import unittest
from unittest.mock import AsyncMock, patch

from app.services import presence_registry


class PresenceRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_join_uses_one_atomic_redis_operation(self):
        redis = AsyncMock()
        redis.eval.return_value = 1
        with patch.object(presence_registry, 'get_redis', return_value=redis):
            self.assertTrue(await presence_registry.join(17, 'tab-a'))
        args = redis.eval.await_args.args
        self.assertEqual(args[1], 2)
        self.assertEqual(args[2], 'itmessage:presence:user:17')
        self.assertEqual(args[3], presence_registry.USERS_KEY)

    async def test_offline_transition_is_global(self):
        redis = AsyncMock()
        redis.eval.return_value = 0
        with patch.object(presence_registry, 'get_redis', return_value=redis):
            self.assertFalse(await presence_registry.leave(17, 'tab-a'))

    async def test_online_users_are_not_local_to_worker(self):
        redis = AsyncMock()
        redis.eval.return_value = ['12', '17']
        with patch.object(presence_registry, 'get_redis', return_value=redis):
            self.assertEqual(await presence_registry.online_user_ids(), {12, 17})


if __name__ == '__main__':
    unittest.main()
