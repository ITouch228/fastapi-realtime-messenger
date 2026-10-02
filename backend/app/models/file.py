from sqlalchemy import Column, Integer, String

from .base import Base


class File(Base):
    __tablename__ = 'files'

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String)
