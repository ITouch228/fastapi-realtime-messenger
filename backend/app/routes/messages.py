from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.dao import ChatDAO, MessageDAO
from app.database import get_session
from app.schemas.user import UserInDB
from app.services.auth import get_current_user
from app.services.event_bus import bus
from app.services.files import add_file_to_db, save_file
from app.services.messages import build_message_out
from app.services.websocket_manager import manager
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/messages')


@router.post('/send_message')
async def send_message(
    chat_id: str | int = Form(...),
    message_text: str = Form(default=''),
    file: UploadFile = File(default=None),
    file_name: str = Form(default=''),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        # temp-chat -> создание чата
        if chat_id.startswith('temp-'):
            try:
                target_id = int(chat_id.split('-')[1])
            except ValueError:
                raise HTTPException(status_code=400, detail='Invalid chat ID format')
            chat = await ChatDAO.add(
                session=session, users=[current_user.id, target_id]
            )
            chat_id = chat.id
            logger.info(
                f'Notify user {target_id} with message: new_chat - {chat.dict()}'
            )
            await manager.send_personal_message(
                {'type': 'new_chat', 'message': chat.dict()}, target_id
            )
            await bus.publish(target_id, {'type': 'new_chat', 'chat_id': chat_id})
        else:
            try:
                chat_id = int(chat_id)
            except ValueError:
                raise HTTPException(status_code=400, detail='Invalid chat ID format')

        chat = await ChatDAO.find_one_or_none(session, id=chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail='Chat not found')
        if current_user.id not in (chat.users or []):
            raise HTTPException(status_code=403, detail='Forbidden')

        # файл
        file_id = None
        if file:
            if file.size and file.size > 10 * 1024 * 1024:
                raise HTTPException(status_code=413, detail='File too large')

            file_content = await file.read()
            success = await save_file(chat_id, file_name, file_content)
            if not success:
                raise HTTPException(status_code=500, detail='File save failed')

            file_id = await add_file_to_db(chat_id, file_name, session)

        if message_text and len(message_text) > 10000:
            raise HTTPException(status_code=400, detail='Message too long')

        # Сохранение сообщения
        message = await MessageDAO.add(
            session=session,
            chat_id=chat_id,
            user_from_id=current_user.id,
            message_text=message_text,
            message_file_id=file_id,
            time=datetime.now(UTC).strftime('%Y %m %d %H %M %S'),
        )

        message_out = await build_message_out(session=session, message=message)

        # Отправка уведомления через WebSocket
        for user in chat.users or []:
            if user != current_user.id:
                await manager.send_personal_message(
                    {'type': 'new_message', 'message': message_out.model_dump()},
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

        return {'status': 'success', 'message': message_out}

    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        logger.error(f'Message send error: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.delete('/delete_message')
async def delete_message(
    message_id: int,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    message = await MessageDAO.find_one_or_none(session=session, id=message_id)
    if not message:
        raise HTTPException(status_code=404, detail='Message not found')

    # Удалять может только автор сообщения
    if message.user_from_id != current_user.id:
        raise HTTPException(status_code=403, detail='Forbidden')

    # Дополнительная проверка: пользователь состоит в чате сообщения
    chat = await ChatDAO.find_one_or_none(session=session, id=message.chat_id)
    if not chat or current_user.id not in (chat.users or []):
        raise HTTPException(status_code=403, detail='Forbidden')

    if await MessageDAO.delete_message(session=session, message_id=message_id):
        return {'status': 'ok'}
    return {'status': 'denied'}
