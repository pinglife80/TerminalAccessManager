"""Make blacklist.ip_address nullable to allow blocking by MAC only

Revision ID: 010_blacklist_ip_nullable
Revises: 009_audit_keyset_index
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '010_blacklist_ip_nullable'
down_revision = '009_audit_keyset_index'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make ip_address nullable to allow blocking by MAC address only
    op.alter_column(
        'blacklist',
        'ip_address',
        existing_type=sa.String(45),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'blacklist',
        'ip_address',
        existing_type=sa.String(45),
        nullable=False,
    )
