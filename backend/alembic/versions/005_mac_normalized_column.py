"""Add mac_address_normalized column for indexed MAC search

Revision ID: 005
Revises: 004
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def _normalize_mac(mac):
    """Normalize MAC address by removing separators and uppercasing"""
    if mac is None:
        return None
    return mac.replace(':', '').replace('-', '').replace('.', '').upper()


def upgrade() -> None:
    # Add mac_address_normalized column to terminals
    op.add_column('terminals', sa.Column('mac_address_normalized', sa.String(12), nullable=True))

    # Add mac_address_normalized column to whitelist
    op.add_column('whitelist', sa.Column('mac_address_normalized', sa.String(12), nullable=True))

    # Add mac_address_normalized column to blacklist
    op.add_column('blacklist', sa.Column('mac_address_normalized', sa.String(12), nullable=True))

    # Backfill existing data using PostgreSQL REPLACE functions
    op.execute("""
        UPDATE terminals
        SET mac_address_normalized = UPPER(REPLACE(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), '.', ''))
        WHERE mac_address IS NOT NULL
    """)

    op.execute("""
        UPDATE whitelist
        SET mac_address_normalized = UPPER(REPLACE(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), '.', ''))
        WHERE mac_address IS NOT NULL
    """)

    op.execute("""
        UPDATE blacklist
        SET mac_address_normalized = UPPER(REPLACE(REPLACE(REPLACE(mac_address, ':', ''), '-', ''), '.', ''))
        WHERE mac_address IS NOT NULL
    """)

    # Create indexes on the normalized column
    op.create_index('ix_terminals_mac_norm', 'terminals', ['mac_address_normalized'])
    op.create_index('ix_whitelist_mac_norm', 'whitelist', ['mac_address_normalized'])
    op.create_index('ix_blacklist_mac_norm', 'blacklist', ['mac_address_normalized'])


def downgrade() -> None:
    op.drop_index('ix_blacklist_mac_norm', table_name='blacklist')
    op.drop_index('ix_whitelist_mac_norm', table_name='whitelist')
    op.drop_index('ix_terminals_mac_norm', table_name='terminals')
    op.drop_column('blacklist', 'mac_address_normalized')
    op.drop_column('whitelist', 'mac_address_normalized')
    op.drop_column('terminals', 'mac_address_normalized')
