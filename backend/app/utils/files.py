import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi.responses import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.config import FILES_ROOT, settings
from app.exceptions import AppError, BadRequestError, PayloadTooLargeError
from app.utils.logging import get_logger
from app.utils.validators import validate_file_name

logger = get_logger(__name__)

IMAGE_EXTENSIONS = {
    '.jpg': 'JPEG',
    '.jpeg': 'JPEG',
    '.png': 'PNG',
    '.gif': 'GIF',
    '.webp': 'WEBP',
}


@dataclass(frozen=True)
class SavedUpload:
    """Метаданные реально записанных байтов, а не клиента."""

    disk_name: str
    original_name: str
    mime_type: str
    size_bytes: int


def resolve_file_path(db_path: str) -> Path | None:
    """Возвращает путь к файлу на диске по относительному пути"""

    if not db_path:
        return None

    root = FILES_ROOT.resolve()
    file_path = (root / db_path).resolve()

    # is_relative_to вместо startswith: строковый preфикс пропускал
    # соседние каталоги-«близяты» (uploads/ vs uploads_evil/)
    if not file_path.is_relative_to(root):
        return None

    if not file_path.exists():
        return None

    return file_path


def guess_mime_type(file_path: Path) -> str | None:
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type


def render_image_response(
    file_path: Path,
    accept_header: str,
    width: int | None,
    quality: int,
) -> Response | None:
    """
    Готовит HTTP-ответ с изображением: ресайз по ширине и WEBP, если клиент
    его поддерживает. Возвращает None, если файл не изображение, GIF, или
    Pillow не смог его обработать (тогда вызывающий отдаёт файл как есть).
    """
    mime_type = guess_mime_type(file_path)
    if not (mime_type and mime_type.startswith('image/')):
        return None

    if mime_type == 'image/gif':
        return None

    try:
        with Image.open(file_path) as img:
            output_format = (
                'WEBP'
                if 'image/webp' in (accept_header or '')
                else (img.format or 'PNG')
            )
            if width:
                img.thumbnail((width, width * 2))

            output = io.BytesIO()
            img.save(output, format=output_format, quality=quality, optimize=True)

            return Response(
                output.getvalue(),
                media_type=f'image/{output_format.lower()}',
                headers={
                    'Cache-Control': 'private, max-age=31536000',
                    'Content-DPR': '1.0',
                    'Vary': 'Accept',
                },
            )
    except OSError:
        # Ошибки при чтении/записи файлов — не логируем как exceptions,
        # так как это может быть просто битый файл, а не сбой сервера
        logger.warning('Ошибка при загрузке изображения: %s', file_path)
        return None


