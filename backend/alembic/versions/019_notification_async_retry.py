"""Add async/retry fields to notification_logs

Revision ID: 019_notification_async_retry
Revises: 018_notification_rules
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa


revision = '019_notification_async_retry'
down_revision = '018_notification_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notification_logs', sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('notification_logs', sa.Column('next_retry_at', sa.DateTime(), nullable=True))
    op.add_column('notification_logs', sa.Column('completed_at', sa.DateTime(), nullable=True))
    op.create_index('ix_notification_logs_next_retry_at', 'notification_logs', ['next_retry_at'])
    op.create_index('ix_notification_logs_status', 'notification_logs', ['status'])


def downgrade() -> None:
    op.drop_index('ix_notification_logs_status', table_name='notification_logs')
    op.drop_index('ix_notification_logs_next_retry_at', table_name='notification_logs')
    op.drop_column('notification_logs', 'completed_at')
    op.drop_column('notification_logs', 'next_retry_at')
    op.drop_column('notification_logs', 'retry_count')
