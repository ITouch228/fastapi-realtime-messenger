from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import BaseDBSchema
from app.schemas.file import FileResponse


class MessageInDb(BaseDBSchema):
    chat_id: int
    sender_id: int
    message_text: str | None
    message_file_id: int | None
    sent_at: datetime
    is_deleted: bool

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(MessageInDb):
    file: FileResponse | None = None
