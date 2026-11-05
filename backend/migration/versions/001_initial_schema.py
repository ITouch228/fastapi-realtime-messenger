"""Единая начальная схема ITMessage для новой PostgreSQL.

Revision ID: 001_initial_schema
Revises:
Миграция рассчитана только на пустую БД; старые Alembic revisions не поддерживаются.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('username', sa.String(64), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    op.create_table(
        'chats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('users', postgresql.ARRAY(sa.Integer()), nullable=False),
        *_timestamps(),
    )
    op.create_index('ix_chats_users_gin', 'chats', ['users'], postgresql_using='gin')
    op.create_index('ix_chats_users_unique', 'chats', ['users'], unique=True)

    op.create_table(
        'files',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('file_path', sa.String(512), nullable=False, unique=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(127), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        *_timestamps(),
    )
    op.create_index('ix_files_owner_id', 'files', ['owner_id'])

    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('message_text', sa.String(4096), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('chat_id', sa.Integer(), sa.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message_file_id', sa.Integer(), sa.ForeignKey('files.id', ondelete='SET NULL'), nullable=True),
        *_timestamps(),
    )
    op.create_index('ix_messages_sent_at', 'messages', ['sent_at'])
    op.create_index('ix_messages_chat_id', 'messages', ['chat_id'])
    op.create_index('ix_messages_sender_id', 'messages', ['sender_id'])
    op.create_index('ix_messages_message_file_id', 'messages', ['message_file_id'])

    op.create_table(
        'file_cleanup_tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('file_path', sa.String(512), nullable=False, unique=True),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table('file_cleanup_tasks')
    op.drop_table('messages')
    op.drop_table('files')
    op.drop_table('chats')
    op.drop_table('users')
