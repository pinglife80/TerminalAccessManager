"""Make idx_blacklist_unique_active a unique index

Revision ID: 030_blacklist_unique_index
Revises: 029_terminal_non_compliant_confirm_count
Create Date: 2026-08-05 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '030_blacklist_unique_index'
down_revision = '029_terminal_non_compliant_confirm_count'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Remove duplicate active blacklist entries (keep earliest id)
    op.execute("""
        DELETE FROM blacklist a USING blacklist b
        WHERE a.id > b.id
          AND a.ip_address = b.ip_address
          AND a.mac_address_normalized = b.mac_address_normalized
          AND a.auto_unblocked = FALSE
          AND a.unblocked_at IS NULL
          AND b.auto_unblocked = FALSE
          AND b.unblocked_at IS NULL
    """)

    # Step 2: Drop old non-unique index if it exists
    op.execute("""
        DROP INDEX IF EXISTS idx_blacklist_unique_active
    """)

    # Step 3: Create new unique partial index
    op.execute("""
        CREATE UNIQUE INDEX idx_blacklist_unique_active
        ON blacklist (ip_address, mac_address_normalized)
        WHERE unblocked_at IS NULL AND auto_unblocked = FALSE
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_blacklist_unique_active
    """)
    op.execute("""
        CREATE INDEX idx_blacklist_unique_active
        ON blacklist (ip_address, mac_address_normalized)
        WHERE unblocked_at IS NULL AND auto_unblocked = FALSE
    """)