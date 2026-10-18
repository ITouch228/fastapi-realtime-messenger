from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import (
    AppError,
    BadRequestError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
)
from app.schemas import MessageResponse, UserResponse
from app.services import (
    AuthManager,
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
    current_user: UserResponse = Depends(AuthManager.get_current_user),
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
    current_user: UserResponse = Depends(AuthManager.get_current_user),
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
            await manager.send_personal_message(
                {
                    'type': 'new_chat',
                    'message': created_chat.model_dump(mode='json'),
                },
                peer_id,
            )
            # шлём и себе, чтобы клиент увидел новый чат
            await manager.send_personal_message(
                {
                    'type': 'new_chat',
                    'message': created_chat.model_dump(mode='json'),
                },
                current_user.id,
            )
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

        if message_text and len(message_text) > 10000:
            raise BadRequestError(detail='Сообщение слишком длинное')

        # файл
        file_id: int | None = None
        if file:
            if file.size and file.size > 10 * 1024 * 1024:
                raise PayloadTooLargeError(detail='Файл слишком большой')

            file_content = await file.read()
            success = await save_file(chat_id_int, file_name, file_content)
            if not success:
                raise AppError(detail='Ошибка при сохранении файла')

            file_in_db = await FileManager.create(
                chat_id=chat_id_int,
                file_name=file_name,
                owner_id=current_user.id,
                original_name=file.filename or file_name,
                mime_types=file.content_type or 'application/octet-stream',
                size_bytes=len(file_content),
                session=session,
            )
            file_id = file_in_db.id

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
        for user in chat.users or []:
            await manager.send_personal_message(payload, user)

        return message_response

    except AppError:
        raise
    except Exception:
        logger.exception('Ошибка при отправке сообщения')
        raise AppError(detail='Ошибка сервера')


@router.delete('/{message_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    current_user: UserResponse = Depends(AuthManager.get_current_user),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
):
    await MessageManager.delete(
        session=session, message_id=message_id, user_id=current_user.id
    )
    await session.commit()
