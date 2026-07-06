"""Add priority column to notification_rules

Revision ID: 022
Revises: 021
Create Date: 2026-07-06 12:10:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '022_notification_rule_priority'
down_revision = '021_notification_template_priority'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notification_rules', sa.Column('priority', sa.Integer(), nullable=False, server_default='100'))


def downgrade() -> None:
    op.drop_column('notification_rules', 'priority')