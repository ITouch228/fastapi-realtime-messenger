from sqlalchemy import Index, Integer, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Chat(Base):
    __tablename__ = 'chats'

    users: Mapped[list[int]] = mapped_column(ARRAY(Integer))

    __table_args__ = (
        # GIN-индекс для эффективных contains по массиву users
        Index('ix_chats_users_gin', 'users', postgresql_using='gin'),
        # Unique на пару пользователей: users хранится отсортированным
        # (ChatManager.create пишет sorted(...)), поэтому канонический ключ
        # пары — строка array_to_string(users, ','). Гарантирует одну запись
        # на пару при параллельных POST /chats.
        Index(
            'ix_chats_users_unique',
            func.array_to_string(users, ','),
            unique=True,
        ),
    )
