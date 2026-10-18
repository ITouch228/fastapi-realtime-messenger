from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao import FileDAO, MessageDAO
from app.exceptions import NotFoundError, PermissionDeniedError
from app.schemas import FileInDb, FileResponse, MessageInDb, MessageResponse
from app.utils import get_logger

logger = get_logger(__name__)


class MessageManager:
    """Сервис для работы с сообщениями."""

    @staticmethod
    async def create(
        session: AsyncSession,
        chat_id: int,
        sender_id: int,
        text: str | None,
        file_id: int | None,
        sent_at: datetime,
    ) -> MessageInDb:
        message = await MessageDAO.add(
            session=session,
            chat_id=chat_id,
            sender_id=sender_id,
            message_text=text,
            message_file_id=file_id,
            sent_at=sent_at,
        )
        return MessageInDb.model_validate(message)

    @staticmethod
    async def get_chat_messages(
        session: AsyncSession, chat_id: int, user_id: int
    ) -> list[MessageResponse]:
        """Сообщения чата с проверкой доступа — чат и сообщения одним запросом."""
        logger.info('Получение сообщений чата %s пользователем %s', chat_id, user_id)

        rows = await MessageDAO.find_by_chat_with_chat(session=session, chat_id=chat_id)
        if not rows:
            raise NotFoundError('Чат не найден')

        chat, _ = rows[0]
        if user_id not in (chat.users or []):
            raise PermissionDeniedError('Доступ запрещен')

        messages = [
            MessageInDb.model_validate(message)
            for _, message in rows
            if message is not None
        ]
        return await MessageManager.build_message_responses(
            session=session, messages=messages
        )

    @staticmethod
    async def delete(session: AsyncSession, message_id: int, user_id: int) -> None:
        """Мягкое удаление: проверка автора и членства в чате одним запросом."""
        logger.info('Удаление сообщения %s пользователем %s', message_id, user_id)

        row = await MessageDAO.find_with_chat_users(
            session=session, message_id=message_id
        )
        if row is None:
            raise NotFoundError('Сообщение не найдено')

        message, chat_users = row
        if message.sender_id != user_id:
            raise PermissionDeniedError('Доступ запрещен')
        if user_id not in (chat_users or []):
            raise PermissionDeniedError('Доступ запрещен')

        await MessageDAO.soft_delete_message(session=session, message_id=message_id)

    @staticmethod
    async def build_message_response(
        session: AsyncSession, message: MessageInDb
    ) -> MessageResponse:
        responses = await MessageManager.build_message_responses(
            session=session, messages=[message]
        )
        return responses[0]

    @staticmethod
    async def build_message_responses(
        session: AsyncSession, messages: list[MessageInDb]
    ) -> list[MessageResponse]:
        """Собирает MessageResponse, подтягивая файлы одним запросом (без N+1)."""
        file_ids = [m.message_file_id for m in messages if m.message_file_id]
        files_map = await MessageManager._resolve_files_meta(
            session=session, file_ids=file_ids
        )

        responses: list[MessageResponse] = []
        for message in messages:
            response = MessageResponse.model_validate(message)
            if message.message_file_id:
                response.file = files_map.get(message.message_file_id)
            responses.append(response)

        return responses

    @staticmethod
    async def _resolve_files_meta(
        session: AsyncSession, file_ids: list[int]
    ) -> dict[int, FileResponse]:
        """Метаданные файлов по их id одним запросом."""
        if not file_ids:
            return {}

        files = await FileDAO.find_by_ids(session=session, file_ids=file_ids)
        result: dict[int, FileResponse] = {}
        for file_in_db in files:
            file = FileInDb.model_validate(file_in_db)
            result[file.id] = FileResponse(
                id=file.id,
                kind='image' if file.mime_type.startswith('image/') else 'file',
                url=f'/api/files/{file.id}',
                mime_type=file.mime_type,
                filename=file.original_name,
                size=file.size_bytes,
            )
        return result
