"""Unit-контракты сессий и ротации JWT без внешнего Redis/PostgreSQL."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.exceptions import NotFoundError, UnauthorizedError
from app.services.auth import AuthManager
from app.services.session_manager import SessionManager


class SessionManagerUnitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = AsyncMock()
        self.sessions = SessionManager(self.redis, ttl_seconds=3600)

    async def test_create_uses_expiring_redis_key(self):
        with patch.object(
            SessionManager, 'generate_session_id', return_value='unique-session'
        ):
            result = await self.sessions.create(42)
        self.assertEqual(result, 'unique-session')
        self.redis.set.assert_awaited_once_with('unique-session', '42', ex=3600)

    async def test_missing_session_is_not_authenticated(self):
        self.redis.get.return_value = None
        self.assertIsNone(await self.sessions.get_user_id('expired'))

    async def test_existing_session_resolves_user(self):
        self.redis.get.return_value = '42'
        self.assertEqual(await self.sessions.get_user_id('active'), 42)

    async def test_remove_revokes_exact_key(self):
        await self.sessions.remove('revoked')
        self.redis.delete.assert_awaited_once_with('revoked')


class TokenRotationUnitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = AsyncMock()
        self.sessions = AsyncMock(spec=SessionManager)
        self.sessions.get_user_id.return_value = 42
        self.sessions.create.return_value = 'new-session'

    async def test_missing_refresh_does_not_query_redis(self):
        with self.assertRaises(UnauthorizedError):
            await AuthManager.rotate_session(self.session, self.sessions, None)
        self.sessions.get_user_id.assert_not_awaited()
        self.sessions.remove.assert_not_awaited()

    async def test_access_token_cannot_be_used_as_refresh(self):
        with patch('app.services.auth.verify_token', return_value=None) as verify:
            with self.assertRaises(UnauthorizedError):
                await AuthManager.rotate_session(
                    self.session, self.sessions, 'access-jwt'
                )
        verify.assert_called_once_with('access-jwt', token_type='refresh')
        self.sessions.get_user_id.assert_not_awaited()
        self.sessions.remove.assert_not_awaited()

    async def test_expired_redis_session_is_not_rotated(self):
        self.sessions.get_user_id.return_value = None
        with (
            patch('app.services.auth.verify_token', return_value='old-session'),
            self.assertRaises(UnauthorizedError),
        ):
            await AuthManager.rotate_session(self.session, self.sessions, 'refresh')
        self.sessions.remove.assert_not_awaited()
        self.sessions.create.assert_not_awaited()

    async def test_inactive_user_revokes_existing_session(self):
        with (
            patch('app.services.auth.verify_token', return_value='old-session'),
            patch(
                'app.services.auth.UserManager.get_active',
                new_callable=AsyncMock,
                side_effect=NotFoundError(detail='User not found'),
            ),
            self.assertRaises(UnauthorizedError),
        ):
            await AuthManager.rotate_session(self.session, self.sessions, 'refresh')
        self.sessions.remove.assert_awaited_once_with('old-session')
        self.sessions.create.assert_not_awaited()

    async def test_valid_refresh_rotates_session_and_tokens(self):
        with (
            patch('app.services.auth.verify_token', return_value='old-session'),
            patch(
                'app.services.auth.UserManager.get_active',
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id=42),
            ),
            patch.object(
                AuthManager,
                '_generate_tokens',
                return_value=('new-access', 'new-refresh'),
            ) as generate,
        ):
            result = await AuthManager.rotate_session(
                self.session, self.sessions, 'refresh'
            )
        self.assertEqual(result, ('new-access', 'new-refresh'))
        self.sessions.get_user_id.assert_awaited_once_with('old-session')
        self.sessions.remove.assert_awaited_once_with('old-session')
        self.sessions.create.assert_awaited_once_with(42)
        generate.assert_called_once_with('new-session', 42)

    async def test_logout_revokes_access_session(self):
        with patch('app.services.auth.verify_token', return_value='session-id'):
            await AuthManager.revoke_session(self.sessions, 'access')
        self.sessions.remove.assert_awaited_once_with('session-id')

    async def test_invalid_access_token_does_not_revoke_session(self):
        with patch('app.services.auth.verify_token', return_value=None):
            await AuthManager.revoke_session(self.sessions, 'invalid')
        self.sessions.remove.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
