"""Add unique constraint on terminals (ip_address, mac_address)

Revision ID: 004
Revises: 003_search_indexes
Create Date: 2026-06-09

Deduplicates existing (ip_address, mac_address) pairs before adding constraint.
Keeps the most recent record (highest id) for each duplicate pair.
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Deduplicate — keep the latest record (max id) for each (ip_address, mac_address) pair
    op.execute("""
        DELETE FROM terminals
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM terminals
            GROUP BY ip_address, mac_address
        )
    """)

    # Step 2: Add unique constraint
    op.create_unique_constraint('uq_terminal_ip_mac', 'terminals', ['ip_address', 'mac_address'])


def downgrade() -> None:
    op.drop_constraint('uq_terminal_ip_mac', 'terminals', type_='unique')
