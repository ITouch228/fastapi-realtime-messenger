from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.database import get_session
from app.exceptions import UnauthorizedError
from app.schemas import UserResponse
from app.services import AuthManager, SessionManager, get_session_manager
from app.utils import get_access_token_from_cookie

templates: Jinja2Templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


async def get_current_user_from_cookie(
    session: AsyncSession = Depends(get_session),
    access: str | None = Depends(get_access_token_from_cookie),
    session_manager: SessionManager = Depends(get_session_manager),
) -> UserResponse | None:
    """Опциональная зависимость: вернёт юзера или None (не бросает 401)."""
    return await AuthManager.get_user_by_token(
        session=session,
        access_token=access,
        session_manager=session_manager,
    )


async def get_current_user(
    current_user: UserResponse | None = Depends(get_current_user_from_cookie),
) -> UserResponse:
    """Строгая зависимость: требует авторизации, иначе 401."""
    if current_user is None:
        raise UnauthorizedError('Не аутентифицирован')
    return current_user
