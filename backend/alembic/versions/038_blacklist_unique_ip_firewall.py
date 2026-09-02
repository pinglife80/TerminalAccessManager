"""unify blacklist active unique key to (ip_address, firewall_tag)

The firewall (Sangfor AF) blocks by IP only and is idempotent by IP, so the
database must mirror a single active entry per (ip_address, firewall_tag).
The previous unique index on (ip_address, mac_address_normalized, firewall_tag)
let DHCP-reused IPs accumulate multiple active rows (one per MAC), inflating
row counts vs firewall state and feeding block/unblock oscillation.

This migration:
- dedups existing active rows per (ip, firewall_tag), keeping the latest
- drops the old unique index
- creates a new unique index on (ip_address, firewall_tag)

Revision ID: 038_blacklist_unique_ip_firewall
Revises: 037_terminal_block_state
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa
from datetime import UTC, datetime


# revision identifiers, used by Alembic.
revision = '038_blacklist_unique_ip_firewall'
down_revision = '037_terminal_block_state'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)

    # 1. Dedup active rows per (ip_address, firewall_tag): keep latest, mark older unblocked
    result = conn.execute(
        sa.text("""
            WITH duplicates AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY ip_address, firewall_tag
                           ORDER BY blocked_at DESC, id DESC
                       ) as rn
                FROM blacklist
                WHERE unblocked_at IS NULL
                  AND auto_unblocked = false
                  AND firewall_tag IS NOT NULL
            )
            UPDATE blacklist
            SET auto_unblocked = true,
                unblocked_at = :now,
                unblocked_by = 'migration',
                reason = reason || ' [migration: duplicate IP+firewall entry]'
            WHERE id IN (SELECT id FROM duplicates WHERE rn > 1)
        """),
        {"now": now}
    )
    print(f"Marked {result.rowcount} duplicate entries as unblocked (kept latest per IP+firewall)")

    # 2. Drop old unique index
    op.execute("DROP INDEX IF EXISTS idx_blacklist_unique_active")

    # 3. Create new unique index on (ip_address, firewall_tag)
    op.execute("""
        CREATE UNIQUE INDEX idx_blacklist_unique_active
        ON blacklist (ip_address, firewall_tag)
        WHERE unblocked_at IS NULL AND auto_unblocked = false
    """)
    print("Created new unique index idx_blacklist_unique_active (ip, firewall_tag)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_blacklist_unique_active")
    op.execute("""
        CREATE UNIQUE INDEX idx_blacklist_unique_active
        ON blacklist (ip_address, mac_address_normalized, firewall_tag)
        WHERE unblocked_at IS NULL AND auto_unblocked = false
    """)