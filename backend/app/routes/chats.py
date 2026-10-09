from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import ChatDAO, MessageDAO
from app.database import get_session
from app.schemas.chat import ChatInDb
from app.schemas.user import UserInDB
from app.services.auth import get_current_user
from app.services.messages import build_message_out
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/chats')


@router.get('/get_user_chats')
async def get_user_chats(
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    logger.info(f'Загрузка чатов пользователя с id: {current_user.id}')
    chats = await ChatDAO.get_all_user_chats(session=session, user_id=current_user.id)

    result = []
    if chats is not None:
        for chat in chats:
            # Получаем последнее сообщение для этого чата
            messages = await MessageDAO.find_all_or_none(
                session=session, chat_id=chat.id, order_by='time desc', limit=1
            )

            last_message = None
            if messages:
                last_message = {
                    'text': messages[0].message_text,
                    'time': messages[0].time,
                }

            result.append(
                {
                    'id': chat.id,
                    'users': chat.users,
                    'lastMessage': last_message['text'] if last_message else None,
                    'lastMessageTime': last_message['time'] if last_message else None,
                }
            )

    return result


@router.get('/get_chat_by_user_ids')
async def get_chat_by_user_ids(
    target_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    chats = await ChatDAO.search_chats(
        session=session, current_user_id=current_user.id, user_id=target_id
    )

    if chats:
        return ChatInDb.model_validate(chats[0]).id
    return None


@router.get('/get_chat_messages')
async def get_chat_messages(
    chat_id: str,
    current_user: UserInDB = Depends(get_current_user),
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

    messages_in_db = await MessageDAO.find_all_or_none(
        session=session, chat_id=chat_id_int
    )

    return [
        await build_message_out(session=session, message=m)
        for m in (messages_in_db or [])
    ]


@router.delete('/delete_chat')
async def delete_chat(
    chat_id: int,
    current_user: UserInDB = Depends(get_current_user),
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
