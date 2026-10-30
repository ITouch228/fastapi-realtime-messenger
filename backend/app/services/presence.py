from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao import ChatDAO
from app.services.users import UserManager
from app.services.websocket_manager import manager


async def _online_peers(user_id: int, session: AsyncSession) -> list[int]:
    """Собеседники пользователя, у которых есть активное WS-соединение.

    Сначала снимок подключений из памяти, потом БД: если локально нет ни
    одного клиента, SELECT по чатам не выполняется вовсе. Порядок важен —
    онлайн-множество обычно сильно меньше числа собеседников.
    """
    online = await manager.online_user_ids()
    if not online:
        return []

    peers = await ChatDAO.get_peers(session=session, user_id=user_id)
    return [peer_id for peer_id in peers if peer_id in online]


async def notify_online(user_id: int, session: AsyncSession) -> None:
    """Разослать собеседникам статус «пользователь появился в сети»."""
    targets = await _online_peers(user_id, session)
    if not targets:
        return

    await manager.send_to_users(
        {'type': 'presence_update', 'user_id': user_id, 'online': True},
        targets,
    )


async def notify_offline(user_id: int, session: AsyncSession) -> None:
    """Обновить last_seen_at и разослать статус «пользователь ушёл в сеть».

    Порядок: прочитать адресатов → записать last_seen и закоммитить →
    разослать. Так клиенты получают событие только по уже зафиксированным
    данным (обновлённый last_seen виден в следующем GET /api/chats), а не
    по транзакции, которая ещё может откатиться.
    """
    last_seen = datetime.now(UTC)
    targets = await _online_peers(user_id, session)

    await UserManager.set_last_seen(session=session, user_id=user_id, when=last_seen)
    await session.commit()

    if not targets:
        return

    await manager.send_to_users(
        {
            'type': 'presence_update',
            'user_id': user_id,
            'online': False,
            'last_seen': last_seen.isoformat(),
        },
        targets,
    )
