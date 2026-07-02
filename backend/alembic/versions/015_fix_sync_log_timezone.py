"""Fix ldap_sync_log datetime columns to include timezone

Revision ID: 015_fix_sync_log_timezone
Revises: 014_remove_email_unique
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = '015_fix_sync_log_timezone'
down_revision = '014_remove_email_unique'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'ldap_sync_log',
        'started_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        'ldap_sync_log',
        'completed_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'ldap_sync_log',
        'started_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        nullable=False,
    )
    op.alter_column(
        'ldap_sync_log',
        'completed_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        nullable=True,
    )