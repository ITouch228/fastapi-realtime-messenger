"""unique index on chat users pair

Revision ID: 06_add_chat_users_unique_index
Revises: 05_add_user_last_seen
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '06_add_chat_users_unique_index'
down_revision: Union[str, None] = '05_add_user_last_seen'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Уникальность пары пользователей без потери существующих чатов.

    PostgreSQL поддерживает сравнение массивов integer[] через B-tree.
    Перед созданием индекса останавливаем миграцию, если уже есть дубликаты:
    автоматическое DELETE приводило к потере сообщений по ON DELETE CASCADE.
    """
    duplicates = op.get_bind().execute(
        sa.text('SELECT 1 FROM chats GROUP BY users HAVING count(*) > 1 LIMIT 1')
    ).scalar()
    if duplicates:
        raise RuntimeError(
            'Найдены дубли чатов: сначала объедините их сообщения вручную.'
        )
    op.create_index('ix_chats_users_unique', 'chats', ['users'], unique=True)


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_chats_users_unique')
