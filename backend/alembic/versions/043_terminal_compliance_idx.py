"""add index on terminals.compliance_checked_at

The scheduled first-check query filters by
`compliance_checked_at IS NULL OR compliance_checked_at < cutoff`. When many
terminals remain `unknown`, `compliance_status = 'unknown'` loses selectivity and
the planner degrades to a full sequential scan. Indexing `compliance_checked_at`
lets the planner use a bitmap OR to locate only the rows that need re-checking.

Revision ID: 043_terminal_compliance_idx
Revises: 042_terminal_compliant_check
Create Date: 2026-10-26
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '043_terminal_compliance_idx'
down_revision = '042_terminal_compliant_check'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_terminals_compliance_checked_at',
        'terminals',
        ['compliance_checked_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_terminals_compliance_checked_at', table_name='terminals')