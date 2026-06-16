"""Add composite index for keyset pagination on audit_logs

Revision ID: 009_audit_keyset_index
Revises: 008_audit_resource_name
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '009_audit_keyset_index'
down_revision = '008_audit_resource_name'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for efficient keyset pagination: ORDER BY timestamp DESC, id DESC
    op.create_index(
        'idx_audit_logs_keyset',
        'audit_logs',
        ['timestamp', 'id'],
    )


def downgrade() -> None:
    op.drop_index('idx_audit_logs_keyset', table_name='audit_logs')
