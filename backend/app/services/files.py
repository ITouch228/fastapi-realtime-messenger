import io
import os

import aiofiles
from fastapi import Depends, HTTPException
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import FILES_ROOT
from app.dao.dao import FileDAO
from app.database import get_session
from app.schemas.file import FileInDb
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


async def save_file(chat_id: int, file_name: str, file_content: bytes) -> bool:
    if chat_id < 0:
        raise HTTPException(status_code=400, detail='Invalid chat ID')

    if '..' in file_name or file_name.startswith('/'):
        raise HTTPException(status_code=400, detail='Invalid file name')

    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail='Empty file content')

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
        raise HTTPException(status_code=400, detail='File type not allowed')

    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='File too large')

    rel_path = f'{chat_id}/{file_name}'

    abs_path = (FILES_ROOT / rel_path).resolve()

    if not str(abs_path).startswith(str(FILES_ROOT.resolve())):
        raise HTTPException(status_code=400, detail='Invalid file path')

    try:
        os.makedirs(abs_path.parent, exist_ok=True)

        if file_ext.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            try:
                img = Image.open(io.BytesIO(file_content))
                img.verify()
                file_content = await compress_image(file_content)
            except Exception:
                raise HTTPException(status_code=400, detail='Invalid image file')

        async with aiofiles.open(abs_path, 'wb') as f:
            await f.write(file_content)

        return True
    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        logger.error(f'File save error: {str(e)}')
        return False


async def add_file_to_db(
    chat_id: int, file_name: str, session: AsyncSession = Depends(get_session)
):
    logger.info(f'add_file_to_db: {chat_id}, {file_name}')

    if '..' in file_name or file_name.startswith('/'):
        raise HTTPException(status_code=400, detail='Invalid file name')

    if chat_id < 0:
        raise HTTPException(status_code=400, detail='Invalid chat ID')

    rel_path = f'{chat_id}/{file_name}'

    abs_path = (FILES_ROOT / rel_path).resolve()

    if os.path.exists(abs_path):
        file = await FileDAO.find_one_or_none(session=session, file_path=rel_path)
        if file:
            file_id = FileInDb.model_validate(file).id
            return file_id

    try:
        new_file = await FileDAO.add(session=session, file_path=rel_path)
        logger.info(f'Successfully added file: {chat_id}, {file_name}')
        return new_file.id
    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        logger.error(f'Error adding file: {str(e)}')
        raise HTTPException(status_code=400, detail='File registration failed')


async def get_file_path_in_db(
    session: AsyncSession = Depends(get_session), **filter_by
):
    try:
        logger.info(f'get_file_path_in_db: {filter_by}')
        file = await FileDAO.find_one_or_none(session=session, **filter_by)
        if file:
            file_path = FileInDb.model_validate(file).file_path
            return file_path
        return None
    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        logger.error(f'Error finding file: {str(e)}')
        raise HTTPException(status_code=400, detail='File search failed')


async def compress_image(image_bytes: bytes, quality: int = 85) -> bytes:
    """Сжимает JPEG/WEBP с потерями, оптимизирует PNG, сохраняет анимацию GIF.

    Возвращает оригинальные байты, если сжатие не удалось или не уменьшило размер.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        fmt = (img.format or '').upper()

        # GIF: Image.open читает только первый кадр, пересжатие убило бы анимацию.
        if fmt == 'GIF':
            return image_bytes

        output_buffer = io.BytesIO()
        if fmt == 'PNG':
            # PNG остаётся без потерь, но с оптимизацией палитры/IDAT.
            img.save(output_buffer, format='PNG', optimize=True)
        else:
            # JPEG/WEBP/bmp: lossy WebP даёт лучший баланс размера и качества.
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            img.save(output_buffer, format='WEBP', quality=quality, method=4)

        compressed = output_buffer.getvalue()
        # Никогда не увеличиваем файл.
        return compressed if len(compressed) < len(image_bytes) else image_bytes
    except Exception as e:
        logger.error(f'Image compression error: {str(e)}')
        return image_bytes  # Возвращаем оригинал, если ошибка
