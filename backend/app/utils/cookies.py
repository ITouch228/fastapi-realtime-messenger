from datetime import timedelta

from fastapi import Cookie, Response

from app.config import settings


def get_access_token_from_cookie(
    access: str | None = Cookie(default=None, alias='access'),
):
    if not access:
        return None
    return access


def set_tokens_to_response_cookie(
    response: Response, access_token, refresh_token, csrf_token: str | None = None
):
    response.set_cookie(
        key='access',
        path='/',
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=int(
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES).total_seconds()
        ),
    )
    response.set_cookie(
        key='refresh',
        path='/',
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=int(timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
    )
    if csrf_token is not None:
        response.set_cookie(
            key='csrftoken',
            path='/',
            value=csrf_token,
            httponly=False,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )


def delete_tokens_from_response_cookie(response: Response):
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
    response.delete_cookie(
        key='csrftoken',
        path='/',
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
