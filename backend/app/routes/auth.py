from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from app.config import settings
from app.dao.dao import UserDAO
from app.database import get_session
from app.schemas.user import UserCreate, UserInDB, UserResponse
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_user_from_cookie,
    get_password_hash,
    verify_token,
)
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
templates: Jinja2Templates = Jinja2Templates(directory='app/templates')


router = APIRouter(prefix='/auth')


@router.post('/register', status_code=status.HTTP_201_CREATED)
async def post_register(
    request: Request,
    user_data: UserCreate = Form(...),
    session: AsyncSession = Depends(get_session),
):
    logger.info(
        f'Registration attempt for user with username: {user_data.username}, email: {user_data.email}'
    )

    username = user_data.username.strip()
    email = user_data.email.strip()
    password = user_data.password

    if len(username) < 3:
        return templates.TemplateResponse(
            'register.html',
            {'request': request, 'message': 'Логин должен быть минимум 3 символа'},
            status_code=400,
        )

    try:
        validate_email(email)
    except EmailNotValidError:
        return templates.TemplateResponse(
            'register.html',
            {'request': request, 'message': 'Некорректный email'},
            status_code=400,
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            'register.html',
            {'request': request, 'message': 'Пароль должен быть минимум 6 символов'},
            status_code=400,
        )

    existing_user_username = await UserDAO.find_one_or_none(
        session=session, username=user_data.username
    )
    if existing_user_username:
        return templates.TemplateResponse(
            'register.html',
            {
                'request': request,
                'message': 'Пользователь с таким именем уже существует',
            },
            status_code=400,
        )
    existing_user_email = await UserDAO.find_one_or_none(
        session=session, email=user_data.email
    )
    if existing_user_email:
        return templates.TemplateResponse(
            'register.html',
            {
                'request': request,
                'message': 'Пользователь с такой почтой уже существует',
            },
            status_code=400,
        )

    try:
        user_dict = {
            'username': username,
            'email': email,
            'hashed_password': get_password_hash(password),
        }

        user = await UserDAO.add(session=session, **user_dict)
        if user:
            logger.info(f'Successfully registered user with ID: {user.id}')
        else:
            logger.error(
                f'Registration failed for user with username: {user_data.username}, email: {user_data.email}'
            )

        return templates.TemplateResponse(
            'login.html', {'request': request, 'message': 'Регистрация прошла успешно!'}
        )
    except Exception as e:
        logger.error(f'Registration error: {str(e)}')
        return templates.TemplateResponse(
            'register.html', {'request': request, 'message': 'Ошибка при регистрации'}
        )


@router.post('/login')
async def post_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    try:
        logger.info(f'Login attempt for username: {username}')

        user = await UserDAO.find_one_or_none(session=session, username=username)
        if not user:
            logger.warning(f'User not found: {username}')
            return templates.TemplateResponse(
                'login.html',
                {'request': request, 'message': 'Неверное имя пользователя'},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        authenticated_user = await authenticate_user(
            session=session, username=username, password=password
        )
        if not authenticated_user:
            logger.warning(f'Invalid password for user: {username}')
            return templates.TemplateResponse(
                'login.html',
                {'request': request, 'message': 'Неверный пароль'},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            access_token_expires = timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
            access_token = create_access_token(
                data={'sub': str(authenticated_user.id)},
                expires_delta=access_token_expires,
            )

            refresh_token = create_refresh_token({'sub': str(authenticated_user.id)})
        except Exception as e:
            logger.error(f'Token generation failed: {str(e)}')
            raise HTTPException(status_code=500, detail='Authentication failed')

        logger.info(f'Successful login for user ID: {authenticated_user.id}')

        response = RedirectResponse(url='/messages', status_code=status.HTTP_302_FOUND)

        response.set_cookie(
            key='access',
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=access_token_expires.seconds,
        )
        response.set_cookie(
            key='refresh',
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=int(
                timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()
            ),
        )

        return response

    except Exception as e:
        logger.error(f'Login error for {username}: {str(e)}')
        return templates.TemplateResponse(
            'login.html',
            {'request': request, 'message': 'Произошла ошибка при входе'},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.post('/logout')
async def logout():
    response = JSONResponse(content={'status': 'success'})

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


@router.get('/me', response_model=UserResponse)
async def read_me(
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
):
    return current_user


@router.post('/refresh')
async def refresh_token(
    response: Response, refresh: str = Cookie(default=None, alias='refresh')
):
    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='No refresh token provided'
        )

    user_id = verify_token(refresh, token_type='refresh')
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid refresh token'
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data={'sub': str(user_id)}, expires_delta=access_token_expires
    )

    response.set_cookie(
        key='access',
        value=new_access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=access_token_expires.seconds,
    )

    return {'status': 'success'}
