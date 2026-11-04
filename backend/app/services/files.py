from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FILES_ROOT
from app.dao import ChatDAO, FileDAO, MessageDAO
from app.exceptions import AppError, BadRequestError, ConflictError, NotFoundError
from app.schemas import FileInDb, UserResponse
from app.utils import delete_files_from_disk, get_logger
from app.utils.validators import validate_file_name

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
        """Зарегистрировать файл в БД (идемпотентно по file_path)."""
        logger.info('Добавление файла в БД: чат %s, файл %s', chat_id, file_name)

        validate_file_name(file_name)

        if chat_id < 0:
            raise BadRequestError('Некорректный ID чата')

        rel_path = f'{chat_id}/{file_name}'
        abs_path = (FILES_ROOT / rel_path).resolve()
        if not abs_path.is_relative_to(FILES_ROOT.resolve()):
            raise BadRequestError('Некорректный путь файла')

        try:
            # Savepoint: при коллизии уникального file_path откатывается только
            # этот INSERT, основная транзакция (чат/сообщение) остаётся живой
            async with session.begin_nested():
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
        except IntegrityError:
            # Гонка: параллельная загрузка того же пути уже создала запись —
            # возвращаем существующую (idempotent create).
            existing = await FileDAO.find_one_or_none(
                session=session, file_path=rel_path
            )
            if existing is not None:
                return FileInDb.model_validate(existing)
            logger.exception('Ошибка целостности при добавлении файла: %s', file_name)
            raise ConflictError('Файл уже зарегистрирован') from None
        except AppError:
            raise
        except SQLAlchemyError:
            logger.exception('Ошибка БД при регистрации файла: %s', file_name)
            raise AppError(detail='Ошибка регистрации файла') from None

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
        """Проверить, что пользователь состоит в чате, где есть файл. Иначе NotFoundError."""
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

    @staticmethod
    async def delete_chat_files(session: AsyncSession, chat_id: int) -> list[str]:
        """Удалить записи File в текущей транзакции и вернуть пути для cleanup.

        Физические файлы удаляются только ПОСЛЕ успешного commit вызывающим
        кодом. При rollback записи и вложения остаются доступными.
        """
        files = await FileDAO.find_by_chat(session=session, chat_id=chat_id)
        if not files:
            return []

        rel_paths = [f.file_path for f in files]
        await FileDAO.delete_by_chat(session=session, chat_id=chat_id)
        logger.info('Удалено %d файлов чата: %s', len(rel_paths), chat_id)

        return rel_paths

    @staticmethod
    async def cleanup_failed_upload(rel_path: str) -> None:
        """Best-effort удаление только что созданного файла после неуспешного POST.

        Не допускаем маскирования первичной ошибки транзакции ошибкой диска.
        Путь берётся из серверного UUID-имени, а не из имени от клиента.
        """
        try:
            await delete_files_from_disk([rel_path])
        except Exception:
            logger.exception(
                'Не удалось убрать новое вложение после отката: %s', rel_path
            )

    @staticmethod
    async def cleanup_deleted_chat_files(rel_paths: list[str]) -> None:
        """Best-effort очистка диска после commit; сбой не отменяет удаление чата."""
        if not rel_paths:
            return
        try:
            await delete_files_from_disk(rel_paths)
        except Exception:
            logger.exception(
                'Не удалось очистить %d файлов после удаления чата; '
                'требуется повторная очистка осиротевших файлов',
                len(rel_paths),
            )
