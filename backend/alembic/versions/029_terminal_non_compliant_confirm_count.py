"""Add non_compliant_confirm_count column to terminals table

Revision ID: 029_terminal_non_compliant_confirm_count
Revises: 028_whitelist_unique_constraint
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '029_terminal_non_compliant_confirm_count'
down_revision = '028_whitelist_unique_constraint'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'terminals',
        sa.Column(
            'non_compliant_confirm_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    op.drop_column('terminals', 'non_compliant_confirm_count')
