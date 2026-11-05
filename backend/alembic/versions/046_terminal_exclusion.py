"""add terminal exclusion rules

Exclusion rules are evaluated before ARP entries are written to the
``terminals`` table. Matching entries never enter the terminal database and
therefore never participate in compliance calculation or statistics.

Revision ID: 046_terminal_exclusion
Revises: 045_blacklist_unblock_reason
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '046_terminal_exclusion'
down_revision = '045_blacklist_unblock_reason'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'terminal_exclusions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ip_pattern', sa.String(length=100), nullable=True),
        sa.Column('ip_pattern_type', sa.String(length=20), nullable=True),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('mac_pattern_type', sa.String(length=20), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_terminal_exclusions_id', 'terminal_exclusions', ['id'], unique=False
    )
    op.create_index(
        'ix_terminal_exclusions_is_active',
        'terminal_exclusions',
        ['is_active'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_terminal_exclusions_is_active', table_name='terminal_exclusions')
    op.drop_index('ix_terminal_exclusions_id', table_name='terminal_exclusions')
    op.drop_table('terminal_exclusions')
