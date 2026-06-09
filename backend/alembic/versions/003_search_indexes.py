"""Add indexes for search optimization

Revision ID: 003
Revises: 002_terminal_baseline
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002_terminal_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_whitelist_created_at', 'whitelist', ['created_at'])
    op.create_index('ix_blacklist_blocked_at', 'blacklist', ['blocked_at'])
    op.create_index('ix_blacklist_expires_at', 'blacklist', ['expires_at'])
    op.create_index('ix_audit_logs_ip_address', 'audit_logs', ['ip_address'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_ip_address', table_name='audit_logs')
    op.drop_index('ix_blacklist_expires_at', table_name='blacklist')
    op.drop_index('ix_blacklist_blocked_at', table_name='blacklist')
    op.drop_index('ix_whitelist_created_at', table_name='whitelist')
