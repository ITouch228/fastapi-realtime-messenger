from http import HTTPStatus


class AppError(Exception):
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, detail: str = 'Внутренняя ошибка сервера') -> None:
        self.detail = detail
        super().__init__(detail)


class BadRequestError(AppError):
    status_code = HTTPStatus.BAD_REQUEST

    def __init__(self, detail: str = 'Некорректный запрос') -> None:
        super().__init__(detail)


class UnauthorizedError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED

    def __init__(self, detail: str = 'Не аутентифицирован') -> None:
        super().__init__(detail)


class PermissionDeniedError(AppError):
    status_code = HTTPStatus.FORBIDDEN

    def __init__(self, detail: str = 'Доступ запрещен') -> None:
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND

    def __init__(self, detail: str = 'Ресурс не найден') -> None:
        super().__init__(detail)


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT

    def __init__(self, detail: str = 'Конфликт') -> None:
        super().__init__(detail)


class PayloadTooLargeError(AppError):
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    def __init__(self, detail: str = 'Файл слишком большой') -> None:
        super().__init__(detail)
