"""add excluded_by_rule flag to terminals

Terminals that match an exclusion rule but are retained (blocked or actively
blacklisted) are flagged so dashboard statistics can filter them out.

Revision ID: 047_terminal_excluded_flag
Revises: 046_terminal_exclusion
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '047_terminal_excluded_flag'
down_revision = '046_terminal_exclusion'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'terminals',
        sa.Column(
            'excluded_by_rule',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        'ix_terminals_excluded_by_rule',
        'terminals',
        ['excluded_by_rule'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_terminals_excluded_by_rule', table_name='terminals')
    op.drop_column('terminals', 'excluded_by_rule')
