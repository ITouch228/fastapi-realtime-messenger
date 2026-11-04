"""Проверки восстановления outbox и идемпотентного удаления файлов."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.file_cleanup import (
    _unlink_outbox_file,
    process_file_cleanup_batch,
)


class CleanupOutboxTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch('app.services.file_cleanup.FILES_ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def fake_session(self, paths, referenced=None):
        session = AsyncMock()
        tasks = [SimpleNamespace(id=i, file_path=p) for i, p in enumerate(paths)]
        session.scalars.return_value = SimpleNamespace(all=lambda: tasks)
        session.scalar.return_value = referenced
        maker = MagicMock()
        maker.return_value.__aenter__ = AsyncMock(return_value=session)
        maker.return_value.__aexit__ = AsyncMock(return_value=None)
        return session, maker

    async def test_unlink_is_idempotent(self):
        directory = self.root / '42'
        directory.mkdir()
        target = directory / 'file.txt'
        target.write_bytes(b'payload')
        _unlink_outbox_file('42/file.txt')
        _unlink_outbox_file('42/file.txt')
        self.assertFalse(target.exists())

    async def test_rejects_path_escape(self):
        with self.assertRaises(ValueError):
            _unlink_outbox_file('../../outside.txt')

    async def test_completed_job_deleted_after_file_unlink(self):
        (self.root / '42').mkdir()
        target = self.root / '42' / 'file.txt'
        target.write_bytes(b'payload')
        session, maker = self.fake_session(['42/file.txt'])
        with patch('app.services.file_cleanup.async_session_maker', maker):
            self.assertEqual(await process_file_cleanup_batch(), 1)
        self.assertFalse(target.exists())
        session.delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_failed_unlink_keeps_job_for_retry(self):
        session, maker = self.fake_session(['42/file.txt'])
        with (
            patch('app.services.file_cleanup.async_session_maker', maker),
            patch(
                'app.services.file_cleanup.run_in_threadpool',
                side_effect=OSError('disk unavailable'),
            ),
        ):
            self.assertEqual(await process_file_cleanup_batch(), 0)
        session.delete.assert_not_awaited()
        session.commit.assert_awaited_once()

    async def test_referenced_file_is_never_removed(self):
        (self.root / '42').mkdir()
        target = self.root / '42' / 'file.txt'
        target.write_bytes(b'preserve')
        session, maker = self.fake_session(['42/file.txt'], referenced=15)
        with patch('app.services.file_cleanup.async_session_maker', maker):
            self.assertEqual(await process_file_cleanup_batch(), 0)
        self.assertEqual(target.read_bytes(), b'preserve')
        session.delete.assert_awaited_once()

    async def test_commit_failure_does_not_lose_retry_task(self):
        session, maker = self.fake_session(['42/missing.txt'])
        session.commit.side_effect = RuntimeError('DB disconnected')
        with (
            patch('app.services.file_cleanup.async_session_maker', maker),
            self.assertRaisesRegex(RuntimeError, 'DB disconnected'),
        ):
            await process_file_cleanup_batch()
        session.delete.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
