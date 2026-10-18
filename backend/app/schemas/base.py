from datetime import datetime

from pydantic import BaseModel


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime


class IDMixin(BaseModel):
    id: int


class BaseDBSchema(TimestampMixin, IDMixin):
    pass
