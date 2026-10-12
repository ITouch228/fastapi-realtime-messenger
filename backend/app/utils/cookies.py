from fastapi import Cookie


def get_access_token_from_cookie(
    access: str | None = Cookie(default=None, alias='access'),
):
    if not access:
        return None
    return access
