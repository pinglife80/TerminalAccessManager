"""Create backup_config table

Revision ID: 023_backup_config_table
Revises: 022_notification_rule_priority
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023_backup_config_table'
down_revision = '022_notification_rule_priority'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'backup_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('schedule', sa.String(length=100), nullable=False, server_default='0 2 * * *'),
        sa.Column('retention_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('storage_type', sa.String(length=50), nullable=False, server_default='local'),
        sa.Column('storage_config', sa.JSON(), nullable=True),
        sa.Column('backup_database', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('backup_config', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('backup_logs', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('encrypt_backup', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('backup_config')