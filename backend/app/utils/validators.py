import re

# Минимальный валидный email формата local@domain.tld
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def is_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value))
