import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import async_session_maker
from app.exceptions import NotFoundError, UnauthorizedError
from app.services import (
    SessionManager,
    UserManager,
    get_session_manager,
    manager,
    notify_offline,
    notify_online,
)
from app.utils import get_logger, verify_token

logger = get_logger(__name__)

router = APIRouter(prefix='/ws')


def is_allowed_ws_origin(origin: str | None) -> bool:
    """Разрешать WS только со страниц из явного списка доверенных origins.

    Проверка выполняется до чтения cookie и до обращения к Redis/БД.
    Отсутствующий Origin также отклоняется: браузеры передают его при WS handshake.
    """
    return origin is not None and origin in settings.ALLOWED_ORIGINS


@router.websocket('/{user_id}')
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """WS-соединение пользователя: авторизация по cookie, ping-цикл, presence."""
    if not is_allowed_ws_origin(websocket.headers.get('origin')):
        logger.warning('WS Origin отклонён для пользователя: %s', user_id)
        await websocket.close(code=4403)
        return

    token = websocket.cookies.get('access')
    if not token:
        logger.warning('WS авторизация отклонена для пользователя: %s', user_id)
        await websocket.close(code=4401)
        return
    session_id = verify_token(token, 'access')
    if not session_id or await session_manager.get_user_id(session_id) != user_id:
        logger.warning('WS авторизация отклонена для пользователя: %s', user_id)
        await websocket.close(code=4401)
        return

    async with async_session_maker() as session:
        try:
            await UserManager.get_active(session=session, user_id=user_id)
        except (NotFoundError, UnauthorizedError):
            # В WS нет HTTP exception handlers — перехватываем явно и рвём
            # соединение аккуратным кодом 4404.
            logger.warning(
                'WS отклонён: пользователь недоступен (удалён/деактивирован): %s',
                user_id,
            )
            await websocket.close(code=4404)
            return

    came_online = await manager.connect(websocket, user_id)
    if came_online:
        async with async_session_maker() as session:
            await notify_online(user_id, session)

    try:
        while True:
            try:
                await asyncio.wait_for(
                    websocket.receive_text(), settings.WS_HEARTBEAT_TIMEOUT
                )
            except TimeoutError:
                await websocket.send_json({'type': 'ping'})
    except (WebSocketDisconnect, OSError, RuntimeError) as exc:
        # Штатный обрыв: клиент закрыл вкладку, сеть пропала, сокет уже
        # закрыт (starlette поднимает RuntimeError при send в закрытый сокет)
        logger.info('WS-соединение закрыто: user_id=%s (%s)', user_id, exc)
    except (KeyError, TypeError, AttributeError):
        # Программный баг, а не обрыв связи: пробрасываем наверх (starlette
        # закроет сокет кодом 1011), cleanup в finally выполнится в любом случае.
        logger.critical(
            'Неожиданная ошибка в WS-цикле: user_id=%s', user_id, exc_info=True
        )
        raise
    finally:
        # Отписка обязательна в любом случае, иначе соединение останется в
        # active_connections и пользователь «зависнет» в статусе онлайн
        went_offline = await manager.disconnect(websocket, user_id)
        if went_offline:
            async with async_session_maker() as session:
                await notify_offline(user_id, session)
