import enum
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class TerminalStatus(enum.StrEnum):
    """Terminal status enum - represents firewall block state only.

    Compliance state is tracked separately via compliance_status field.
    """
    BLOCKED = "blocked"      # Device has been blocked on firewall
    UNBLOCKED = "unblocked"  # Device is not blocked (default)


class Terminal(Base):
    """MAC Address model for tracking network devices"""

    __tablename__ = "terminals"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False, index=True)
    mac_address_normalized = Column(String(12), nullable=True, index=True)
    status = Column(
        String(20), default=TerminalStatus.UNBLOCKED.value, index=True
    )  # blocked, unblocked
    comments = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    source = Column(String(50), default="arp")  # arp, ipguard, whitelist, manual
    source_tag = Column(String(50), nullable=True, index=True)  # Data source tag
    compliance_status = Column(String(20), default="unknown", index=True)  # compliant / bypass / non_compliant / unknown
    wl_match_type = Column(String(10), nullable=True)  # "mac" / "ip" / "both" / null (whitelist match type)
    firewall_tag = Column(String(50), nullable=True, index=True)  # Firewall tag from block operation

    # Composite index for efficient queries
    __table_args__ = (
        UniqueConstraint('ip_address', 'mac_address', name='uq_terminal_ip_mac'),
        Index('idx_mac_timestamp', 'mac_address', 'timestamp'),
        Index('idx_ip_status', 'ip_address', 'status'),
    )

    def __repr__(self):
        return f"<Terminal(ip='{self.ip_address}', mac='{self.mac_address}', status='{self.status}')>"
