"""Регрессионные тесты очистки вложений после фиксации транзакции."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from app.routes.chats import delete_chat
from app.services.files import FileManager


class ChatDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_runs_after_commit(self):
        session = SimpleNamespace(commit=AsyncMock())
        user = SimpleNamespace(id=7)
        with patch('app.routes.chats.ChatManager.delete') as delete:
            with patch('app.routes.chats.FileManager.cleanup_deleted_chat_files') as cleanup:
                delete.return_value = ['42/photo.webp']
                order = Mock()
                order.attach_mock(delete, 'delete')
                order.attach_mock(session.commit, 'commit')
                order.attach_mock(cleanup, 'cleanup')
                await delete_chat(42, user, session, None)
                self.assertEqual(
                    order.mock_calls,
                    [
                        call.delete(chat_id=42, user_id=7, session=session),
                        call.commit(),
                        call.cleanup(['42/photo.webp']),
                    ],
                )

    async def test_failed_commit_never_unlinks_files(self):
        session = SimpleNamespace(commit=AsyncMock())
        session.commit.side_effect = RuntimeError('DB down')
        user = SimpleNamespace(id=7)
        with patch('app.routes.chats.ChatManager.delete') as delete:
            with patch('app.routes.chats.FileManager.cleanup_deleted_chat_files') as cleanup:
                delete.return_value = ['42/photo.webp']
                with self.assertRaisesRegex(RuntimeError, 'DB down'):
                    await delete_chat(42, user, session, None)
                cleanup.assert_not_awaited()

    async def test_db_phase_does_not_unlink_files(self):
        find_path = 'app.services.files.FileDAO.find_by_chat'
        delete_path = 'app.services.files.FileDAO.delete_by_chat'
        unlink_path = 'app.services.files.delete_files_from_disk'
        with patch(find_path) as find:
            with patch(delete_path) as delete:
                with patch(unlink_path) as unlink:
                    find.return_value = [SimpleNamespace(file_path='42/photo.webp')]
                    session = Mock()
                    paths = await FileManager.delete_chat_files(session, 42)
                    self.assertEqual(paths, ['42/photo.webp'])
                    delete.assert_awaited_once_with(session=session, chat_id=42)
                    unlink.assert_not_awaited()

    async def test_cleanup_failure_does_not_raise(self):
        name = 'app.services.files.delete_files_from_disk'
        with patch(name, side_effect=OSError('disk unavailable')):
            await FileManager.cleanup_deleted_chat_files(['42/photo.webp'])


if __name__ == '__main__':
    unittest.main()
