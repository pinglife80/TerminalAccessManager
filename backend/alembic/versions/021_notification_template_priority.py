"""Add priority column to notification_templates

Revision ID: 021
Revises: 020
Create Date: 2026-07-06 12:05:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notification_templates', sa.Column('priority', sa.Integer(), nullable=False, server_default='100'))


def downgrade() -> None:
    op.drop_column('notification_templates', 'priority')