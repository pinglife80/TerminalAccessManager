"""add terminal block_state column

Adds block_state to track the actionable/blockable state of non_compliant
terminals, distinguishing 'no_firewall' (unblockable, no bound firewall) from
'block_failed' (firewall exists but block failed, awaiting retry) so they can be
reported separately instead of accumulating as a permanent pending-retry backlog.

Revision ID: 037_terminal_block_state
Revises: 036_blacklist_operation_tracking
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '037_terminal_block_state'
down_revision = '036_blacklist_operation_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('terminals', sa.Column('block_state', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('terminals', 'block_state')