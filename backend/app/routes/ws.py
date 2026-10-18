import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.database import async_session_maker
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

HEARTBEAT_TIMEOUT = 25


@router.websocket('/{user_id}')
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    session_manager: SessionManager = Depends(get_session_manager),
):
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
        if not await UserManager.get_active(session=session, user_id=user_id):
            await websocket.close(code=4404)
            return

    came_online = await manager.connect(websocket, user_id)
    if came_online:
        async with async_session_maker() as session:
            await notify_online(user_id, session)

    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), HEARTBEAT_TIMEOUT)
            except TimeoutError:
                await websocket.send_json({'type': 'ping'})
    except (WebSocketDisconnect, Exception):
        # TODO: [SMELL] except (WebSocketDisconnect, Exception) — Exception ловит
        # ВСЁ (RuntimeError, OSError, KeyboardInterrupt). Лучше (WebSocketDisconnect,
        # OSError, ConnectionResetError).
        went_offline = manager.disconnect(websocket, user_id)
        if went_offline:
            async with async_session_maker() as session:
                await notify_offline(user_id, session)
