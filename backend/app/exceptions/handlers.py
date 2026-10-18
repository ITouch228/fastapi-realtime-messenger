from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.exceptions.base import AppError
from app.utils.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error('Внутренняя ошибка приложения: %s', exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={'detail': exc.detail},
        )
