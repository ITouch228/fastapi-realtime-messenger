from fastapi import APIRouter, Cookie, Depends
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.deps import get_current_user_from_cookie, templates
from app.schemas import UserResponse
from app.utils import generate_csrf_token, set_csrf_cookie

router = APIRouter()


@router.get('/')
async def get_index_page():
    return RedirectResponse('/auth/login')


@router.get('/auth/register')
async def get_register_page(
    request: Request,
    csrf_token: str = Cookie(default=None, alias='csrftoken'),
):
    response = templates.TemplateResponse('register.html', {'request': request})
    if not csrf_token:
        set_csrf_cookie(response, generate_csrf_token())
    return response


@router.get('/auth/login')
async def get_login_page(
    request: Request,
    current_user: UserResponse | None = Depends(get_current_user_from_cookie),
    csrf_token: str = Cookie(default=None, alias='csrftoken'),
):
    if current_user:
        return RedirectResponse('/messages')
    response = templates.TemplateResponse('login.html', {'request': request})
    if not csrf_token:
        set_csrf_cookie(response, generate_csrf_token())
    return response


@router.get('/messages')
async def get_messages_page(
    request: Request,
    current_user: UserResponse | None = Depends(get_current_user_from_cookie),
):
    if not current_user:
        return RedirectResponse('/auth/login', status_code=302)

    return templates.TemplateResponse(
        'index.html',
        {
            'request': request,
        },
    )


@router.get('/favicon.ico')
async def favicon():
    return RedirectResponse(url='/static/images/favicon.ico')
