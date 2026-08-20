"""Create compliance_scope table

Revision ID: 031_compliance_scope
Revises: 030_blacklist_unique_index
Create Date: 2026-08-19 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '031_compliance_scope'
down_revision = '030_blacklist_unique_index'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'compliance_scope',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('scope_type', sa.String(length=20), nullable=False),
        sa.Column('scope_value', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_by', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(op.f('ix_compliance_scope_id'), 'compliance_scope', ['id'], unique=False)
    op.create_index(op.f('ix_compliance_scope_scope_type'), 'compliance_scope', ['scope_type'], unique=False)
    op.create_index(op.f('ix_compliance_scope_scope_value'), 'compliance_scope', ['scope_value'], unique=False)
    op.create_index(op.f('ix_compliance_scope_is_active'), 'compliance_scope', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_compliance_scope_is_active'), table_name='compliance_scope')
    op.drop_index(op.f('ix_compliance_scope_scope_value'), table_name='compliance_scope')
    op.drop_index(op.f('ix_compliance_scope_scope_type'), table_name='compliance_scope')
    op.drop_index(op.f('ix_compliance_scope_id'), table_name='compliance_scope')
    op.drop_table('compliance_scope')
