from sqlalchemy.ext.asyncio import AsyncSession

from app.dao import ChatDAO, MessageDAO
from app.exceptions import NotFoundError, PermissionDeniedError
from app.schemas import ChatInDb, ChatResponse
from app.services.users import UserManager
from app.services.websocket_manager import manager
from app.utils import get_logger

logger = get_logger(__name__)


def _peer_id(chat_users: list[int] | None, user_id: int) -> int | None:
    """Вернуть id собеседника (первый участник, не равный user_id)."""
    for uid in chat_users or []:
        if uid != user_id:
            return uid
    return None


# TODO: [DUP] last_message ('Удалено' / 'Файл') продублирован в get_by_user
# и get_by_users — вынести в общий _build_chat_response(chat, last_message, peer).
# docs/architecture.md §5: 🟡 дублирование сборки ChatResponse


class ChatManager:
    """Сервис для работы с чатами."""

    @staticmethod
    async def create(
        session: AsyncSession,
        user_a_id: int,
        user_b_id: int,
    ) -> ChatInDb:
        logger.info('Создание чата между пользователями: %s и %s', user_a_id, user_b_id)
        chat = await ChatDAO.add(session=session, users=[user_a_id, user_b_id])
        return ChatInDb.model_validate(chat)

    @staticmethod
    async def get(
        session: AsyncSession,
        chat_id: int,
    ) -> ChatResponse | None:
        logger.info('Получение чата с ID: %s', chat_id)
        chat = await ChatDAO.find_one_or_none(session=session, id=chat_id)
        if chat is None:
            return None
        return ChatResponse.model_validate(chat)

    @staticmethod
    async def get_by_user(user_id: int, session: AsyncSession) -> list[ChatResponse]:
        logger.info('Загрузка чатов пользователя с ID: %s', user_id)

        chats = await ChatDAO.find_by_user(session=session, user_id=user_id)

        chat_ids = [c.id for c in chats] if chats else []
        last_messages = (
            await MessageDAO.get_last_messages_for_chats(session, chat_ids)
            if chat_ids
            else {}
        )

        peer_ids = [pid for pid in (_peer_id(c.users, user_id) for c in chats) if pid]
        last_seen_map = await UserManager.get_last_seen_map(session, peer_ids)

        result: list[ChatResponse] = []
        for chat in chats:
            last_message = last_messages.get(chat.id)
            if last_message is None:
                last_message_text = None
                last_message_sent_at = None
            else:
                text, sent_at, is_deleted = last_message
                if is_deleted:
                    text = 'Удалено'
                elif not text:
                    text = 'Файл'
                last_message_text = text
                last_message_sent_at = sent_at

            chat_response = ChatResponse.model_validate(chat)
            chat_response.last_message = last_message_text
            chat_response.last_message_sent_at = last_message_sent_at

            peer = _peer_id(chat.users, user_id)
            if peer is not None:
                chat_response.peer_online = manager.is_online(peer)
                chat_response.peer_last_seen = last_seen_map.get(peer)

            result.append(chat_response)

        return result

    @staticmethod
    async def get_by_users(
        user_a_id: int, user_b_id: int, session: AsyncSession
    ) -> ChatResponse | None:
        logger.info('Загрузка чата пользователей с ID: %s %s', user_a_id, user_b_id)

        chat = await ChatDAO.find_between_users(
            session=session, user_a_id=user_a_id, user_b_id=user_b_id
        )

        if chat is None:
            return None

        chat_ids = [chat.id] if chat else []

        last_message = (
            await MessageDAO.get_last_messages_for_chats(session, chat_ids)
            if chat_ids
            else {}
        ).get(chat.id)

        if last_message is None:
            last_message_text = None
            last_message_sent_at = None
        else:
            text, sent_at, is_deleted = last_message
            if is_deleted:
                text = 'Удалено'
            elif not text:
                text = 'Файл'
            last_message_text = text
            last_message_sent_at = sent_at

        chat_response = ChatResponse.model_validate(chat)
        chat_response.last_message = last_message_text
        chat_response.last_message_sent_at = last_message_sent_at

        chat_response.peer_online = manager.is_online(user_b_id)
        chat_response.peer_last_seen = (
            await UserManager.get_last_seen_map(session, [user_b_id])
        ).get(user_b_id)

        return chat_response

    @staticmethod
    async def delete(chat_id: int, user_id: int, session: AsyncSession) -> None:
        chat = await ChatDAO.find_one_or_none(session, id=chat_id)
        if not chat:
            raise NotFoundError('Чат не найден')

        if user_id not in (chat.users or []):
            raise PermissionDeniedError('Доступ запрещен')

        logger.info('Удаление чата: %s', chat_id)
        await ChatDAO.delete(session=session, chat_id=chat_id)
        logger.info('Чат успешно удалён: %s', chat_id)
