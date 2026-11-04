"""Проверка общего Redis-хранилища для ограничения запросов."""

import unittest

from limits.storage import RedisStorage

from app.services.limiter import rate_limiter


class SharedRateLimitTests(unittest.TestCase):
    def test_rate_limit_uses_redis_instead_of_process_memory(self):
        self.assertIsInstance(rate_limiter._storage, RedisStorage)


if __name__ == '__main__':
    unittest.main()
