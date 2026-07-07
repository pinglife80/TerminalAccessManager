"""Add updated_at column to terminal table

Revision ID: 025_terminal_updated_at
Revises: 024_blacklist_soft_delete
Create Date: 2026-07-07

"""

from alembic import op
import sqlalchemy as sa

revision = '025_terminal_updated_at'
down_revision = '024_blacklist_soft_delete'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('terminals', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('idx_terminal_updated_at', 'terminals', ['updated_at'])


def downgrade() -> None:
    op.drop_index('idx_terminal_updated_at', table_name='terminals')
    op.drop_column('terminals', 'updated_at')