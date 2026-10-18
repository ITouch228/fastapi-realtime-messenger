"""add users.last_seen_at

Revision ID: 05_add_user_last_seen
Revises: 04_rename_time_to_sent_at
Create Date: 2026-10-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, DateTime

# revision identifiers, used by Alembic.
revision: str = '05_add_user_last_seen'
down_revision: Union[str, None] = '04_rename_time_to_sent_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        Column('last_seen_at', DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'last_seen_at')
