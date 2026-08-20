"""fix blacklist sync issues and clean up dirty data

- Mark orphaned active entries (no firewall_tag or no mac_address_normalized) as unblocked
- Deduplicate active entries: keep only the latest per (ip, mac_norm, firewall_tag), mark older as unblocked
- Drop old unique index, create new unique index including firewall_tag
- Clean up unblocked entries older than 90 days

Revision ID: 035_blacklist_fix_sync
Revises: 034_compliance_oscillation_fixes
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa
from datetime import UTC, datetime, timedelta


# revision identifiers, used by Alembic.
revision = '035_blacklist_fix_sync'
down_revision = '034_compliance_oscillation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)
    unblocked_cutoff = now - timedelta(days=90)

    # 1. Mark orphaned entries without firewall_tag as unblocked (reconciliation ghost entries)
    result = conn.execute(
        sa.text("""
            UPDATE blacklist
            SET auto_unblocked = true,
                unblocked_at = :now,
                unblocked_by = 'migration',
                reason = reason || ' [migration: orphaned - missing firewall_tag]'
            WHERE unblocked_at IS NULL
              AND auto_unblocked = false
              AND (firewall_tag IS NULL OR firewall_tag = '')
        """),
        {"now": now}
    )
    print(f"Marked {result.rowcount} orphaned entries (no firewall_tag) as unblocked")

    # 2. Mark orphaned entries without mac_address_normalized as unblocked
    result = conn.execute(
        sa.text("""
            UPDATE blacklist
            SET auto_unblocked = true,
                unblocked_at = :now,
                unblocked_by = 'migration',
                reason = reason || ' [migration: orphaned - missing MAC]'
            WHERE unblocked_at IS NULL
              AND auto_unblocked = false
              AND (mac_address_normalized IS NULL OR mac_address_normalized = '')
        """),
        {"now": now}
    )
    print(f"Marked {result.rowcount} orphaned entries (no MAC) as unblocked")

    # 3. Deduplicate: for same (ip, mac_norm, firewall_tag) multiple active entries, keep only the latest (largest id)
    result = conn.execute(
        sa.text("""
            WITH duplicates AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY ip_address, mac_address_normalized, firewall_tag
                           ORDER BY blocked_at DESC, id DESC
                       ) as rn
                FROM blacklist
                WHERE unblocked_at IS NULL
                  AND auto_unblocked = false
                  AND firewall_tag IS NOT NULL
                  AND mac_address_normalized IS NOT NULL
            )
            UPDATE blacklist
            SET auto_unblocked = true,
                unblocked_at = :now,
                unblocked_by = 'migration',
                reason = reason || ' [migration: duplicate entry]'
            WHERE id IN (SELECT id FROM duplicates WHERE rn > 1)
        """),
        {"now": now}
    )
    print(f"Marked {result.rowcount} duplicate entries as unblocked (kept latest per IP+MAC+firewall)")

    # 4. Drop old unique index and create new one including firewall_tag
    op.execute("DROP INDEX IF EXISTS idx_blacklist_unique_active")
    op.execute("""
        CREATE UNIQUE INDEX idx_blacklist_unique_active
        ON blacklist (ip_address, mac_address_normalized, firewall_tag)
        WHERE unblocked_at IS NULL AND auto_unblocked = false
    """)
    print("Created new unique index idx_blacklist_unique_active (ip, mac, firewall_tag)")

    # 5. Clean up old unblocked history (older than 90 days) - hard delete
    result = conn.execute(
        sa.text("""
            DELETE FROM blacklist
            WHERE unblocked_at IS NOT NULL
              AND unblocked_at < :cutoff
        """),
        {"cutoff": unblocked_cutoff}
    )
    print(f"Cleaned up {result.rowcount} unblocked entries older than 90 days")


def downgrade() -> None:
    # Drop new index and restore old index
    op.execute("DROP INDEX IF EXISTS idx_blacklist_unique_active")
    op.execute("""
        CREATE UNIQUE INDEX idx_blacklist_unique_active
        ON blacklist (ip_address, mac_address_normalized)
        WHERE unblocked_at IS NULL AND auto_unblocked = false
    """)
    # Downgrade does not restore data that was marked unblocked or deleted
