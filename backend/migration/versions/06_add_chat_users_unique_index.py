"""unique index on chat users pair

Revision ID: 06_add_chat_users_unique_index
Revises: 05_add_user_last_seen
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '06_add_chat_users_unique_index'
down_revision: Union[str, None] = '05_add_user_last_seen'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # chats.users хранится отсортированным (ChatManager.create пишет sorted(...)),
    # поэтому канонический ключ пары — строка array_to_string(users, ',').
    # PostgreSQL не имеет оператора '=' для ARRAY в operator class, поэтому
    # уникальный индекс строится по текстовому выражению.

    # 1. Дедупликация: оставляем самый старый чат пары, удаляем более новые.
    op.execute(
        """
        DELETE FROM chats a
        USING chats b
        WHERE a.id > b.id
          AND array_to_string(a.users, ',') = array_to_string(b.users, ',')
        """
    )

    # 2. Expression unique index — гарантирует одну запись на пару пользователей.
    op.execute(
        """
        CREATE UNIQUE INDEX ix_chats_users_unique
        ON chats (array_to_string(users, ','))
        """
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_chats_users_unique')
