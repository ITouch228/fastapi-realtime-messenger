from sqlalchemy import Index, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Chat(Base):
    __tablename__ = 'chats'

    users: Mapped[list[int]] = mapped_column(ARRAY(Integer))

    # GIN-индекс для эффективных contains по массиву users
    __table_args__ = (Index('ix_chats_users_gin', 'users', postgresql_using='gin'),)
