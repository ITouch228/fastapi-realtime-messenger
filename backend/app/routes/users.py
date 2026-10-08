from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import UserDAO
from app.database import get_session
from app.schemas.user import UserInDB
from app.services.auth import get_current_user_from_cookie, require_user
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/users')


@router.get('/get_user_info')
async def get_user_info(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
):
    require_user(current_user)

    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    return {
        'id': user.id,
        'username': user.username,
        'avatar': user.username[0].upper(),  # Первая буква имени как аватар
    }


@router.get('/search_users')
async def search_users(
    query: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
):
    require_user(current_user)

    users = await UserDAO.seach_users_by_query(session=session, query=query)

    users = [UserInDB.model_validate(user) for user in users] if users else None

    return (
        [{'user_id': user.id, 'username': user.username} for user in users]
        if users
        else []
    )
