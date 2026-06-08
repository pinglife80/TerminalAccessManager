"""rename mac_addresses to terminals, add compliance_baselines table, migrate ipguard data

Revision ID: 002_terminal_baseline
Revises: 001_datasource_compliance
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = '002_terminal_baseline'
down_revision = '001_datasource_compliance'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename mac_addresses table to terminals
    op.rename_table('mac_addresses', 'terminals')

    # Rename indexes (PostgreSQL auto-renames with table, but explicit is safer)
    # Drop old indexes and recreate with new names
    op.drop_index('ix_mac_addresses_source_tag', table_name='terminals')
    op.drop_index('ix_mac_addresses_compliance_status', table_name='terminals')
    op.create_index('ix_terminals_source_tag', 'terminals', ['source_tag'])
    op.create_index('ix_terminals_compliance_status', 'terminals', ['compliance_status'])

    # 2. Add wl_match_type column to terminals
    op.add_column('terminals', sa.Column('wl_match_type', sa.String(10), nullable=True))

    # 3. Create compliance_baselines table
    op.create_table(
        'compliance_baselines',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('tag', sa.String(50), unique=True, nullable=False),
        sa.Column('config', JSON, nullable=False, server_default='{}'),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_status', sa.String(20), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_compliance_baselines_id', 'compliance_baselines', ['id'])
    op.create_index('ix_compliance_baselines_tag', 'compliance_baselines', ['tag'])

    # 4. Migrate ipguard data_sources to compliance_baselines
    op.execute("""
        INSERT INTO compliance_baselines (name, type, tag, config, enabled, last_sync_at, last_sync_status, last_sync_error, created_at, updated_at)
        SELECT name, type, tag, config, enabled, last_sync_at, last_sync_status, last_sync_error, created_at, updated_at
        FROM data_sources
        WHERE type = 'ipguard'
    """)

    # 5. Delete ipguard entries from data_sources
    op.execute("DELETE FROM data_sources WHERE type = 'ipguard'")


def downgrade() -> None:
    # 5. Restore ipguard entries to data_sources
    op.execute("""
        INSERT INTO data_sources (name, type, tag, config, enabled, last_sync_at, last_sync_status, last_sync_error, created_at, updated_at)
        SELECT name, type, tag, config, enabled, last_sync_at, last_sync_status, last_sync_error, created_at, updated_at
        FROM compliance_baselines
        WHERE type = 'ipguard'
    """)

    # 4. Drop compliance_baselines table
    op.drop_index('ix_compliance_baselines_tag', table_name='compliance_baselines')
    op.drop_index('ix_compliance_baselines_id', table_name='compliance_baselines')
    op.drop_table('compliance_baselines')

    # 3. Remove wl_match_type column from terminals
    op.drop_column('terminals', 'wl_match_type')

    # 1. Rename terminals table back to mac_addresses
    op.drop_index('ix_terminals_compliance_status', table_name='terminals')
    op.drop_index('ix_terminals_source_tag', table_name='terminals')
    op.rename_table('terminals', 'mac_addresses')
    op.create_index('ix_mac_addresses_source_tag', 'mac_addresses', ['source_tag'])
    op.create_index('ix_mac_addresses_compliance_status', 'mac_addresses', ['compliance_status'])
