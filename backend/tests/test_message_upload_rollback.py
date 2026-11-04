"""Откат файловых побочных эффектов неудачной отправки сообщения."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.exceptions import AppError
from app.routes.messages import send_message
from app.services.files import FileManager


class MessageUploadRollbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved = SimpleNamespace(
            disk_name='a' * 32 + '.txt',
            original_name='report.txt',
            mime_type='text/plain',
            size_bytes=7,
        )
        self.upload = SimpleNamespace(
            filename='report.txt', read=AsyncMock(return_value=b'payload')
        )
        self.user = SimpleNamespace(id=7)
        self.session = SimpleNamespace(commit=AsyncMock())
        self.response = SimpleNamespace(model_dump=lambda **_: {'id': 10})

    async def send(self, *, file=True):
        return await send_message(
            chat_id='42',
            message_text='hello',
            file_name='report.txt' if file else None,
            file=self.upload if file else None,
            peer_id=None,
            client_id='test-client-id',
            current_user=self.user,
            session=self.session,
            _=None,
        )

    def mocked_dependencies(self):
        self.enterContext(
            patch('app.routes.messages.ChatManager.get', new_callable=AsyncMock)
        ).return_value = SimpleNamespace(users=[7, 8])
        self.enterContext(
            patch('app.routes.messages.save_file', new_callable=AsyncMock)
        ).return_value = self.saved
        self.file_create = self.enterContext(
            patch('app.routes.messages.FileManager.create', new_callable=AsyncMock)
        )
        self.file_create.return_value = SimpleNamespace(id=17)
        self.message_create = self.enterContext(
            patch('app.routes.messages.MessageManager.create', new_callable=AsyncMock)
        )
        self.message_create.return_value = SimpleNamespace(id=10)
        self.build_response = self.enterContext(
            patch(
                'app.routes.messages.MessageManager.build_message_response',
                new_callable=AsyncMock,
            )
        )
        self.build_response.return_value = self.response
        self.publish = self.enterContext(
            patch('app.routes.messages.manager.send_to_users', new_callable=AsyncMock)
        )
        self.cleanup = self.enterContext(
            patch(
                'app.routes.messages.FileManager.cleanup_failed_upload',
                new_callable=AsyncMock,
            )
        )

    async def test_file_registration_failure_removes_new_file(self):
        self.mocked_dependencies()
        self.file_create.side_effect = AppError(detail='DB rejected file')
        with self.assertRaises(AppError):
            await self.send()
        self.cleanup.assert_awaited_once_with('42/' + self.saved.disk_name)
        self.session.commit.assert_not_awaited()
        self.publish.assert_not_awaited()

    async def test_message_creation_failure_removes_new_file(self):
        self.mocked_dependencies()
        self.message_create.side_effect = AppError(detail='DB rejected message')
        with self.assertRaises(AppError):
            await self.send()
        self.cleanup.assert_awaited_once_with('42/' + self.saved.disk_name)
        self.session.commit.assert_not_awaited()
        self.publish.assert_not_awaited()

    async def test_response_construction_failure_removes_new_file(self):
        self.mocked_dependencies()
        self.build_response.side_effect = AppError(detail='Build failed')
        with self.assertRaises(AppError):
            await self.send()
        self.cleanup.assert_awaited_once_with('42/' + self.saved.disk_name)
        self.session.commit.assert_not_awaited()

    async def test_commit_failure_removes_new_file(self):
        self.mocked_dependencies()
        self.session.commit.side_effect = AppError(detail='Commit failed')
        with self.assertRaises(AppError):
            await self.send()
        self.cleanup.assert_awaited_once_with('42/' + self.saved.disk_name)
        self.session.commit.assert_awaited_once()
        self.publish.assert_not_awaited()

    async def test_successful_commit_preserves_new_file(self):
        self.mocked_dependencies()
        result = await self.send()
        self.assertIs(result, self.response)
        self.cleanup.assert_not_awaited()
        self.session.commit.assert_awaited_once()
        self.publish.assert_awaited_once()

    async def test_post_commit_publish_error_never_deletes_saved_file(self):
        self.mocked_dependencies()
        self.publish.side_effect = RuntimeError('WebSocket publish failed')
        with self.assertRaises(AppError):
            await self.send()
        self.cleanup.assert_not_awaited()
        self.session.commit.assert_awaited_once()

    async def test_text_only_failure_does_not_attempt_file_cleanup(self):
        self.mocked_dependencies()
        self.session.commit.side_effect = AppError(detail='Commit failed')
        with self.assertRaises(AppError):
            await self.send(file=False)
        self.cleanup.assert_not_awaited()

    async def test_cancellation_during_message_write_removes_new_file(self):
        self.mocked_dependencies()
        self.message_create.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.send()
        self.cleanup.assert_awaited_once_with('42/' + self.saved.disk_name)
        self.session.commit.assert_not_awaited()


class FailedUploadCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_removes_only_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / '42'
            directory.mkdir()
            new_file = directory / ('a' * 32 + '.txt')
            old_file = directory / ('b' * 32 + '.txt')
            new_file.write_bytes(b'new')
            old_file.write_bytes(b'old')
            with patch('app.utils.files.FILES_ROOT', root):
                await FileManager.cleanup_failed_upload('42/' + new_file.name)
            self.assertFalse(new_file.exists())
            self.assertEqual(old_file.read_bytes(), b'old')

    async def test_cleanup_failure_does_not_mask_original_exception(self):
        with patch(
            'app.services.files.delete_files_from_disk',
            new_callable=AsyncMock,
            side_effect=OSError('disk unavailable'),
        ):
            await FileManager.cleanup_failed_upload('42/new.txt')


if __name__ == '__main__':
    unittest.main()
