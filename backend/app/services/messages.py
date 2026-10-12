from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import FileDAO
from app.schemas.file import FileInDb, FileMeta
from app.schemas.message import MessageResponse
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


async def build_message_out(message, session: AsyncSession) -> MessageResponse:
    """Возвращает сообщение в формате для ответа."""
    file_meta = None

    if message.message_file_id:
        file_meta = await _resolve_file_meta(
            session=session,
            message_file_id=message.message_file_id,
            message_id=message.id,
        )

    return MessageResponse(
        id=message.id,
        chat_id=message.chat_id,
        sender_id=message.sender_id,
        message_text=message.message_text,
        sent_at=message.sent_at,
        message_file_id=message.message_file_id,
        file=file_meta,
        is_deleted=message.is_deleted,
    )


async def _resolve_file_meta(
    session: AsyncSession,
    message_file_id: int,
    message_id: int,
) -> FileMeta | None:
    """Достаёт файл из БД и собирает метаданные."""
    try:
        file_in_db = await FileDAO.find_one_or_none(session=session, id=message_file_id)
        if not file_in_db:
            logger.warning(
                'Файл %s не найден в БД для сообщения %s', message_file_id, message_id
            )
            return None

        file_db = FileInDb.model_validate(file_in_db)
        mime_type = file_db.mime_type
        kind: Literal['image', 'file'] = (
            'image' if mime_type.startswith('image/') else 'file'
        )

        return FileMeta(
            id=file_db.id,
            kind=kind,
            url=f'/api/files/{file_db.id}',
            mime_type=mime_type,
            filename=file_db.original_name,
            size=file_db.size_bytes,
        )

    except HTTPException:
        logger.warning(
            'Ошибка доступа к файлу %s для сообщения %s', message_file_id, message_id
        )
        return None
