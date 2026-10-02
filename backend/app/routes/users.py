import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from app.dao.dao import UserDAO
from app.database import get_session
from app.schemas.user import UserInDB

logger = logging.getLogger(__name__)
templates: Jinja2Templates = Jinja2Templates(directory='app/templates')


router = APIRouter(prefix='/users')


@router.get('/get_user_info')
async def get_user_info(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    return {
        'id': user.id,
        'username': user.username,
        'avatar': user.username[0].upper(),  # Первая буква имени как аватар
    }


@router.get('/search_users')
async def search_users(query: str, session: AsyncSession = Depends(get_session)):
    users = await UserDAO.seach_users_by_query(session=session, query=query)

    users = [UserInDB.model_validate(user) for user in users] if users else None

    return (
        [{'user_id': user.id, 'username': user.username} for user in users]
        if users
        else []
    )
