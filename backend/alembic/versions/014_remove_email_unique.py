"""Remove unique constraint from users.email

Revision ID: 014_remove_email_unique
Revises: 013_hashed_password_nullable
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = '014_remove_email_unique'
down_revision = '013_hashed_password_nullable'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('ix_users_email', 'users', type_='unique')


def downgrade() -> None:
    op.create_unique_constraint('ix_users_email', 'users', ['email'])