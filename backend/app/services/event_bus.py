import asyncio
from collections import defaultdict

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, user_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[user_id].add(queue)
        return queue

    def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        self._subscribers[user_id].discard(queue)
        if not self._subscribers[user_id]:
            self._subscribers.pop(user_id, None)

    async def publish(self, user_id: int, payload: dict) -> None:
        for queue in list(self._subscribers.get(user_id, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(f'SSE queue full for user_id={user_id}, dropping event')


bus = EventBus()
