from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '03_add_missing_columns'
down_revision: Union[str, None] = '45c5351c41f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # messages: is_deleted
    op.add_column('messages', sa.Column('is_deleted', sa.Boolean(),
        nullable=False, server_default=sa.text('false')))

    # files: старые записи не имеют владельца — удаляем их (данные не нужны).
    op.execute('TRUNCATE TABLE files RESTART IDENTITY CASCADE')

    op.add_column('files', sa.Column('owner_id', sa.Integer(), nullable=False))
    op.add_column('files', sa.Column('original_name', sa.String(255),
        nullable=False, server_default=''))
    op.add_column('files', sa.Column('mime_type', sa.String(127),
        nullable=False, server_default='application/octet-stream'))
    op.add_column('files', sa.Column('size_bytes', sa.BigInteger(),
        nullable=False, server_default='0'))
    op.create_index('ix_files_owner_id', 'files', ['owner_id'])
    op.create_foreign_key('fk_files_owner_id_users', 'files', 'users',
        ['owner_id'], ['id'], ondelete='CASCADE')

def downgrade() -> None:
    op.drop_constraint('fk_files_owner_id_users', 'files', type_='foreignkey')
    op.drop_index('ix_files_owner_id', table_name='files')
    op.drop_column('files', 'size_bytes')
    op.drop_column('files', 'mime_type')
    op.drop_column('files', 'original_name')
    op.drop_column('files', 'owner_id')
    op.drop_column('messages', 'is_deleted')