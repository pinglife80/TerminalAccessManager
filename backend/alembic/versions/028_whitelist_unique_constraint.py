"""Add unique constraint to whitelist table

Revision ID: 028_whitelist_unique_constraint
Revises: 027_backup_wl_tz_dt
Create Date: 2026-07-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '028_whitelist_unique_constraint'
down_revision = '027_backup_wl_tz_dt'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_whitelist_pattern',
        'whitelist',
        ['ip_pattern', 'pattern_type', 'mac_address_normalized']
    )


def downgrade() -> None:
    op.drop_constraint('uq_whitelist_pattern', 'whitelist', type_='unique')
