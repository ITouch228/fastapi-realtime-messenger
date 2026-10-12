import secrets
from functools import lru_cache

from app.deps import pwd_context


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


@lru_cache(maxsize=1)
def get_dummy_hash():
    return get_password_hash(secrets.token_urlsafe(32))


DUMMY_PASSWORD_HASH = get_dummy_hash()
