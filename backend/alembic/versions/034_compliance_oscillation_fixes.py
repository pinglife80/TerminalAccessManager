"""compliance oscillation prevention: add confirm counts and ip change tracking

Revision ID: 034_compliance_oscillation
Revises: 033_terminal_mac_unique
Create Date: 2026-08-20

Adds:
- compliant_confirm_count: symmetric confirmation counter for returning to compliant
- ip_changed_at: tracks when IP last changed for grace-period handling
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '034_compliance_oscillation'
down_revision = '033_terminal_mac_unique'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add compliant_confirm_count (defaults to 0)
    op.add_column('terminals', sa.Column(
        'compliant_confirm_count', sa.Integer(), nullable=False, server_default='0'
    ))
    # Add ip_changed_at timestamp (nullable)
    op.add_column('terminals', sa.Column(
        'ip_changed_at', sa.DateTime(timezone=True), nullable=True
    ))


def downgrade() -> None:
    op.drop_column('terminals', 'ip_changed_at')
    op.drop_column('terminals', 'compliant_confirm_count')
