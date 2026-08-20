"""make mac_address_normalized unique (one record per MAC)

Revision ID: 033_terminal_mac_unique
Revises: 032_mac_prefix_scope_split
Create Date: 2026-08-20

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "033_terminal_mac_unique"
down_revision = "032_mac_prefix_scope_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # Step 1: Deduplicate - keep one record per mac_address_normalized
    # Strategy: prefer blocked records (latest blocked), otherwise latest updated record
    # Create a temp table with the ids to keep
    op.execute("""
        CREATE TEMP TABLE terminals_to_keep AS
        SELECT id FROM (
            SELECT
                id,
                mac_address_normalized,
                status,
                updated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY mac_address_normalized
                    ORDER BY
                        CASE WHEN status = 'blocked' THEN 0 ELSE 1 END,
                        updated_at DESC NULLS LAST,
                        id DESC
                ) as rn
            FROM terminals
            WHERE mac_address_normalized IS NOT NULL
        ) sub
        WHERE rn = 1
    """)

    # Delete duplicate records that are not in the keep set
    op.execute("""
        DELETE FROM terminals
        WHERE mac_address_normalized IS NOT NULL
          AND id NOT IN (SELECT id FROM terminals_to_keep)
    """)

    # Also handle records with NULL mac_address_normalized - these shouldn't exist but clean up if any
    op.execute("""
        DELETE FROM terminals WHERE mac_address_normalized IS NULL
    """)

    # Step 2: Drop old unique constraint
    op.execute("ALTER TABLE terminals DROP CONSTRAINT IF EXISTS uq_terminal_ip_mac")

    # Step 3: Create new unique constraint on mac_address_normalized
    op.execute("ALTER TABLE terminals ADD CONSTRAINT uq_terminal_mac UNIQUE (mac_address_normalized)")

    # Cleanup temp table
    op.execute("DROP TABLE IF EXISTS terminals_to_keep")


def downgrade() -> None:
    # Drop new unique constraint
    op.execute("ALTER TABLE terminals DROP CONSTRAINT IF EXISTS uq_terminal_mac")

    # Re-create old composite unique constraint (note: duplicate (ip, mac) may have been deleted,
    # but going forward new entries would enforce uniqueness again)
    op.execute("ALTER TABLE terminals ADD CONSTRAINT uq_terminal_ip_mac UNIQUE (ip_address, mac_address)")
