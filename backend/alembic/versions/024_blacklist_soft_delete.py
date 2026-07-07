"""Add soft delete fields to blacklist table

Revision ID: 024_blacklist_soft_delete
Revises: 023_backup_config_table
Create Date: 2026-07-07 21:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024_blacklist_soft_delete'
down_revision = '023_backup_config_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unblocked_at and unblocked_by columns for soft delete
    op.add_column('blacklist', sa.Column('unblocked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('blacklist', sa.Column('unblocked_by', sa.String(length=50), nullable=True))
    
    # Create index for efficient queries
    op.create_index('idx_blacklist_unblocked', 'blacklist', ['unblocked_at'])


def downgrade() -> None:
    # Remove index and columns
    op.drop_index('idx_blacklist_unblocked', table_name='blacklist')
    op.drop_column('blacklist', 'unblocked_by')
    op.drop_column('blacklist', 'unblocked_at')