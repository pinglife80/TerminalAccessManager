"""add terminal compliance_checked_at column

Records the timestamp of the most recent non-compliant confirm-count increment
for a terminal. Used by the minimum-interval guard to prevent double-counting
from concurrent/adjacent first-discovery checks within a single sync cycle.

Revision ID: 041_terminal_compliance_check
Revises: 040_terminal_mac_ip_unique
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '041_terminal_compliance_check'
down_revision = '040_terminal_mac_ip_unique'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('terminals', sa.Column('compliance_checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('terminals', 'compliance_checked_at')