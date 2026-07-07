"""Fix historical unblocked_at for auto-unblocked blacklist entries

Revision ID: 026_blacklist_fix_unblocked_at
Revises: 025_terminal_updated_at
Create Date: 2026-07-08 02:30:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '026_blacklist_fix_unblocked_at'
down_revision = '025_terminal_updated_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Set unblocked_at for records that were auto-unblocked but missing the timestamp
    op.execute(
        "UPDATE blacklist SET unblocked_at = blocked_at "
        "WHERE auto_unblocked = true AND unblocked_at IS NULL"
    )
    # Also fix manually unblocked records (unblocked_by set but unblocked_at missing)
    op.execute(
        "UPDATE blacklist SET unblocked_at = blocked_at "
        "WHERE unblocked_by IS NOT NULL AND unblocked_at IS NULL"
    )


def downgrade() -> None:
    # Cannot restore NULL values reliably, no-op
    pass
