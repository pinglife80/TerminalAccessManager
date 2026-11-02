"""add device grouping columns to terminals

Adds nullable device identity columns so a single physical device (identified
by IPGuard AGENT.ID) can group its wired + wireless ARP records for unified
compliance judgment. All columns are nullable: a terminal without a device
match keeps NULL and falls back to per-NIC behavior.

Revision ID: 044_terminal_device_grouping
Revises: 043_terminal_compliance_idx
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '044_terminal_device_grouping'
down_revision = '043_terminal_compliance_idx'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('terminals', sa.Column('device_id', sa.String(64), nullable=True))
    op.add_column('terminals', sa.Column('device_name', sa.String(255), nullable=True))
    op.add_column('terminals', sa.Column('device_serial', sa.String(255), nullable=True))
    op.create_index('ix_terminals_device_id', 'terminals', ['device_id'])


def downgrade() -> None:
    op.drop_index('ix_terminals_device_id', table_name='terminals')
    op.drop_column('terminals', 'device_serial')
    op.drop_column('terminals', 'device_name')
    op.drop_column('terminals', 'device_id')