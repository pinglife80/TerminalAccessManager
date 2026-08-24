"""add blacklist operation tracking fields

Add last_operation_type/status/error/at and retry_count to track the latest
block/unblock operation outcome for actionable status display.

Revision ID: 036_blacklist_operation_tracking
Revises: 035_blacklist_fix_sync
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '036_blacklist_operation_tracking'
down_revision = '035_blacklist_fix_sync'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('blacklist', sa.Column('last_operation_type', sa.String(length=20), nullable=True))
    op.add_column('blacklist', sa.Column('last_operation_status', sa.String(length=20), nullable=True))
    op.add_column('blacklist', sa.Column('last_operation_error', sa.Text(), nullable=True))
    op.add_column('blacklist', sa.Column('last_operation_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('blacklist', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('blacklist', 'retry_count')
    op.drop_column('blacklist', 'last_operation_at')
    op.drop_column('blacklist', 'last_operation_error')
    op.drop_column('blacklist', 'last_operation_status')
    op.drop_column('blacklist', 'last_operation_type')