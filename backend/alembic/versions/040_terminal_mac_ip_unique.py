"""terminals: MAC -> MAC+IP composite unique key

Replaces the MAC-only unique constraint (uq_terminal_mac) with a composite
unique constraint on (ip_address, mac_address_normalized) so that one MAC with
multiple IPs (e.g. bridged VMs) can be stored as independent terminal rows.

This also makes mac_address_normalized NOT NULL, since every production code
path (ARP collector, mock-data CLI) always populates it.

Revision ID: 040_terminal_mac_ip_unique
Revises: 039_terminal_non_compliant_type
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '040_terminal_mac_ip_unique'
down_revision = '039_terminal_non_compliant_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop the MAC-only unique constraint (idempotent).
    op.execute("ALTER TABLE terminals DROP CONSTRAINT IF EXISTS uq_terminal_mac")

    # 2. Clean legacy NULL-MAC rows then enforce NOT NULL (no production path
    #    creates a terminal without a normalized MAC).
    op.execute("DELETE FROM terminals WHERE mac_address_normalized IS NULL")
    op.execute("ALTER TABLE terminals ALTER COLUMN mac_address_normalized SET NOT NULL")

    # 3. Add the composite (ip_address, mac_address_normalized) unique constraint.
    op.create_unique_constraint(
        'uq_terminal_mac_ip',
        'terminals',
        ['ip_address', 'mac_address_normalized'],
    )


def downgrade() -> None:
    # Reverting may fail if duplicate MACs exist (a possible result of the
    # multi-IP data written while this constraint was active). This is a
    # best-effort structural rollback.
    op.drop_constraint('uq_terminal_mac_ip', 'terminals', type_='unique')
    op.execute("ALTER TABLE terminals ALTER COLUMN mac_address_normalized DROP NOT NULL")
    op.execute("ALTER TABLE terminals DROP CONSTRAINT IF EXISTS uq_terminal_mac")
    op.create_unique_constraint('uq_terminal_mac', 'terminals', ['mac_address_normalized'])