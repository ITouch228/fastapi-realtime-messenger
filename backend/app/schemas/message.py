from datetime import datetime

from pydantic import AliasChoices, ConfigDict, Field

from app.schemas.base import BaseDBSchema
from app.schemas.file import FileResponse


class MessageInDb(BaseDBSchema):
    chat_id: int
    sender_id: int = Field(validation_alias=AliasChoices('sender_id', 'user_from_id'))
    message_text: str | None
    message_file_id: int | None
    sent_at: datetime
    is_deleted: bool

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageResponse(MessageInDb):
    file: FileResponse | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
