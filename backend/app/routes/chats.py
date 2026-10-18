from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import ChatResponse, UserResponse
from app.services import AuthManager, ChatManager
from app.utils import require_csrf

router = APIRouter(prefix='/chats')


@router.get('', response_model=list[ChatResponse])
async def get_user_chats(
    current_user: UserResponse = Depends(AuthManager.get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatManager.get_by_user(user_id=current_user.id, session=session)


@router.get('/direct/{target_id}', response_model=ChatResponse | None)
async def get_chat_by_user_ids(
    target_id: int,
    current_user: UserResponse = Depends(AuthManager.get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChatManager.get_by_users(
        user_a_id=current_user.id,
        user_b_id=target_id,
        session=session,
    )


@router.delete('/{chat_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: int,
    current_user: UserResponse = Depends(AuthManager.get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
):
    await ChatManager.delete(chat_id=chat_id, user_id=current_user.id, session=session)
    await session.commit()
