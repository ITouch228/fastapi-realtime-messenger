from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import ChatDAO, MessageDAO
from app.database import get_session
from app.schemas.user import UserResponse
from app.services.auth import get_current_user
from app.services.chats import get_chat_by_user_ids_in_db, get_user_chats_in_db
from app.services.messages import build_message_out
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/chats')


@router.get('')
async def get_user_chats(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    logger.info('Загрузка чатов пользователя с ID: %s', current_user.id)

    return await get_user_chats_in_db(current_user.id, session=session)


@router.get('/direct/{target_id}')
async def get_chat_by_user_ids(
    target_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    logger.info('Загрузка чата пользователей с ID: %s %s', current_user.id, target_id)

    return await get_chat_by_user_ids_in_db(
        user_a_id=current_user.id,
        user_b_id=target_id,
        session=session,
    )


@router.get('/{chat_id}/messages')
async def get_chat_messages(
    chat_id: str,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if chat_id.startswith('temp-'):
        return []
    chat_id_int = int(chat_id)

    chat = await ChatDAO.find_one_or_none(session=session, id=chat_id_int)
    if not chat:
        raise HTTPException(status_code=404, detail='Chat not found')

    if current_user.id not in (chat.users or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Forbidden')

    messages_in_db = await MessageDAO.find_all(session=session, chat_id=chat_id_int)

    return [
        await build_message_out(session=session, message=m)
        for m in (messages_in_db or [])
    ]


@router.delete('/{chat_id}', status_code=204)
async def delete_chat(
    chat_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat = await ChatDAO.find_one_or_none(session=session, id=chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail='Chat not found')

    if current_user.id not in (chat.users or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Forbidden')

    await ChatDAO.delete_chat(session=session, chat_id=chat_id)
    logger.info(f'Deleted chat with id: {chat_id}')

    return {'status': 'success'}
