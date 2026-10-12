from typing import Literal

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    status: Literal['ok'] = 'ok'
