import os

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FILES_ROOT
from app.dao.dao import ChatDAO, FileDAO, MessageDAO
from app.schemas.file import FileInDb
from app.schemas.user import UserResponse
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


async def ensure_can_access_file(
    session: AsyncSession,
    file_id: int,
    current_user: UserResponse,
) -> None:
    chat_ids = await MessageDAO.list_chat_ids_by_file(session=session, file_id=file_id)
    if not chat_ids:
        raise HTTPException(status_code=404, detail='File not found')

    user_chats = await ChatDAO.find_by_ids_with_user(
        session=session, chat_ids=chat_ids, user_id=current_user.id
    )
    if not user_chats:
        raise HTTPException(status_code=404, detail='File not found')


async def add_file_to_db(
    session: AsyncSession,
    chat_id: int,
    file_name: str,
    owner_id: int,
    original_name: str,
    mime_types: str,
    size_bytes: int,
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
        new_file = await FileDAO.add(
            session=session,
            file_path=rel_path,
            owner_id=owner_id,
            original_name=original_name,
            mime_type=mime_types,
            size_bytes=size_bytes,
        )
        logger.info(f'Successfully added file: {chat_id}, {file_name}')
        return new_file.id
    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        logger.error(f'Error adding file: {str(e)}')
        raise HTTPException(status_code=400, detail='File registration failed')


async def get_file_path_in_db(session: AsyncSession, **filter_by):
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
