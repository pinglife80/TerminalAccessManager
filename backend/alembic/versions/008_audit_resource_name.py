"""Add resource_name column to audit_logs table

Revision ID: 008_audit_resource_name
Revises: 007_firewall_tag
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '008_audit_resource_name'
down_revision = '007_firewall_tag'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add resource_name column to audit_logs table (nullable for backward compatibility)
    op.add_column('audit_logs', sa.Column('resource_name', sa.String(200), nullable=True))


def downgrade() -> None:
    # Remove resource_name column
    op.drop_column('audit_logs', 'resource_name')
