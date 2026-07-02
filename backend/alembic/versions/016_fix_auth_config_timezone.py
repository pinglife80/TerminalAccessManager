"""Fix auth_config datetime columns to include timezone

Revision ID: 016_fix_auth_config_timezone
Revises: 015_fix_sync_log_timezone
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = '016_fix_auth_config_timezone'
down_revision = '015_fix_sync_log_timezone'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'auth_config',
        'created_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        'auth_config',
        'updated_at',
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'auth_config',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        nullable=False,
    )
    op.alter_column(
        'auth_config',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        nullable=False,
    )