def compress_image_sync(
    image_bytes: bytes, quality: int = settings.IMAGE_SAVE_QUALITY
) -> bytes:
    """
    Сжимает JPEG/WEBP с потерями, оптимизирует PNG, сохраняет анимацию GIF.

    Возвращает оригинальные байты, если сжатие не удалось или не уменьшило размер.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            fmt = (img.format or '').upper()
            if fmt == 'GIF':
                return image_bytes

            output = io.BytesIO()
            if fmt == 'PNG':
                # PNG остаётся без потерь, но с оптимизацией палитры/IDAT.
                img.save(output, format='PNG', optimize=True)
            # JPEG/WEBP/bmp: lossy WebP даёт лучший баланс размера и качества.
            elif img.mode not in ('RGB', 'RGBA'):
                img.convert('RGB').save(
                    output, format='WEBP', quality=quality, method=4
                )
            else:
                img.save(output, format='WEBP', quality=quality, method=4)

            compressed = output.getvalue()
            return compressed if len(compressed) < len(image_bytes) else image_bytes
    except Image.DecompressionBombError:
        raise
    except OSError:
        # Ошибки при работе с файловой системой — не логируем как exceptions
        logger.warning('Ошибка при сжатии изображения')
        return image_bytes
    except Exception:
        # Прочие ошибки Pillow — логируем, возвращаем оригинал
        logger.exception('Ошибка Pillow при сжатии изображения')
        return image_bytes


async def delete_files_from_disk(rel_paths: list[str]) -> None:
    """Удаляет файлы с диска (non-blocking). Не бросает, если файлы уже удалены."""

    def _unlink() -> None:
        root = FILES_ROOT.resolve()
        for rel in rel_paths:
            path = (root / rel).resolve()
            if path.is_relative_to(root) and path.exists():
                try:
                    path.unlink()
                except OSError:
                    logger.warning('Не удалось удалить файл: %s', rel)

    await run_in_threadpool(_unlink)


async def _prepare_image(extension: str, content: bytes) -> tuple[bytes, str]:
    """Проверить формат изображения и вернуть байты с правильным расширением."""

    def inspect() -> str | None:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
            return str(image.format) if image.format is not None else None

    try:
        actual_format = await run_in_threadpool(inspect)
        if actual_format != IMAGE_EXTENSIONS[extension]:
            raise BadRequestError(detail='Расширение не соответствует изображению')
        if actual_format != 'GIF':
            content = await run_in_threadpool(compress_image_sync, content)

        def stored_format() -> str | None:
            with Image.open(io.BytesIO(content)) as image:
                return str(image.format) if image.format is not None else None

        fmt = await run_in_threadpool(stored_format)
        suffixes = {
            'JPEG': '.jpg',
            'PNG': '.png',
            'GIF': '.gif',
            'WEBP': '.webp',
        }
        if fmt not in suffixes:
            raise BadRequestError(detail='Неподдерживаемый формат изображения')
        return content, suffixes[fmt]
    except Image.DecompressionBombError as exc:
        raise PayloadTooLargeError(detail='Файл слишком большой для обработки') from exc
    except (Image.UnidentifiedImageError, OSError) as exc:
        raise BadRequestError(detail='Некорректный файл изображения') from exc


async def _write_unique_file(chat_id: int, extension: str, content: bytes) -> str:
    """Записать байты только в новый UUID-путь; не перезаписывать существующий."""
    directory = FILES_ROOT.resolve() / str(chat_id)
    try:
        await run_in_threadpool(directory.mkdir, parents=True, exist_ok=True)
        for _ in range(3):
            disk_name = uuid4().hex + extension
            path = directory / disk_name
            created = False
            try:
                async with aiofiles.open(path, 'xb') as handle:
                    created = True
                    await handle.write(content)
                return disk_name
            except FileExistsError:
                continue
            except OSError:
                if created:
                    await run_in_threadpool(path.unlink, missing_ok=True)
                raise
        raise AppError(detail='Не удалось подобрать уникальное имя файла')
    except OSError as exc:
        logger.exception('Ошибка записи вложения в чат %s', chat_id)
        raise AppError(detail='Не удалось сохранить файл') from exc


async def save_file(chat_id: int, file_name: str, file_content: bytes) -> SavedUpload:
    """Проверить вложение и вернуть метаданные фактически записанного файла."""
    if chat_id < 0:
        raise BadRequestError(detail='Некорректный ID чата')
    validate_file_name(file_name)
    if not file_content:
        raise BadRequestError(detail='Пустое содержимое файла')
    if len(file_content) > settings.MAX_FILE_SIZE:
        raise PayloadTooLargeError(detail='Файл слишком большой')

    extension = Path(file_name).suffix.lower()
    if extension not in settings.ALLOWED_FILE_EXTENSIONS:
        raise BadRequestError(detail='Недопустимый тип файла')
    if extension in IMAGE_EXTENSIONS:
        file_content, extension = await _prepare_image(extension, file_content)

    mime_type = mimetypes.guess_type('file' + extension)[0]
    if mime_type is None:
        mime_type = 'application/octet-stream'
    disk_name = await _write_unique_file(chat_id, extension, file_content)
    return SavedUpload(
        disk_name=disk_name,
        original_name=file_name,
        mime_type=mime_type,
        size_bytes=len(file_content),
    )
