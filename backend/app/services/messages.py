import mimetypes
import os
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FILES_ROOT
from app.dao.dao import FileDAO
from app.schemas.file import FileInDb, FileMeta
from app.schemas.message import MessageOut
from app.utils.file_path import resolve_file_path
from app.utils.logging_config import get_logger

ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'text/plain',
    'text/csv',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


logger = get_logger(__name__)


def build_file_meta(file_id: int, file_path: str | os.PathLike[str]) -> FileMeta:
    path_str = os.fspath(file_path)
    mime_type, _ = mimetypes.guess_type(path_str)
    mime_type = mime_type or 'application/octet-stream'
    kind: Literal['image', 'file'] = (
        'image' if mime_type.startswith('image/') else 'file'
    )

    return FileMeta(
        id=file_id,
        kind=kind,
        url=f'/api/files/download_file/{file_id}',
        mime_type=mime_type,
        filename=os.path.basename(path_str),
        size=os.path.getsize(path_str) if os.path.exists(path_str) else None,
    )


async def build_message_out(message, session: AsyncSession) -> MessageOut:
    file_meta = None

    if message.message_file_id:
        file_meta = await _resolve_file_meta(
            session=session,
            message_file_id=message.message_file_id,
            message_id=message.id,
        )

    return MessageOut(
        id=message.id,
        chat_id=message.chat_id,
        user_from_id=message.user_from_id,
        message_text=message.message_text,
        time=message.time,
        message_file_id=message.message_file_id,
        file=file_meta,
    )


async def _resolve_file_meta(
    session: AsyncSession,
    message_file_id: int,
    message_id: int,
) -> FileMeta | None:
    """Resolve file metadata; return None on any failure without breaking the message."""
    try:
        file_in_db = await FileDAO.find_one_or_none(session=session, id=message_file_id)
        if not file_in_db:
            logger.warning(
                f'File {message_file_id} not found in DB for message {message_id}'
            )
            return None

        file_db = FileInDb.model_validate(file_in_db)
        file_path = resolve_file_path(file_db.file_path)

        if not file_path or not os.path.exists(file_path):
            logger.warning(
                f'File {message_file_id} missing on disk for message {message_id}'
            )
            return None

        abs_file_path = os.path.abspath(file_path)
        expected_prefix = str(FILES_ROOT.resolve())
        if not abs_file_path.startswith(expected_prefix):
            logger.warning(
                f'File {message_file_id} path traversal detected for message {message_id}'
            )
            return None

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or 'application/octet-stream'
        if mime_type not in ALLOWED_MIME_TYPES:
            logger.warning(
                f'File {message_file_id} has disallowed MIME type {mime_type} '
                f'for message {message_id}'
            )
            return None

        return build_file_meta(file_id=message_file_id, file_path=file_path)

    except HTTPException:
        logger.warning(f'File {message_file_id} access error for message {message_id}')
        return None
