"""Файлы, запланированные к удалению после успешного commit."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FileCleanupTask(Base):
    __tablename__ = 'file_cleanup_tasks'

    file_path: Mapped[str] = mapped_column(String(512), unique=True)
