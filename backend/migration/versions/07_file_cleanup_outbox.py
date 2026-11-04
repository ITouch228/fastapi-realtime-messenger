"""Persistent file cleanup outbox.

Revision ID: 07_file_cleanup_outbox
Revises: 06_add_chat_users_unique_index
"""

from alembic import op
import sqlalchemy as sa

revision = '07_file_cleanup_outbox'
down_revision = '06_add_chat_users_unique_index'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'file_cleanup_tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('file_path'),
    )


def downgrade() -> None:
    op.drop_table('file_cleanup_tasks')
