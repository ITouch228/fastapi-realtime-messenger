"""Regression tests: files may be unlinked only after a successful DB commit."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.routes.chats import delete_chat
from app.services.files import FileManager


class ChatDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_runs_after_commit(self):
        session = SimpleNamespace(commit=AsyncMock())
        user = SimpleNamespace(id=7)
        with (
            patch('app.routes.chats.ChatManager.delete', new_callable=AsyncMock) as delete,
            patch(
                'app.routes.chats.FileManager.cleanup_deleted_chat_files',
                new_callable=AsyncMock,
            ) as cleanup,
        ):
            delete.return_value = ['42/photo.webp']
            calls = Mock()
            calls.attach_mock(delete, 'delete')
            calls.attach_mock(session.commit, 'commit')
            calls.attach_mock(cleanup, 'cleanup')

            await delete_chat(chat_id=42, current_user=user, session=session, _=None)

            self.assertEqual(
                calls.mock_calls,
                [
                    unittest.mock.call.delete(chat_id=42, user_id=7, session=session),
                    unittest.mock.call.commit(),
                    unittest.mock.call.cleanup(['42/photo.webp']),
                ],
            )

    async def test_failed_commit_never_unlinks_files(self):
        session = SimpleNamespace(commit=AsyncMock(side_effect=RuntimeError('DB down')))
        with (
            patch('app.routes.chats.ChatManager.delete', new_callable=AsyncMock) as delete,
            patch(
                'app.routes.chats.FileManager.cleanup_deleted_chat_files',
                new_callable=AsyncMock,
            ) as cleanup,
        ):
            delete.return_value = ['42/photo.webp']
            with self.assertRaisesRegex(RuntimeError, 'DB down'):
                await delete_chat(
                    chat_id=42,
                    current_user=SimpleNamespace(id=7),
                    session=session,
                    _=None,
                )
            cleanup.assert_not_awaited()

    async def test_db_only_phase_returns_paths_without_disk_io(self):
        with (
            patch('app.services.files.FileDAO.find_by_chat', new_callable=AsyncMock) as find,
            patch('app.services.files.FileDAO.delete_by_chat', new_callable=AsyncMock) as delete,
            patch('app.services.files.delete_files_from_disk', new_callable=AsyncMock) as unlink,
        ):
            find.return_value = [SimpleNamespace(file_path='42/photo.webp')]
            session = Mock()
            paths = await FileManager.delete_chat_files(session=session, chat_id=42)
            self.assertEqual(paths, ['42/photo.webp'])
            delete.assert_awaited_once_with(session=session, chat_id=42)
            unlink.assert_not_awaited()

    async def test_cleanup_failure_does_not_change_committed_response(self):
        with patch(
            'app.services.files.delete_files_from_disk',
            new_callable=AsyncMock,
            side_effect=OSError('disk unavailable'),
        ):
            await FileManager.cleanup_deleted_chat_files(['42/photo.webp'])


if __name__ == '__main__':
    unittest.main()
