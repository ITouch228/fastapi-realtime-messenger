import io
import mimetypes
import os
from pathlib import Path

import aiofiles
from fastapi.responses import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.config import FILES_ROOT, settings
from app.exceptions import AppError, BadRequestError, PayloadTooLargeError
from app.utils.logging import get_logger
from app.utils.validators import validate_file_name

logger = get_logger(__name__)


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


async def save_file(chat_id: int, file_name: str, file_content: bytes) -> None:
    """Проверить и сохранить файл в uploads/{chat_id}/. Изображения сжимает в WebP."""
    if chat_id < 0:
        raise BadRequestError(detail='Некорректный ID чата')

    # Отклоняет разделители путей (в т.ч. обратную косую черту Windows),
    # управляющие символы, '.'/'..'.
    validate_file_name(file_name)

    if len(file_content) == 0:
        raise BadRequestError(detail='Пустое содержимое файла')

    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in settings.ALLOWED_FILE_EXTENSIONS:
        raise BadRequestError(detail='Недопустимый тип файла')

    if len(file_content) > settings.MAX_FILE_SIZE:
        raise PayloadTooLargeError(detail='Файл слишком большой')

    rel_path = f'{chat_id}/{file_name}'

    abs_path = (FILES_ROOT / rel_path).resolve()

    if not abs_path.is_relative_to(FILES_ROOT.resolve()):
        raise BadRequestError(detail='Некорректный путь файла')

    try:
        await run_in_threadpool(os.makedirs, abs_path.parent, exist_ok=True)

        if file_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            try:
                img = await run_in_threadpool(Image.open, io.BytesIO(file_content))
                await run_in_threadpool(img.verify)

                if file_ext != '.gif':
                    file_content = await run_in_threadpool(
                        compress_image_sync, file_content
                    )
            except Image.DecompressionBombError:
                raise PayloadTooLargeError(detail='Файл слишком большой для обработки')
            except Image.UnidentifiedImageError:
                raise BadRequestError(detail='Некорректный файл изображения')
            except OSError:
                raise BadRequestError(detail='Некорректный файл изображения')

        async with aiofiles.open(abs_path, 'wb') as f:
            await f.write(file_content)
    except AppError:
        raise
    except OSError as exc:
        logger.exception('Ошибка сохранения файла: %s', file_name)
        raise AppError(detail='Не удалось сохранить файл') from exc
