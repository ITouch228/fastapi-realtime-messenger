"""Регрессионные тесты хранения вложений и соответствия метаданных байтам."""

import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.exceptions import BadRequestError, PayloadTooLargeError
from app.utils.files import save_file


class AttachmentStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        root_patch = patch('app.utils.files.FILES_ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    async def test_same_original_name_creates_two_independent_files(self):
        first = await save_file(42, 'report.txt', b'first')
        second = await save_file(42, 'report.txt', b'second')
        self.assertNotEqual(first.disk_name, second.disk_name)
        self.assertEqual((self.root / '42' / first.disk_name).read_bytes(), b'first')
        self.assertEqual((self.root / '42' / second.disk_name).read_bytes(), b'second')
        self.assertEqual(first.original_name, 'report.txt')
        self.assertEqual(first.mime_type, 'text/plain')
        self.assertEqual(second.size_bytes, 6)

    async def test_existing_uuid_filename_is_not_overwritten(self):
        original = self.root / '42'
        original.mkdir()
        existing = original / ('a' * 32 + '.txt')
        existing.write_bytes(b'keep')
        with patch('app.utils.files.uuid4') as new_id:
            new_id.side_effect = [
                SimpleNamespace(hex='a' * 32),
                SimpleNamespace(hex='b' * 32),
            ]
            result = await save_file(42, 'same.txt', b'new')
        self.assertEqual(existing.read_bytes(), b'keep')
        self.assertEqual(result.disk_name, 'b' * 32 + '.txt')
        self.assertEqual((original / result.disk_name).read_bytes(), b'new')

    async def test_very_long_client_name_is_not_part_of_disk_path(self):
        name = 'x' * 251 + '.txt'
        result = await save_file(42, name, b'payload')
        self.assertEqual(result.original_name, name)
        self.assertEqual(len(result.disk_name), 36)
        self.assertEqual((self.root / '42' / result.disk_name).read_bytes(), b'payload')

    async def test_image_metadata_matches_actual_stored_format_and_size(self):
        source = io.BytesIO()
        Image.new('RGB', (100, 100), (50, 100, 150)).save(source, format='JPEG')
        result = await save_file(42, 'photo.jpg', source.getvalue())
        stored = self.root / '42' / result.disk_name
        with Image.open(stored) as image:
            self.assertEqual(result.mime_type, Image.MIME[image.format])
        self.assertEqual(result.size_bytes, stored.stat().st_size)
        self.assertEqual(result.original_name, 'photo.jpg')
        self.assertEqual(stored.suffix, '.' + ('jpg' if result.mime_type == 'image/jpeg' else 'webp'))

    async def test_mismatched_image_extension_is_rejected(self):
        source = io.BytesIO()
        Image.new('RGB', (2, 2)).save(source, format='PNG')
        with self.assertRaises(BadRequestError):
            await save_file(42, 'fake.jpg', source.getvalue())
        self.assertFalse((self.root / '42').exists())

    async def test_path_traversal_and_oversized_file_rejected(self):
        with self.assertRaises(BadRequestError):
            await save_file(42, '../bad.txt', b'data')
        with self.assertRaises(PayloadTooLargeError):
            await save_file(42, 'big.txt', b'a' * (10 * 1024 * 1024 + 1))


if __name__ == '__main__':
    unittest.main()
