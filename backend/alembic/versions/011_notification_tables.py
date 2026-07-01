"""Add notification_channels and notification_logs tables

Revision ID: 011_notification_tables
Revises: 010_blacklist_ip_nullable
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '011_notification_tables'
down_revision = '010_blacklist_ip_nullable'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create notification_channels table
    op.create_table(
        'notification_channels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True, default=True),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Create notification_logs table
    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(100), nullable=False),
        sa.Column('channel_name', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('recipient', sa.String(255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes for notification_logs
    op.create_index('idx_notification_logs_event_id', 'notification_logs', ['event_id'])
    op.create_index('idx_notification_logs_channel', 'notification_logs', ['channel_name'])
    op.create_index('idx_notification_logs_event_type', 'notification_logs', ['event_type'])
    op.create_index('idx_notification_logs_sent_at', 'notification_logs', ['sent_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_notification_logs_sent_at', table_name='notification_logs')
    op.drop_index('idx_notification_logs_event_type', table_name='notification_logs')
    op.drop_index('idx_notification_logs_channel', table_name='notification_logs')
    op.drop_index('idx_notification_logs_event_id', table_name='notification_logs')

    # Drop tables
    op.drop_table('notification_logs')
    op.drop_table('notification_channels')
