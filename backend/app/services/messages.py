import mimetypes
import os
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import FILES_ROOT
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
        file_in_db = await FileDAO.find_one_or_none(
            session=session, id=message.message_file_id
        )
        if not file_in_db:
            raise HTTPException(status_code=404, detail='File not found')

        file_db = FileInDb.model_validate(file_in_db)
        file_path = resolve_file_path(file_db.file_path)

        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail='File not found')

        abs_file_path = os.path.abspath(file_path)
        expected_prefix = str(FILES_ROOT.resolve())
        if not abs_file_path.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail='Invalid file path')

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or 'application/octet-stream'
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail='File type not allowed')

        file_meta = build_file_meta(
            file_id=message.message_file_id, file_path=file_path
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
