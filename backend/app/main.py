from collections.abc import Callable
from typing import cast

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import STATIC_DIR
from app.routes import auth, chats, files, messages, pages, users, ws
from app.services.limiter import limiter
from app.utils.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


app = FastAPI()

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    cast('Callable[[Request, Exception], Response]', _rate_limit_exceeded_handler),
)

app.include_router(pages.router)
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

app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')


if __name__ == '__main__':
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000)
