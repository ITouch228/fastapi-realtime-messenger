from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.exceptions import (
    AppError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
)
from app.schemas import ChatResponse, MessageResponse, UserResponse
from app.services import (
    ChatManager,
    FileManager,
    MessageManager,
    manager,
)
from app.utils import get_logger, require_csrf, save_file

logger = get_logger(__name__)


router = APIRouter(prefix='/messages')


@router.get('/{chat_id}', response_model=list[MessageResponse])
async def get_chat_messages(
    chat_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await MessageManager.get_chat_messages(
        session=session, chat_id=chat_id, user_id=current_user.id
    )


@router.post(
    '/{chat_id}', response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def send_message(
    chat_id: str,
    message_text: str = Form(default=None),
    file_name: str = Form(default=None),
    file: UploadFile = File(default=None),
    peer_id: int = Form(default=None),
    client_id: str = Form(default=None),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
):
    try:
        sent_at = datetime.now(UTC)

        # Создание нового чата: peer_id в FormData → ChatManager.create
        if peer_id is not None:
            created_chat = await ChatManager.create(
                session=session, user_a_id=current_user.id, user_b_id=peer_id
            )
            chat_id_int: int = created_chat.id
            # payload собирается из валидированной схемы — как new_message
            new_chat_payload = {
                'type': 'new_chat',
                'message': ChatResponse.model_validate(created_chat).model_dump(
                    mode='json'
                ),
            }
            # одному батчем: собеседнику и отправителю (клиент увидит новый чат)
            await manager.send_to_users(new_chat_payload, [peer_id, current_user.id])
        else:
            try:
                chat_id_int = int(chat_id)
            except (ValueError, TypeError):
                raise BadRequestError(detail='Неверный формат ID чата')

        chat = await ChatManager.get(session=session, chat_id=chat_id_int)
        if not chat:
            raise NotFoundError(detail='Чат не найден')
        if current_user.id not in (chat.users or []):
            raise PermissionDeniedError(detail='Доступ запрещен')

        if message_text and len(message_text) > settings.MAX_MESSAGE_LENGTH:
            raise BadRequestError(detail='Сообщение слишком длинное')

        # файл
        file_id: int | None = None
        if file:
            file_content = await file.read()

            # Уникальное имя на диске — предотвращает коллизию имён,
            # которая ломает историю сообщений: если пользователь
            # загрузил тот же файл повторно, новый файл перезаписал бы
            # старый на диске, а БД вернула бы тот же file_id — и
            # предыдущие сообщения с этим file_id показали бы новое содержимое
            disk_name = f'{uuid4().hex}_{file_name}'

            await save_file(chat_id_int, disk_name, file_content)

            file_in_db = await FileManager.create(
                chat_id=chat_id_int,
                file_name=disk_name,
                owner_id=current_user.id,
                original_name=file.filename or file_name,
                mime_types=file.content_type or 'application/octet-stream',
                size_bytes=len(file_content),
                session=session,
            )
            file_id = file_in_db.id

        # Пустое сообщение (ни текста, ни файла) — фронт блокирует, бэк тоже
        # обязан отклонять, иначе в чате остаются пустые невидимки
        if not (message_text or '').strip() and file_id is None:
            raise BadRequestError(detail='Пустое сообщение')

        message = await MessageManager.create(
            session=session,
            chat_id=chat_id_int,
            sender_id=current_user.id,
            text=message_text,
            file_id=file_id,
            sent_at=sent_at,
        )

        message_response = await MessageManager.build_message_response(
            session=session, message=message
        )

        await session.commit()

        # new_message шлём всем участникам, включая отправителя:
        # client_id позволяет клиенту надёжно подтвердить оптимистичное сообщение
        payload = {
            'type': 'new_message',
            'message': message_response.model_dump(mode='json'),
            'client_id': client_id,
        }
        await manager.send_to_users(payload, list(chat.users or []))

        return message_response

    except AppError:
        raise
    except (OSError, RuntimeError) as exc:
        logger.exception('Ошибка I/O при отправке сообщения')
        raise AppError(detail='Ошибка сервера') from exc
    except Exception:
        logger.critical('Неожиданная ошибка при отправке сообщения', exc_info=True)
        raise


@router.delete('/{message_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
):
    await MessageManager.delete(
        session=session, message_id=message_id, user_id=current_user.id
    )
    await session.commit()
