import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FILES_ROOT
from app.dao import ChatDAO, FileDAO, MessageDAO
from app.exceptions import AppError, BadRequestError, NotFoundError
from app.schemas import FileInDb, UserResponse
from app.utils import get_logger

logger = get_logger(__name__)


class FileManager:
    @staticmethod
    async def create(
        session: AsyncSession,
        chat_id: int,
        file_name: str,
        owner_id: int,
        original_name: str,
        mime_types: str,
        size_bytes: int,
    ) -> FileInDb:
        logger.info('Добавление файла в БД: чат %s, файл %s', chat_id, file_name)

        if '..' in file_name or file_name.startswith('/'):
            raise BadRequestError('Некорректное имя файла')

        if chat_id < 0:
            raise BadRequestError('Некорректный ID чата')

        rel_path = f'{chat_id}/{file_name}'
        abs_path = (FILES_ROOT / rel_path).resolve()

        if os.path.exists(abs_path):
            file = await FileDAO.find_one_or_none(session=session, file_path=rel_path)
            if file:
                return FileInDb.model_validate(file)

        try:
            new_file = await FileDAO.add(
                session=session,
                file_path=rel_path,
                owner_id=owner_id,
                original_name=original_name,
                mime_type=mime_types,
                size_bytes=size_bytes,
            )
            logger.info('Файл успешно добавлен: чат %s, файл %s', chat_id, file_name)
            return FileInDb.model_validate(new_file)
        except AppError:
            raise
        except Exception:
            # TODO: [SMELL] except Exception — ловит всё, включая OperationalError
            # (БД недоступна) и превращает в BadRequestError (400). Логично ловить
            # IntegrityError → ConflictError, остальное — AppError (500).
            # docs/architecture.md §5: 🟢 except Exception в FileManager.create
            logger.exception('Ошибка при добавлении файла: %s', file_name)
            raise BadRequestError('Ошибка регистрации файла')

    @staticmethod
    async def get(session: AsyncSession, file_id: int) -> FileInDb | None:
        """Возвращает FileInDb по id или None, если запись не найдена."""
        file = await FileDAO.find_one_or_none(session=session, id=file_id)
        if file is None:
            return None
        return FileInDb.model_validate(file)

    @staticmethod
    async def ensure_can_access_file(
        session: AsyncSession,
        file_id: int,
        current_user: UserResponse,
    ) -> None:
        chat_ids = await MessageDAO.list_chat_ids_by_file(
            session=session, file_id=file_id
        )
        if not chat_ids:
            raise NotFoundError('Файл не найден')

        user_chats = await ChatDAO.find_by_ids_and_user(
            session=session, chat_ids=chat_ids, user_id=current_user.id
        )
        if not user_chats:
            raise NotFoundError('Файл не найден')
