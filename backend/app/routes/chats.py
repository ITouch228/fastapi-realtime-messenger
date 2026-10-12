from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.user import UserResponse
from app.services.auth import get_current_user
from app.services.chats import (
    delete_chat_in_db,
    get_chat_by_user_ids_in_db,
    get_chat_in_db,
    get_user_chats_in_db,
)
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


@router.delete('/{chat_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat = await get_chat_in_db(session=session, chat_id=chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Чат не найден'
        )

    if current_user.id not in (chat.users or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Доступ запрещен'
        )

    await delete_chat_in_db(session=session, chat_id=chat_id)
    logger.info('Удаление чата с ID: %s', chat_id)
