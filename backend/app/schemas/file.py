from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.base import BaseDBSchema, IDMixin


class FileInDb(BaseDBSchema):
    file_path: str
    owner_id: int
    original_name: str
    mime_type: str
    size_bytes: int

    model_config = ConfigDict(from_attributes=True)


class FileResponse(IDMixin, BaseModel):
    kind: Literal['image', 'file']
    url: str
    mime_type: str
    filename: str
    size: int | None = None

    model_config = ConfigDict(from_attributes=True)
