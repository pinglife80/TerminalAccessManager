"""Add notification_templates table for message content configuration

Revision ID: 017_notification_templates
Revises: 016_fix_auth_config_timezone
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '017_notification_templates'
down_revision = '016_fix_auth_config_timezone'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notification_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('channel_type', sa.String(50), nullable=False),
        sa.Column('subject_template', sa.Text(), nullable=True),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('event_type', 'channel_type', name='uq_template_event_channel'),
    )

    op.create_index('idx_notification_templates_event_type', 'notification_templates', ['event_type'])
    op.create_index('idx_notification_templates_channel_type', 'notification_templates', ['channel_type'])


def downgrade() -> None:
    op.drop_index('idx_notification_templates_channel_type', table_name='notification_templates')
    op.drop_index('idx_notification_templates_event_type', table_name='notification_templates')
    op.drop_table('notification_templates')
