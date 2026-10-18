import secrets

from fastapi import Cookie, Request
from fastapi.responses import Response

from app.config import settings
from app.exceptions import PermissionDeniedError


def generate_csrf_token() -> str:
    """Генерирует случайный CSRF-токен."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """Устанавливает куку csrftoken для Double Submit Cookie."""
    response.set_cookie(
        key='csrftoken',
        path='/',
        value=token,
        httponly=False,  # JS должен читать для заголовка
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


async def require_csrf(
    request: Request,
    csrf_token: str = Cookie(default=None, alias='csrftoken'),
) -> None:
    """
    Проверяет CSRF через Double Submit Cookie.
    Заголовок X-CSRF-Token должен совпадать с кукой csrftoken.
    """
    header_token = request.headers.get('X-CSRF-Token')
    if not csrf_token or not header_token or csrf_token != header_token:
        raise PermissionDeniedError(detail='Неверный CSRF-токен')
