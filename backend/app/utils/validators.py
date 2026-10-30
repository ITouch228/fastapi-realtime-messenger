import re
from pathlib import Path

from app.exceptions import BadRequestError

# Минимальный валидный email формата local@domain.tld
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

# Ограничение на длину имени файла (колонка original_name — String(255))
_MAX_FILE_NAME_LEN = 255


def is_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value))


def validate_file_name(file_name: str) -> str:
    """
    Проверяет, что file_name — безопасное базовое имя файла.

    Отклоняет: пустые имена, путевые разделители (в т.ч. обратную косую черту,
    значимую на Windows), '.' / '..', управляющие символы, имена длиннее 255.
    Возвращает проверенное имя.
    """
    if not file_name:
        raise BadRequestError(detail='Пустое имя файла')

    # Базовое имя POSIX-пути после нормализации Windows-разделителей
    name = Path(file_name.replace('\\', '/')).name
    if not name or name in ('.', '..'):
        raise BadRequestError(detail='Некорректное имя файла')
    if name != file_name:
        raise BadRequestError(detail='Некорректное имя файла')

    # Управляющие символы (NUL, переводы строк и т.п.)
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise BadRequestError(detail='Некорректное имя файла')

    if len(name) > _MAX_FILE_NAME_LEN:
        raise BadRequestError(detail='Имя файла слишком длинное')

    return name
