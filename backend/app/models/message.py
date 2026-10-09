from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    __tablename__ = 'messages'

    message_text: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    chat_id: Mapped[int] = mapped_column(
        ForeignKey('chats.id', ondelete='CASCADE'), index=True
    )
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    message_file_id: Mapped[int | None] = mapped_column(
        ForeignKey('files.id'), nullable=True, index=True
    )
