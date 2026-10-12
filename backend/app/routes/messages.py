from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import ChatDAO, MessageDAO
from app.database import get_session
from app.schemas.user import UserResponse
from app.services.auth import get_current_user
from app.services.event_bus import bus
from app.services.files import add_file_to_db
from app.services.messages import build_message_out
from app.services.websocket_manager import manager
from app.utils.files import save_file
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/messages')


@router.get('/{chat_id}')
async def get_chat_messages(
    chat_id: str,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if chat_id.startswith('temp-'):
        return []
    chat_id_int = int(chat_id)

    chat = await ChatDAO.find_one_or_none(session=session, id=chat_id_int)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Чат не найден'
        )

    if current_user.id not in (chat.users or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Доступ запрещен'
        )

    messages_in_db = await MessageDAO.find_all(session=session, chat_id=chat_id_int)

    return [
        await build_message_out(session=session, message=m)
        for m in (messages_in_db or [])
    ]


@router.post('/{chat_id}', status_code=status.HTTP_201_CREATED)
async def send_message(
    chat_id: str,
    message_text: str = Form(default=''),
    file: UploadFile = File(default=None),
    file_name: str = Form(default=''),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        sent_at = datetime.now(UTC)

        # temp-chat -> создание чата
        if chat_id.startswith('temp-'):
            try:
                target_id = int(chat_id.split('-')[1])
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Неверный формат ID чата',
                )
            chat = await ChatDAO.add(
                session=session, users=[current_user.id, target_id]
            )
            chat_id = chat.id
            logger.info(
                'Уведомление о новом чате с ID: %s пользователя: %s', chat_id, target_id
            )
            await manager.send_personal_message(
                {'type': 'new_chat', 'message': chat.to_dict()}, target_id
            )
            await bus.publish(target_id, {'type': 'new_chat', 'chat_id': chat_id})
        else:
            try:
                chat_id = int(chat_id)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Неверный формат ID чата',
                )

        chat = await ChatDAO.find_one_or_none(session, id=chat_id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Чат не найден'
            )
        if current_user.id not in (chat.users or []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail='Доступ запрещен'
            )

        # файл
        file_id = None
        if file:
            if file.size and file.size > 10 * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail='Файл слишком большой',
                )

            file_content = await file.read()
            success = await save_file(chat_id, file_name, file_content)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Ошибка при сохранении файла',
                )

            file_id = await add_file_to_db(
                chat_id=chat_id,
                file_name=file_name,
                owner_id=current_user.id,
                original_name=file.filename or file_name,
                mime_types=file.content_type or 'application/octet-stream',
                size_bytes=len(file_content),
                session=session,
            )
        if message_text and len(message_text) > 10000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Сообщение слишком длинное',
            )

        message = await MessageDAO.add(
            session=session,
            chat_id=chat_id,
            sender_id=current_user.id,
            message_text=message_text,
            message_file_id=file_id,
            sent_at=sent_at,
        )

        message_out = await build_message_out(session=session, message=message)

        for user in chat.users or []:
            if user != current_user.id:
                await manager.send_personal_message(
                    {
                        'type': 'new_message',
                        'message': message_out.model_dump(mode='json'),
                    },
                    user,
                )
                await bus.publish(
                    user,
                    {
                        'type': 'new_message',
                        'chat_id': chat_id,
                        'message_id': message.id,
                    },
                )

        return {'status': 'ok', 'message': message_out}

    except HTTPException:
        raise
    except Exception:
        logger.exception('Ошибка при отправке сообщения')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Ошибка сервера'
        )


@router.delete('/{message_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    message = await MessageDAO.find_one_or_none(session=session, id=message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Сообщение не найдено'
        )

    # Удалять может только автор сообщения
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Доступ запрещен'
        )

    # Дополнительная проверка: пользователь состоит в чате сообщения
    chat = await ChatDAO.find_one_or_none(session=session, id=message.chat_id)
    if not chat or current_user.id not in (chat.users or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Доступ запрещен'
        )

    if not await MessageDAO.soft_delete_message(session=session, message_id=message_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Доступ запрещен'
        )
