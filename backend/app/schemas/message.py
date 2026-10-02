from fastapi import File as FastAPI_File
from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, EmailStr

from app.schemas.file import FileMeta


class MessageBase(BaseModel):
    email: EmailStr


class MessageCreate(BaseModel):
    chat_id: str
    message_text: str | None
    file: UploadFile = FastAPI_File(default=None)
    file_name: str | None


class MessageInDb(BaseModel):
    id: int
    chat_id: int
    user_from_id: int
    message_text: str | None
    message_file_id: int | None
    time: str

    model_config = ConfigDict(from_attributes=True)


class MessageOut(MessageInDb):
    file: FileMeta | None = None

    model_config = ConfigDict(from_attributes=True)
