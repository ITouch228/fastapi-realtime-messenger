"""rename messages.time to sent_at

Revision ID: 04_rename_time_to_sent_at
Revises: 03_add_missing_columns
Create Date: 2026-10-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '04_rename_time_to_sent_at'
down_revision: Union[str, None] = '03_add_missing_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_messages_time', table_name='messages')
    op.alter_column('messages', 'time', new_column_name='sent_at')
    op.create_index('ix_messages_sent_at', 'messages', ['sent_at'])


def downgrade() -> None:
    op.drop_index('ix_messages_sent_at', table_name='messages')
    op.alter_column('messages', 'sent_at', new_column_name='time')
    op.create_index('ix_messages_time', 'messages', ['time'])
