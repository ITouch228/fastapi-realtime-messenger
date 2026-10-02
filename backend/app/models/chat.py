from sqlalchemy import ARRAY, Column, Integer

from .base import Base


class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True, index=True)
    users: list[int] = Column(ARRAY(Integer))  # type: ignore[assignment]

    def dict(self):
        return {
            'id': self.id,
            'users': self.users,
        }
