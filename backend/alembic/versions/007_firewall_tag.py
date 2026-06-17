"""Add firewall_tag column to terminals table

Revision ID: 007_firewall_tag
Revises: 006_rbac_tables
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '007_firewall_tag'
down_revision = '006_rbac_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add firewall_tag column to terminals table
    op.add_column('terminals', sa.Column('firewall_tag', sa.String(50), nullable=True))
    # Add index for firewall_tag
    op.create_index('ix_terminals_firewall_tag', 'terminals', ['firewall_tag'])


def downgrade() -> None:
    # Remove index and column
    op.drop_index('ix_terminals_firewall_tag', table_name='terminals')
    op.drop_column('terminals', 'firewall_tag')
