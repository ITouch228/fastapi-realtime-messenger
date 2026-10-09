from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class File(Base):
    __tablename__ = 'files'

    file_path: Mapped[str] = mapped_column(String(512), index=True)
