import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.deps import templates
from app.schemas.user import UserInDB
from app.services.auth import (
    get_current_user,
    get_current_user_from_cookie,
)
from app.services.event_bus import bus

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
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
):
    if not current_user:
        return templates.TemplateResponse('login.html', {'request': request})
    return RedirectResponse('/messages')


@router.get('/messages')
async def get_messages_page(
    request: Request,
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
):
    if not current_user:
        return RedirectResponse('/auth/login', status_code=302)

    return templates.TemplateResponse(
        'index.html',
        {
            'request': request,
        },
    )


@router.get('/sse-updates')
async def sse_updates(
    current_user: UserInDB = Depends(get_current_user),
):
    queue = bus.subscribe(current_user.id)

    async def event_generator():
        try:
            yield ': connected\n\n'
            while True:
                with contextlib.suppress(asyncio.TimeoutError):
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f'data: {json.dumps(payload)}\n\n'
                yield ': ping\n\n'
        finally:
            bus.unsubscribe(current_user.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'},
    )


@router.get('/favicon.ico')
async def favicon():
    return RedirectResponse(url='/static/images/favicon.ico')
