"""add terminal compliant_checked_at column

Records the timestamp of the most recent compliant/bypass confirmation for a
terminal. Used by the "recently compliant" grace period guard to prevent an
IPGuard transient miss from immediately counting toward a compliant→non_compliant
downgrade during compliance recalculation.

Revision ID: 042_terminal_compliant_check
Revises: 041_terminal_compliance_check
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '042_terminal_compliant_check'
down_revision = '041_terminal_compliance_check'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('terminals', sa.Column('compliant_checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('terminals', 'compliant_checked_at')