from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import UserDAO
from app.models.user import User
from app.schemas.user import UserCreate, UserInDB
from app.services.auth import get_password_hash, verify_password
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


async def add_user_to_db(user_data: UserCreate, session: AsyncSession) -> int:
    try:
        user_dict = user_data.model_dump()
        user_dict['hashed_password'] = get_password_hash(user_dict.pop('password'))

        new_user = await UserDAO.add(session, **user_dict)
        logger.info(f'Successfully added user: {user_data.username}')
        return new_user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error adding user: {str(e)}')
        raise HTTPException(status_code=400, detail='User registration failed')


async def search_users_by_username_query_db(
    query: str, session: AsyncSession
) -> list[User] | None:
    try:
        logger.info(f'search_users_by_username_query_db: {query}')
        users = await UserDAO.seach_users_by_query(session=session, query=query)
        return users
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error finding user: {str(e)}')
        raise HTTPException(status_code=400, detail='User search failed')


async def validate_user_in_db(user_data: dict, session: AsyncSession) -> bool:
    logger.info(f'validate_user_in_db: {user_data}')
    user = await UserDAO.find_one_or_none(session=session, **user_data)
    if user:
        user_in_db = UserInDB.model_validate(user)
        hashed_password = user_in_db.hashed_password

        return hashed_password is not None and verify_password(
            user_data.get('password'), hashed_password
        )
    return False
