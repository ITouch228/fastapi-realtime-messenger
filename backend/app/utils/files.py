import io
import mimetypes
import os
from pathlib import Path

import aiofiles
from fastapi.responses import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.config import FILES_ROOT
from app.exceptions import AppError, BadRequestError, PayloadTooLargeError
from app.utils.logging import get_logger

logger = get_logger(__name__)


def resolve_file_path(db_path: str) -> Path | None:
    """Возвращает путь к файлу на диске по относительному пути"""

    if not db_path:
        return None

    file_path = (FILES_ROOT / db_path).resolve()

    if not str(file_path).startswith(str(FILES_ROOT)):
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
    except Exception:
        logger.exception('Ошибка при загрузке изображения')
        return None


def compress_image_sync(image_bytes: bytes, quality: int = 85) -> bytes:
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
            else:
                # JPEG/WEBP/bmp: lossy WebP даёт лучший баланс размера и качества.
                if img.mode not in ('RGB', 'RGBA'):
                    img.convert('RGB').save(
                        output, format='WEBP', quality=quality, method=4
                    )
                img.save(output, format='WEBP', quality=quality, method=4)

            compressed = output.getvalue()
            return compressed if len(compressed) < len(image_bytes) else image_bytes
    except Image.DecompressionBombError:
        raise
    except Exception:
        logger.exception('Ошибка сжатия изображения')
        return image_bytes


async def save_file(chat_id: int, file_name: str, file_content: bytes) -> bool:
    if chat_id < 0:
        raise BadRequestError(detail='Некорректный ID чата')

    if '..' in file_name or file_name.startswith('/'):
        raise BadRequestError(detail='Некорректное имя файла')

    if len(file_content) == 0:
        raise BadRequestError(detail='Пустое содержимое файла')

    allowed_extensions = [
        '.jpg',
        '.jpeg',
        '.png',
        '.gif',
        '.webp',
        '.txt',
        '.pdf',
        '.doc',
        '.docx',
        '.xls',
        '.xlsx',
        '.csv',
    ]
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in allowed_extensions:
        raise BadRequestError(detail='Недопустимый тип файла')

    if len(file_content) > 10 * 1024 * 1024:
        raise PayloadTooLargeError(detail='Файл слишком большой')

    rel_path = f'{chat_id}/{file_name}'

    abs_path = (FILES_ROOT / rel_path).resolve()

    if not str(abs_path).startswith(str(FILES_ROOT.resolve())):
        raise BadRequestError(detail='Некорректный путь файла')

    try:
        await run_in_threadpool(os.makedirs, abs_path.parent, exist_ok=True)

        if file_ext.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
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

        return True
    except AppError:
        raise
    except Exception:
        logger.exception('Ошибка сохранения файла: %s', file_name)
        return False
