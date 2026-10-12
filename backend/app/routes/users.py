from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import UserDAO
from app.database import get_session
from app.schemas.user import UserResponse
from app.services.auth import get_current_user
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/users')


@router.get('/me', response_model=UserResponse)
async def read_me(current_user: UserResponse = Depends(get_current_user)):
    return current_user


@router.get('/search', response_model=list[UserResponse])
async def search_users(
    query: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserResponse = Depends(get_current_user),
):
    users = await UserDAO.search_by_username(session=session, query=query)

    return [UserResponse.model_validate(user) for user in users] if users else []


@router.get('/{user_id}', response_model=UserResponse)
async def get_user_info(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserResponse = Depends(get_current_user),
):
    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    return UserResponse.model_validate(user)
