"""Make users.hashed_password nullable for LDAP users

Revision ID: 013_hashed_password_nullable
Revises: 012_auth_config
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = '013_hashed_password_nullable'
down_revision = '012_auth_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'users',
        'hashed_password',
        existing_type=sa.String(255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'users',
        'hashed_password',
        existing_type=sa.String(255),
        nullable=False,
    )