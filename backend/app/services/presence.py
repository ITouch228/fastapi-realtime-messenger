from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao import ChatDAO
from app.services.users import UserManager
from app.services.websocket_manager import manager
from app.utils import get_logger

logger = get_logger(__name__)


async def _send_to_peers(user_id: int, payload: dict, session: AsyncSession) -> None:
    peers = await ChatDAO.get_peers(session=session, user_id=user_id)
    for peer_id in peers:
        if manager.is_online(peer_id):
            await manager.send_personal_message(payload, peer_id)


async def notify_online(user_id: int, session: AsyncSession) -> None:
    await _send_to_peers(
        user_id,
        {'type': 'presence_update', 'user_id': user_id, 'online': True},
        session,
    )


async def notify_offline(user_id: int, session: AsyncSession) -> None:
    last_seen = datetime.now(UTC)
    await UserManager.set_last_seen(session=session, user_id=user_id, when=last_seen)
    await session.commit()

    # TODO: [PERF] notify_offline делает 2 DB-запроса (set_last_seen + commit),
    # затем для каждого peer — send_personal_message (потенциально N запросов).
    # Можно объединить в одну транзакцию.
    await _send_to_peers(
        user_id,
        {
            'type': 'presence_update',
            'user_id': user_id,
            'online': False,
            'last_seen': last_seen.isoformat(),
        },
        session,
    )
