"""split mac_prefix scope type into mac_prefix_arp and mac_prefix_ipguard

Revision ID: 032_mac_prefix_scope_split
Revises: 031_compliance_scope
Create Date: 2026-08-20

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "032_mac_prefix_scope_split"
down_revision = "031_compliance_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migrate existing mac_prefix entries to mac_prefix_arp
    op.execute(
        "UPDATE compliance_scope SET scope_type = 'mac_prefix_arp' WHERE scope_type = 'mac_prefix'"
    )


def downgrade() -> None:
    # Revert mac_prefix_arp back to mac_prefix
    op.execute(
        "UPDATE compliance_scope SET scope_type = 'mac_prefix' WHERE scope_type = 'mac_prefix_arp'"
    )
