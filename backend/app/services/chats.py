from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import ChatDAO, MessageDAO
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


async def add_user_chat_in_db(id1: int, id2: int, session: AsyncSession):
    logger.info(f'add_user_chat_in_db: {id1}, {id2}')
    try:
        new_chat = await ChatDAO.add(
            session=session, users=[min(id1, id2), max(id1, id2)]
        )
        logger.info(f'Successfully added chat: {min(id1, id2)}, {max(id1, id2)}')
        return new_chat.id
    except Exception as e:
        logger.error(f'Error adding chat: {str(e)}')
        raise HTTPException(status_code=400, detail='Chat registration failed')


async def get_user_chat_in_db(chat_id: int, session: AsyncSession):
    try:
        logger.info(f'Searching user with params: {chat_id}')
        chat = await ChatDAO.find_one_or_none(session, id=chat_id)
        return chat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error finding chat: {str(e)}')
        raise HTTPException(status_code=400, detail='Chat search failed')


async def get_user_chats_in_db(user_id: int, session: AsyncSession):
    logger.info(f'get_user_chats_in_db: {user_id}')
    chats = await ChatDAO.find_user_chats(session=session, user_id=user_id)

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


async def get_chat_by_user_ids_in_db(
    user_id: int, target_id: int, session: AsyncSession
):
    logger.info(f'get_chat_by_user_ids_in_db: {user_id}, {target_id}')
    chat = await ChatDAO.find_chat_by_user_ids(
        session=session, user1_id=user_id, user2_id=target_id
    )

    return chat


async def delete_chat_in_db(chat_id: int, session: AsyncSession):
    logger.info(f'delete_chat_in_db: {chat_id}')
    is_deleted = await ChatDAO.delete_chat(session=session, chat_id=chat_id)
    if is_deleted:
        logger.info(f'Succesfuly deleted: {chat_id}')

    return is_deleted
