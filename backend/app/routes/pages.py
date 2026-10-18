from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.deps import templates
from app.schemas import UserResponse
from app.services import AuthManager

router = APIRouter()


@router.get('/')
async def get_index_page():
    return RedirectResponse('/auth/login')


@router.get('/auth/register')
async def get_register_page(request: Request):
    return templates.TemplateResponse('register.html', {'request': request})


@router.get('/auth/login')
async def get_login_page(
    request: Request,
    current_user: UserResponse | None = Depends(
        AuthManager.get_current_user_from_cookie
    ),
):
    if not current_user:
        return templates.TemplateResponse('login.html', {'request': request})
    return RedirectResponse('/messages')


@router.get('/messages')
async def get_messages_page(
    request: Request,
    current_user: UserResponse | None = Depends(
        AuthManager.get_current_user_from_cookie
    ),
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
