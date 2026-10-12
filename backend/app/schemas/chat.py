from pydantic import BaseModel, ConfigDict


class ChatInDb(BaseModel):
    id: int

    model_config = ConfigDict(from_attributes=True)
