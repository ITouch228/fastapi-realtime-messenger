from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import UserResponse
from app.services import AuthManager, UserManager

router = APIRouter(prefix='/users')


@router.get('/me', response_model=UserResponse)
async def read_me(current_user: UserResponse = Depends(AuthManager.get_current_user)):
    return current_user


@router.get('/search', response_model=list[UserResponse])
async def search_users(
    query: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserResponse = Depends(AuthManager.get_current_user),
):
    return await UserManager.search(session=session, query=query)


@router.get('/{user_id}', response_model=UserResponse)
async def get_user_info(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserResponse = Depends(AuthManager.get_current_user),
):
    return await UserManager.get(session=session, user_id=user_id)
