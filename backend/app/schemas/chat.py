from pydantic import BaseModel, ConfigDict, EmailStr


class ChatBase(BaseModel):
    email: EmailStr


class ChatInDb(BaseModel):
    id: int
    users: list[int]

    model_config = ConfigDict(from_attributes=True)
