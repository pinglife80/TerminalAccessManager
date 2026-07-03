"""Add notification_rules table for suppression/aggregation/escalation

Revision ID: 018_notification_rules
Revises: 017_notification_templates
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '018_notification_rules'
down_revision = '017_notification_templates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notification_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('channel_name', sa.String(100), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('suppress_enabled', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('suppress_window', sa.Integer(), nullable=True, server_default=sa.text('300')),
        sa.Column('escalate_enabled', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('escalate_threshold', sa.Integer(), nullable=True, server_default=sa.text('5')),
        sa.Column('escalate_window', sa.Integer(), nullable=True, server_default=sa.text('3600')),
        sa.Column('escalate_severity', sa.String(20), nullable=True, server_default=sa.text("'error'")),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Regular unique constraint for non-null channel_name pairs
    op.create_index(
        'ix_notification_rules_event_type',
        'notification_rules',
        ['event_type'],
    )
    op.create_index(
        'ix_notification_rules_channel_name',
        'notification_rules',
        ['channel_name'],
    )
    # Partial unique index: only one catch-all rule per event_type when channel_name is NULL
    op.create_index(
        'uq_rule_event_null_channel',
        'notification_rules',
        ['event_type'],
        unique=True,
        postgresql_where=sa.text('channel_name IS NULL'),
    )
    # Partial unique index: unique (event_type, channel_name) when channel_name is NOT NULL
    op.create_index(
        'uq_rule_event_specific_channel',
        'notification_rules',
        ['event_type', 'channel_name'],
        unique=True,
        postgresql_where=sa.text('channel_name IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_rule_event_specific_channel', table_name='notification_rules')
    op.drop_index('uq_rule_event_null_channel', table_name='notification_rules')
    op.drop_index('ix_notification_rules_channel_name', table_name='notification_rules')
    op.drop_index('ix_notification_rules_event_type', table_name='notification_rules')
    op.drop_table('notification_rules')
