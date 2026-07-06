"""Add archived column to notification_logs

Revision ID: 020
Revises: 019
Create Date: 2026-07-06 12:00:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020_notification_log_archived'
down_revision = '019_notification_async_retry'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notification_logs', sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index(op.f('ix_notification_logs_archived'), 'notification_logs', ['archived'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notification_logs_archived'), table_name='notification_logs')
    op.drop_column('notification_logs', 'archived')