from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import BaseDBSchema


class ChatInDb(BaseDBSchema):
    users: list[int]

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(ChatInDb):
    last_message: str | None = None
    last_message_sent_at: datetime | None = None
    peer_online: bool = False
    peer_last_seen: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
