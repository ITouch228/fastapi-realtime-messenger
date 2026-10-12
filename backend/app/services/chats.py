from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import ChatDAO, MessageDAO
from app.schemas.chat import ChatInDb
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


async def get_chat_in_db(chat_id: int, session: AsyncSession):
    try:
        chat = await ChatDAO.find_one_or_none(session, id=chat_id)
        return chat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error finding chat: {str(e)}')
        raise HTTPException(status_code=400, detail='Chat search failed')


async def get_user_chats_in_db(user_id: int, session: AsyncSession):
    chats = await ChatDAO.get_user_chats(session=session, user_id=user_id)

    result = []
    if chats is not None:
        for chat in chats:
            # Получаем последнее сообщение для этого чата
            messages = await MessageDAO.list_messages(
                session=session,
                chat_id=chat.id,
                order_by='sent_at',
                descending=True,
                limit=1,
            )

            last_message = None
            if messages:
                last_message = {
                    'text': messages[0].message_text,
                    'sent_at': messages[0].sent_at,
                }

            result.append(
                {
                    'id': chat.id,
                    'users': chat.users,
                    'lastMessage': last_message['text'] if last_message else None,
                    'lastMessageSentAt': last_message['sent_at']
                    if last_message
                    else None,
                }
            )

    return result


async def get_chat_by_user_ids_in_db(
    user_a_id: int, user_b_id: int, session: AsyncSession
):
    chat = await ChatDAO.find_between_users(
        session=session, user_a_id=user_a_id, user_b_id=user_b_id
    )

    if chat:
        return ChatInDb.model_validate(chat).id
    return None


async def delete_chat_in_db(chat_id: int, session: AsyncSession):
    logger.info(f'delete_chat_in_db: {chat_id}')
    is_deleted = await ChatDAO.delete_chat(session=session, chat_id=chat_id)
    if is_deleted:
        logger.info(f'Succesfuly deleted: {chat_id}')

    return is_deleted
