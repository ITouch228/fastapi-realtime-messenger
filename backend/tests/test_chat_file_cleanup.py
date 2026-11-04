"""Регрессионные тесты транзакционного outbox при удалении чатов."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from app.models.file_cleanup_task import FileCleanupTask
from app.routes.chats import delete_chat
from app.services.files import FileManager


class ChatDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_attempt_only_after_commit(self):
        session = SimpleNamespace(commit=AsyncMock())
        user = SimpleNamespace(id=7)
        with (
            patch('app.routes.chats.ChatManager.delete') as delete,
            patch('app.routes.chats.process_file_cleanup_batch') as process,
        ):
            delete.return_value = ['42/photo.webp']
            order = Mock()
            order.attach_mock(delete, 'delete')
            order.attach_mock(session.commit, 'commit')
            order.attach_mock(process, 'process')
            await delete_chat(42, user, session, None)
            self.assertEqual(
                order.mock_calls,
                [
                    call.delete(chat_id=42, user_id=7, session=session),
                    call.commit(),
                    call.process(),
                ],
            )

    async def test_failed_commit_does_not_run_worker(self):
        session = SimpleNamespace(commit=AsyncMock(side_effect=RuntimeError('DB down')))
        user = SimpleNamespace(id=7)
        with (
            patch('app.routes.chats.ChatManager.delete') as delete,
            patch('app.routes.chats.process_file_cleanup_batch') as process,
        ):
            delete.return_value = ['42/photo.webp']
            with self.assertRaisesRegex(RuntimeError, 'DB down'):
                await delete_chat(42, user, session, None)
            process.assert_not_awaited()

    async def test_db_phase_enqueues_paths_within_transaction(self):
        session = Mock()
        with (
            patch('app.services.files.FileDAO.find_by_chat') as find,
            patch('app.services.files.FileDAO.delete_by_chat') as delete,
        ):
            find.return_value = [
                SimpleNamespace(file_path='42/photo.webp'),
                SimpleNamespace(file_path='42/document.pdf'),
            ]
            paths = await FileManager.delete_chat_files(session, 42)
            self.assertEqual(paths, ['42/photo.webp', '42/document.pdf'])
            tasks = list(session.add_all.call_args.args[0])
            self.assertEqual(
                [task.file_path for task in tasks],
                ['42/photo.webp', '42/document.pdf'],
            )
            self.assertTrue(all(isinstance(task, FileCleanupTask) for task in tasks))
            delete.assert_awaited_once_with(session=session, chat_id=42)

    async def test_post_commit_cleanup_failure_does_not_fail_delete(self):
        session = SimpleNamespace(commit=AsyncMock())
        user = SimpleNamespace(id=7)
        with (
            patch('app.routes.chats.ChatManager.delete') as delete,
            patch(
                'app.routes.chats.process_file_cleanup_batch',
                side_effect=RuntimeError('disk unavailable'),
            ),
        ):
            delete.return_value = ['42/photo.webp']
            await delete_chat(42, user, session, None)
            session.commit.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
