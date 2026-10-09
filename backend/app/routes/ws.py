from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dao.dao import UserDAO
from app.database import async_session_maker
from app.services.auth import verify_token
from app.services.session_manager import SessionManager, get_session_manager
from app.services.websocket_manager import manager
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix='/ws')


@router.websocket('/{user_id}')
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    session_manager: SessionManager = Depends(get_session_manager),
):
    token = websocket.cookies.get('access')
    # sub токена хранит session_id, user_id резолвим по значению ключа в Redis
    session_id = verify_token(token, 'access') if token else None
    if not session_id or await session_manager.get_user_id(session_id) != user_id:
        logger.warning(f'WS auth rejected for user_id={user_id}')
        await websocket.close(code=4401)
        return

    async with async_session_maker() as session:
        if not await UserDAO.find_one_or_none(session, id=user_id):
            await websocket.close(code=4404)
            return

    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
