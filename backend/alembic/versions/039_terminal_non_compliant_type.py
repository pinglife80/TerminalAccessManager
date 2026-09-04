"""add terminal non_compliant_type column

Stores the actual non-compliance factor for non_compliant terminals:
- 'ip'   -> only IP is non-compliant
- 'mac'  -> only MAC is non-compliant
- 'both' -> both IP and MAC are non-compliant
- None   -> compliant / bypass / unknown / contradictory edge case

This decouples the frontend non_compliant badge from blacklist coverage
(black_match_type), which misleadingly shows 'BOTH' for almost every blocked
terminal because blocking writes both ip and mac into the blacklist.

Revision ID: 039_terminal_non_compliant_type
Revises: 038_blacklist_unique_ip_firewall
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '039_terminal_non_compliant_type'
down_revision = '038_blacklist_unique_ip_firewall'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('terminals', sa.Column('non_compliant_type', sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column('terminals', 'non_compliant_type')