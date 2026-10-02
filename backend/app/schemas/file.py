from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileCreate(BaseModel):
    file_path: str = Field(...)


class FileInDb(BaseModel):
    id: int
    file_path: str

    model_config = ConfigDict(from_attributes=True)


class FileMeta(BaseModel):
    id: int
    kind: Literal['image', 'file']
    url: str
    mime_type: str
    filename: str
    size: int | None = None

    model_config = ConfigDict(from_attributes=True)
