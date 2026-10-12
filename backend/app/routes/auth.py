from datetime import timedelta

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from jose import JWTError
from redis import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.config import settings
from app.dao.dao import UserDAO
from app.database import get_session
from app.schemas.user import UserCreate, UserLogin
from app.services.auth import (
    authenticate_user,
    create_user,
)
from app.services.limiter import limiter
from app.services.session_manager import SessionManager, get_session_manager
from app.utils.jwt import create_access_token, create_refresh_token, verify_token
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix='/auth')


@router.post('/register', status_code=status.HTTP_201_CREATED)
@limiter.limit('10/hour')
async def register(
    request: Request,
    user_data: UserCreate,
    session: AsyncSession = Depends(get_session),
):
    username = user_data.username.strip()
    email = user_data.email.strip().lower()
    password = user_data.password

    logger.info(
        'Попытка регистрации пользователя: %s, %s',
        email,
        username,
    )

    try:
        user = await create_user(
            session=session, username=username, email=email, password=password
        )

        logger.info('Успешная регистрация пользователя: %s', user.id)
        return {'status': 'ok'}
    except IntegrityError as e:
        constraint = getattr(e.orig, 'constraint_name', '') or ''
        if 'users_username_key' in constraint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Пользователь с таким именем уже существует',
            )
        if 'users_email_key' in constraint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Пользователь с таким email уже существует',
            )
        logger.exception('Неизвестная ошибка целостности при регистрации')
        raise HTTPException(500, 'Ошибка регистрации')


@router.post('/login', status_code=status.HTTP_200_OK)
@limiter.limit('5/minute')
async def login(
    request: Request,
    user_data: UserLogin,
    session: AsyncSession = Depends(get_session),
    session_manager: SessionManager = Depends(get_session_manager),
):
    login = user_data.login.strip()
    password = user_data.password

    logger.info('Попытка входа с логином: %s', login)

    authenticated_user = await authenticate_user(
        session=session, login=login, password=password
    )
    if not authenticated_user:
        logger.warning('Неверный пароль для пользователя с логином: %s', login)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Неверный пароль',
        )

    try:
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        session_id = await session_manager.create(authenticated_user.id)
        access_token = create_access_token(
            session_id=session_id,
            expires_delta=access_token_expires,
        )
        refresh_token = create_refresh_token(session_id=session_id)
    except (JWTError, RedisError):
        logger.exception(
            'Ошибка генерации токена для пользователя: %s', authenticated_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Ошибка аутентификации',
        )

    logger.info('Успешный вход пользователя: %s', authenticated_user.id)

    response = JSONResponse(content={'status': 'ok'})

    response.set_cookie(
        key='access',
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=int(access_token_expires.total_seconds()),
    )
    response.set_cookie(
        key='refresh',
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
    )

    return response


@router.post('/logout')
async def logout(
    request: Request,
    access: str = Cookie(default=None, alias='access'),
    session_manager: SessionManager = Depends(get_session_manager),
):
    if access:
        session_id = verify_token(access, token_type='access')
        if session_id:
            await session_manager.remove(session_id)

    response = JSONResponse(content={'status': 'ok'})

    response.delete_cookie(
        key='access',
        path='/',
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key='refresh',
        path='/',
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return response


@router.post('/refresh')
async def refresh_token(
    request: Request,
    response: Response,
    refresh: str = Cookie(default=None, alias='refresh'),
    session: AsyncSession = Depends(get_session),
    session_manager: SessionManager = Depends(get_session_manager),
):
    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Не передан refresh токен'
        )

    session_id = verify_token(refresh, token_type='refresh')
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Неверный refresh токен'
        )

    user_id = await session_manager.get_user_id(session_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Неверный refresh токен',
        )

    user = await UserDAO.find_one_or_none(session=session, id=user_id)
    if user is None or not user.is_active:
        await session_manager.remove(session_id)
        logger.warning('Пользователь с id: %s не активен', user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Пользователь не активен',
        )

    await session_manager.remove(session_id)
    new_session_id = await session_manager.create(user_id)

    try:
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = create_access_token(
            session_id=new_session_id,
            expires_delta=access_token_expires,
        )
        new_refresh_token = create_refresh_token(session_id=new_session_id)
    except (JWTError, RedisError):
        logger.exception('Ошибка генерации токена для пользователя: %s', user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Ошибка аутентификации',
        )

    response.set_cookie(
        key='access',
        value=new_access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=int(access_token_expires.total_seconds()),
    )
    response.set_cookie(
        key='refresh',
        value=new_refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
    )

    return {'status': 'ok'}
