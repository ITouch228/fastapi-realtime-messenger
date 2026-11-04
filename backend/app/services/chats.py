from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao import ChatDAO, MessageDAO
from app.exceptions import (
    AppError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)
from app.schemas import ChatInDb, ChatResponse
from app.services.files import FileManager
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


def _build_chat_response(
    chat,
    last_message: tuple[str | None, datetime | None, bool] | None,
    peer_id: int | None,
    last_seen: datetime | None,
    peer_online: bool,
) -> ChatResponse:
    """Собирает ChatResponse из ORM-чата, кортежа последнего сообщения и данных peer.

    Единая точка для get_by_user и get_by_users — раньше логика 'Удалено'/'Файл'
    и проставления peer_* была продублирована в обоих методах.
    """
    response = ChatResponse.model_validate(chat)

    if last_message is not None:
        text, sent_at, is_deleted = last_message
        if is_deleted:
            text = 'Удалено'
        elif not text:
            text = 'Файл'
        response.last_message = text
        response.last_message_sent_at = sent_at

    if peer_id is not None:
        response.peer_online = peer_online
        response.peer_last_seen = last_seen

    return response


class ChatManager:
    """Сервис для работы с чатами."""

    @staticmethod
    async def create(
        session: AsyncSession,
        user_a_id: int,
        user_b_id: int,
    ) -> ChatInDb:
        """Создать чат пары (идемпотентно: существующий чат возвращается как есть)."""
        if user_a_id == user_b_id:
            raise BadRequestError(detail='Нельзя создать чат с самим собой')

        # Собеседник должен существовать и быть активным — иначе в БД
        # остаётся «битый» чат с недоступным участником
        try:
            peer = await UserManager.get(session=session, user_id=user_b_id)
        except NotFoundError:
            raise NotFoundError(detail='Собеседник не найден') from None
        if not peer.is_active:
            raise NotFoundError(detail='Собеседник не найден')

        logger.info('Создание чата между пользователями: %s и %s', user_a_id, user_b_id)
        # Детерминированный порядок [min, max]: один и тот же диалог хранится
        # одинаково (contains-поиск порядка не требует, но нормализация нужна
        # для unique-индекса ix_chats_users_unique и предсказуемых данных).
        try:
            # Savepoint: при гонке (параллельный POST /chats той же пары)
            # unique-индекс откатывает только этот INSERT, основная транзакция
            # (например, отправка сообщения в temp-чате) остаётся живой.
            async with session.begin_nested():
                chat = await ChatDAO.add(
                    session=session, users=sorted([user_a_id, user_b_id])
                )
        except IntegrityError:
            existing = await ChatDAO.find_between_users(
                session=session, user_a_id=user_a_id, user_b_id=user_b_id
            )
            if existing is None:
                logger.exception('Ошибка целостности при создании чата')
                raise AppError(detail='Ошибка создания чата') from None
            return ChatInDb.model_validate(existing)
        return ChatInDb.model_validate(chat)

    @staticmethod
    async def get(
        session: AsyncSession,
        chat_id: int,
    ) -> ChatResponse | None:
        """Чат по id без проверки участников. Не найден → None."""
        logger.info('Получение чата с ID: %s', chat_id)
        chat = await ChatDAO.find_one_or_none(session=session, id=chat_id)
        if chat is None:
            return None
        return ChatResponse.model_validate(chat)

    @staticmethod
    async def get_by_user(user_id: int, session: AsyncSession) -> list[ChatResponse]:
        """Список чатов пользователя с последним сообщением и статусом собеседника."""
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
        online_ids = await manager.online_user_ids()

        result: list[ChatResponse] = []
        for chat in chats:
            last_message = last_messages.get(chat.id)
            peer = _peer_id(chat.users, user_id)
            last_seen = last_seen_map.get(peer) if peer else None
            result.append(
                _build_chat_response(
                    chat, last_message, peer, last_seen, peer in online_ids
                )
            )

        return result

    @staticmethod
    async def get_by_users(
        user_a_id: int, user_b_id: int, session: AsyncSession
    ) -> ChatResponse | None:
        """Чат между двумя пользователями. Не найден → None."""
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

        last_seen = (await UserManager.get_last_seen_map(session, [user_b_id])).get(
            user_b_id
        )

        return _build_chat_response(
            chat,
            last_message,
            user_b_id,
            last_seen,
            await manager.is_online(user_b_id),
        )

    @staticmethod
    async def delete(chat_id: int, user_id: int, session: AsyncSession) -> list[str]:
        """Удалить чат и записи файлов, вернув пути для очистки после commit."""
        chat = await ChatDAO.find_one_or_none(session, id=chat_id)
        if not chat:
            raise NotFoundError('Чат не найден')

        if user_id not in (chat.users or []):
            raise PermissionDeniedError('Доступ запрещен')

        logger.info('Удаление чата: %s', chat_id)

        # Удаляем только строки в транзакции: физический cleanup после commit.
        rel_paths = await FileManager.delete_chat_files(
            session=session, chat_id=chat_id
        )

        await ChatDAO.delete(session=session, chat_id=chat_id)
        logger.info('Чат подготовлен к удалению: %s', chat_id)
        return rel_paths
