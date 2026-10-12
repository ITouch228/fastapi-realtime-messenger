"""
Базовый класс для всех моделей.

Ре-экспорт Base из app.database, чтобы metadata моделей и настройки
движка/сессий опирались на один и тот же DeclarativeBase.
"""

from app.database import Base

__all__ = ['Base']
