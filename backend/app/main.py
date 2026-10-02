import asyncio
import json

import uvicorn
from fastapi import Cookie, Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

from app.routes import auth, chats, files, messages, users, ws
from app.schemas.user import UserInDB
from app.services.auth import get_current_user_from_cookie, verify_token
from app.utils.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


app = FastAPI()

app.include_router(auth.router, prefix='/api')
app.include_router(users.router, prefix='/api')
app.include_router(chats.router, prefix='/api')
app.include_router(messages.router, prefix='/api')
app.include_router(files.router, prefix='/api')
app.include_router(ws.router, prefix='/api')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'https://localhost:8000',
        'https://127.0.0.1:8000',
        'https://itmessage.itouch.pw',
    ],
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['*'],
    expose_headers=['Access-Control-Allow-Origin'],
)

app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

last_update_counter: dict[int, int] = {}


@app.get('/')
def get_index_page():
    logger.info('get_index_page')
    return RedirectResponse('/auth/login')


@app.get('/auth/register')
def get_register_page(request: Request):
    logger.info('get_register_page')
    return templates.TemplateResponse('register.html', {'request': request})


@app.get('/auth/login')
def get_login_page(request: Request, access: str | None = Cookie(default=None)):
    logger.info('get_login_page')
    if not access or not verify_token(access):
        return templates.TemplateResponse('login.html', {'request': request})
    else:
        return RedirectResponse('/messages')


@app.get('/messages')
async def get_messages_page(
    request: Request,
    current_user: UserInDB | None = Depends(get_current_user_from_cookie),
):
    logger.info('get_messages_page')

    if not current_user:
        return RedirectResponse('/auth/login', status_code=302)

    return templates.TemplateResponse(
        'index.html',
        {
            'request': request,
        },
    )


@app.get('/sse-updates')
async def sse_updates():
    client_last_counter = last_update_counter.copy()

    async def event_generator():
        while True:
            for key in last_update_counter:
                if last_update_counter.get(key) > client_last_counter.get(key, -1):
                    client_last_counter[key] = last_update_counter[key]
                    yield f'data: {json.dumps({"chat_id": key})}\n\n'

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'},
    )


@app.get('/favicon.ico')
async def favicon():
    return RedirectResponse(url='/static/images/favicon.ico')


if __name__ == '__main__':
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000)
