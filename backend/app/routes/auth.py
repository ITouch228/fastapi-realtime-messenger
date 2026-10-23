from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.schemas import UserLogin, UserRegister
from app.services import (
    AuthManager,
    SessionManager,
    get_session_manager,
    rate_limiter,
)
from app.utils import (
    delete_tokens_from_response_cookie,
    generate_csrf_token,
    get_access_token_from_cookie,
    get_refresh_token_from_cookie,
    require_csrf,
    set_tokens_to_response_cookie,
)

router = APIRouter(prefix='/auth')


@router.post('/register', status_code=status.HTTP_201_CREATED)
@rate_limiter.limit(settings.REGISTER_RATE_LIMIT)
async def register(
    request: Request,
    user_data: UserRegister,
    session: AsyncSession = Depends(get_session),
):
    await AuthManager.register_user(session=session, user_data=user_data)
    await session.commit()

    return {'status': 'ok'}


@router.post('/login', status_code=status.HTTP_200_OK)
@rate_limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(
    request: Request,
    response: Response,
    user_data: UserLogin,
    session: AsyncSession = Depends(get_session),
    session_manager: SessionManager = Depends(get_session_manager),
    _: None = Depends(require_csrf),
):
    authenticated_user = await AuthManager.authenticate_user(
        session=session, user_data=user_data
    )

    access_token, refresh_token = await AuthManager.create_session(
        session_manager=session_manager, user_id=authenticated_user.id
    )

    set_tokens_to_response_cookie(
        response=response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=generate_csrf_token(),
    )

    return {'status': 'ok'}


@router.post('/logout')
async def logout(
    request: Request,
    response: Response,
    access: str | None = Depends(get_access_token_from_cookie),
    session_manager: SessionManager = Depends(get_session_manager),
    _: None = Depends(require_csrf),
):
    await AuthManager.revoke_session(
        session_manager=session_manager, access_token=access
    )

    delete_tokens_from_response_cookie(response)

    return {'status': 'ok'}


@router.post('/refresh')
async def refresh_token(
    request: Request,
    response: Response,
    refresh: str | None = Depends(get_refresh_token_from_cookie),
    session: AsyncSession = Depends(get_session),
    session_manager: SessionManager = Depends(get_session_manager),
    _: None = Depends(require_csrf),
):
    access_token, refresh_token = await AuthManager.rotate_session(
        session=session, session_manager=session_manager, refresh_token=refresh
    )

    set_tokens_to_response_cookie(
        response=response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=generate_csrf_token(),
    )

    return {'status': 'ok'}
