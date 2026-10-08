from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.dao.dao import UserDAO
from app.database import async_session_maker
from app.services.auth import verify_token
from app.services.websocket_manager import manager
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix='/ws')


@router.websocket('/{user_id}')
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    token = websocket.cookies.get('access')
    if not token or verify_token(token, 'access') != user_id:
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
