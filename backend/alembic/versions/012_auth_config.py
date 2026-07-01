"""Add auth_config table for authentication provider configurations

Revision ID: 012_auth_config
Revises: 011_notification_tables
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '012_auth_config'
down_revision = '011_notification_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create auth_config table
    op.create_table(
        'auth_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True, default=True),
        sa.Column('priority', sa.Integer(), nullable=True, default=100),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )


def downgrade() -> None:
    # Drop auth_config table
    op.drop_table('auth_config')
