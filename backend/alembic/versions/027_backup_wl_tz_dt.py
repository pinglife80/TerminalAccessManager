"""Add backup_whitelist field and timezone-aware datetime

Revision ID: 027_backup_wl_tz_dt
Revises: 026_blacklist_fix_unblocked_at
Create Date: 2026-07-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '027_backup_wl_tz_dt'
down_revision = '026_blacklist_fix_unblocked_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'backup_config',
        sa.Column('backup_whitelist', sa.Boolean(), nullable=False, server_default='true')
    )

    op.alter_column(
        'notification_channels',
        'created_at',
        type_=sa.DateTime(timezone=True),
        nullable=False,
        existing_type=sa.DateTime(),
        postgresql_using='created_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'notification_channels',
        'updated_at',
        type_=sa.DateTime(timezone=True),
        nullable=True,
        existing_type=sa.DateTime(),
        postgresql_using='updated_at AT TIME ZONE \'UTC\''
    )

    op.alter_column(
        'notification_logs',
        'next_retry_at',
        type_=sa.DateTime(timezone=True),
        nullable=True,
        existing_type=sa.DateTime(),
        postgresql_using='next_retry_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'notification_logs',
        'sent_at',
        type_=sa.DateTime(timezone=True),
        nullable=False,
        existing_type=sa.DateTime(),
        postgresql_using='sent_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'notification_logs',
        'completed_at',
        type_=sa.DateTime(timezone=True),
        nullable=True,
        existing_type=sa.DateTime(),
        postgresql_using='completed_at AT TIME ZONE \'UTC\''
    )

    op.alter_column(
        'notification_templates',
        'created_at',
        type_=sa.DateTime(timezone=True),
        nullable=False,
        existing_type=sa.DateTime(),
        postgresql_using='created_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'notification_templates',
        'updated_at',
        type_=sa.DateTime(timezone=True),
        nullable=True,
        existing_type=sa.DateTime(),
        postgresql_using='updated_at AT TIME ZONE \'UTC\''
    )

    op.alter_column(
        'notification_rules',
        'created_at',
        type_=sa.DateTime(timezone=True),
        nullable=False,
        existing_type=sa.DateTime(),
        postgresql_using='created_at AT TIME ZONE \'UTC\''
    )
    op.alter_column(
        'notification_rules',
        'updated_at',
        type_=sa.DateTime(timezone=True),
        nullable=True,
        existing_type=sa.DateTime(),
        postgresql_using='updated_at AT TIME ZONE \'UTC\''
    )


def downgrade() -> None:
    op.drop_column('backup_config', 'backup_whitelist')

    op.alter_column(
        'notification_channels',
        'created_at',
        type_=sa.DateTime(),
        nullable=False,
        existing_type=sa.DateTime(timezone=True)
    )
    op.alter_column(
        'notification_channels',
        'updated_at',
        type_=sa.DateTime(),
        nullable=True,
        existing_type=sa.DateTime(timezone=True)
    )

    op.alter_column(
        'notification_logs',
        'next_retry_at',
        type_=sa.DateTime(),
        nullable=True,
        existing_type=sa.DateTime(timezone=True)
    )
    op.alter_column(
        'notification_logs',
        'sent_at',
        type_=sa.DateTime(),
        nullable=False,
        existing_type=sa.DateTime(timezone=True)
    )
    op.alter_column(
        'notification_logs',
        'completed_at',
        type_=sa.DateTime(),
        nullable=True,
        existing_type=sa.DateTime(timezone=True)
    )

    op.alter_column(
        'notification_templates',
        'created_at',
        type_=sa.DateTime(),
        nullable=False,
        existing_type=sa.DateTime(timezone=True)
    )
    op.alter_column(
        'notification_templates',
        'updated_at',
        type_=sa.DateTime(),
        nullable=True,
        existing_type=sa.DateTime(timezone=True)
    )

    op.alter_column(
        'notification_rules',
        'created_at',
        type_=sa.DateTime(),
        nullable=False,
        existing_type=sa.DateTime(timezone=True)
    )
    op.alter_column(
        'notification_rules',
        'updated_at',
        type_=sa.DateTime(),
        nullable=True,
        existing_type=sa.DateTime(timezone=True)
    )