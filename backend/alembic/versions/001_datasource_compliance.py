"""add data sources and compliance fields

Revision ID: 001_datasource_compliance
Revises:
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = '001_datasource_compliance'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create data_sources table
    op.create_table(
        'data_sources',
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
    op.create_index('ix_data_sources_id', 'data_sources', ['id'])
    op.create_index('ix_data_sources_tag', 'data_sources', ['tag'])

    # 2. Create data_source_bindings table
    op.create_table(
        'data_source_bindings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('arp_source_tag', sa.String(50), nullable=False),
        sa.Column('firewall_tag', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('arp_source_tag', 'firewall_tag', name='uq_arp_firewall'),
    )
    op.create_index('ix_data_source_bindings_id', 'data_source_bindings', ['id'])
    op.create_index('ix_data_source_bindings_arp_source_tag', 'data_source_bindings', ['arp_source_tag'])
    op.create_index('ix_data_source_bindings_firewall_tag', 'data_source_bindings', ['firewall_tag'])

    # 3. MacAddress: add source_tag and compliance_status columns
    op.add_column('mac_addresses', sa.Column('source_tag', sa.String(50), nullable=True))
    op.add_column('mac_addresses', sa.Column('compliance_status', sa.String(20), server_default='unknown', nullable=True))
    op.create_index('ix_mac_addresses_source_tag', 'mac_addresses', ['source_tag'])
    op.create_index('ix_mac_addresses_compliance_status', 'mac_addresses', ['compliance_status'])

    # 4. Whitelist: rename ip_address to ip_pattern, add pattern_type
    # Rename column ip_address -> ip_pattern
    op.alter_column('whitelist', 'ip_address', new_column_name='ip_pattern')
    # Alter column type to String(100)
    op.alter_column('whitelist', 'ip_pattern', type_=sa.String(100), existing_type=sa.String(45))
    # Add pattern_type column
    op.add_column('whitelist', sa.Column('pattern_type', sa.String(20), server_default='single_ip', nullable=True))

    # 5. Blacklist: add source_tag, firewall_tag, is_auto_blocked, auto_unblocked
    op.add_column('blacklist', sa.Column('source_tag', sa.String(50), nullable=True))
    op.add_column('blacklist', sa.Column('firewall_tag', sa.String(50), nullable=True))
    op.add_column('blacklist', sa.Column('is_auto_blocked', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('blacklist', sa.Column('auto_unblocked', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.create_index('ix_blacklist_source_tag', 'blacklist', ['source_tag'])
    op.create_index('ix_blacklist_firewall_tag', 'blacklist', ['firewall_tag'])
    op.create_index('idx_blacklist_auto', 'blacklist', ['is_auto_blocked', 'auto_unblocked'])


def downgrade() -> None:
    # 5. Blacklist: remove new columns
    op.drop_index('idx_blacklist_auto', table_name='blacklist')
    op.drop_index('ix_blacklist_firewall_tag', table_name='blacklist')
    op.drop_index('ix_blacklist_source_tag', table_name='blacklist')
    op.drop_column('blacklist', 'auto_unblocked')
    op.drop_column('blacklist', 'is_auto_blocked')
    op.drop_column('blacklist', 'firewall_tag')
    op.drop_column('blacklist', 'source_tag')

    # 4. Whitelist: rename ip_pattern back to ip_address, remove pattern_type
    op.drop_column('whitelist', 'pattern_type')
    op.alter_column('whitelist', 'ip_pattern', new_column_name='ip_address')
    op.alter_column('whitelist', 'ip_address', type_=sa.String(45), existing_type=sa.String(100))

    # 3. MacAddress: remove new columns
    op.drop_index('ix_mac_addresses_compliance_status', table_name='mac_addresses')
    op.drop_index('ix_mac_addresses_source_tag', table_name='mac_addresses')
    op.drop_column('mac_addresses', 'compliance_status')
    op.drop_column('mac_addresses', 'source_tag')

    # 2. Drop data_source_bindings table
    op.drop_index('ix_data_source_bindings_firewall_tag', table_name='data_source_bindings')
    op.drop_index('ix_data_source_bindings_arp_source_tag', table_name='data_source_bindings')
    op.drop_index('ix_data_source_bindings_id', table_name='data_source_bindings')
    op.drop_table('data_source_bindings')

    # 1. Drop data_sources table
    op.drop_index('ix_data_sources_tag', table_name='data_sources')
    op.drop_index('ix_data_sources_id', table_name='data_sources')
    op.drop_table('data_sources')
