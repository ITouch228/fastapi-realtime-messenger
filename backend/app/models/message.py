from sqlalchemy import Column, Integer, String

from .base import Base


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer)
    user_from_id = Column(Integer)
    message_text = Column(String, nullable=True)
    message_file_id = Column(Integer, nullable=True)
    time = Column(String)

    def dict(self):
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'user_from_id': self.user_from_id,
            'message_text': self.message_text,
            'message_file_id': self.message_file_id,
            'time': self.time,
        }
