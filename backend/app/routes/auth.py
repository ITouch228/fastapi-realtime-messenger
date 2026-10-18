from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.database import get_session
from app.schemas import UserCreate, UserLogin
from app.services import (
    AuthManager,
    SessionManager,
    get_session_manager,
    rate_limiter,
)
from app.utils import (
    delete_tokens_from_response_cookie,
    generate_csrf_token,
    set_tokens_to_response_cookie,
)
from app.utils.csrf import require_csrf

router = APIRouter(prefix='/auth')


def _auth_response(access_token: str, refresh_token: str) -> JSONResponse:
    """Единый ответ аутентификации: JSON + access/refresh/CSRF куки."""
    response = JSONResponse(content={'status': 'ok'})
    set_tokens_to_response_cookie(
        response,
        access_token,
        refresh_token,
        csrf_token=generate_csrf_token(),
    )
    return response


@router.post('/register', status_code=status.HTTP_201_CREATED)
@rate_limiter.limit('10/hour')
async def register(
    request: Request,
    user_data: UserCreate,
    session: AsyncSession = Depends(get_session),
):
    await AuthManager.create_user(session=session, user_data=user_data)
    await session.commit()
    return {'status': 'ok'}


@router.post('/login', status_code=status.HTTP_200_OK)
@rate_limiter.limit('5/minute')
async def login(
    request: Request,
    user_data: UserLogin,
    session: AsyncSession = Depends(get_session),
    session_manager: SessionManager = Depends(get_session_manager),
):
    authenticated_user = await AuthManager.authenticate_user(
        session=session, user_data=user_data
    )

    access_token, refresh_token = await AuthManager.create_session(
        session_manager=session_manager, user_id=authenticated_user.id
    )

    return _auth_response(access_token, refresh_token)


@router.post('/logout')
async def logout(
    request: Request,
    access: str = Cookie(default=None, alias='access'),
    session_manager: SessionManager = Depends(get_session_manager),
    _: None = Depends(require_csrf),
):
    await AuthManager.revoke_session(
        session_manager=session_manager, access_token=access
    )

    response = JSONResponse(content={'status': 'ok'})
    delete_tokens_from_response_cookie(response)
    return response


@router.post('/refresh')
async def refresh_token(
    request: Request,
    refresh: str = Cookie(default=None, alias='refresh'),
    session: AsyncSession = Depends(get_session),
    session_manager: SessionManager = Depends(get_session_manager),
    _: None = Depends(require_csrf),
):
    access_token, refresh_token = await AuthManager.rotate_session(
        session=session, session_manager=session_manager, refresh_token=refresh
    )

    return _auth_response(access_token, refresh_token)
