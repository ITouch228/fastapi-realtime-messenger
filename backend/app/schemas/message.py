from datetime import datetime

from fastapi import File as FastAPI_File
from fastapi import UploadFile
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.file import FileMeta


class MessageCreate(BaseModel):
    chat_id: str
    message_text: str | None
    file: UploadFile = FastAPI_File(default=None)
    file_name: str | None


class MessageInDb(BaseModel):
    id: int
    chat_id: int
    sender_id: int = Field(validation_alias=AliasChoices('sender_id', 'user_from_id'))
    message_text: str | None
    message_file_id: int | None
    time: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageOut(MessageInDb):
    file: FileMeta | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
