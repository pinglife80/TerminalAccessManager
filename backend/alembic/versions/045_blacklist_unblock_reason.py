"""add unblock_reason to blacklist

Separates the unblock reason from the block reason. Previously the single
``reason`` column was overwritten with the unblock reason when an entry was
unblocked, destroying the original block reason. This adds a dedicated column
so ``reason`` stays the immutable block reason.

Revision ID: 045_blacklist_unblock_reason
Revises: 044_terminal_device_grouping
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '045_blacklist_unblock_reason'
down_revision = '044_terminal_device_grouping'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('blacklist', sa.Column('unblock_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('blacklist', 'unblock_reason')