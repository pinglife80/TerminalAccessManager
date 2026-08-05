from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from app.core.database import Base


class Blacklist(Base):
    """Blacklist model for blocked IP/MAC addresses"""

    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=True, index=True)
    mac_address = Column(String(17), nullable=True, index=True)
    mac_address_normalized = Column(String(12), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    blocked_by = Column(String(50), nullable=False)
    source_tag = Column(String(50), nullable=True, index=True)  # ARP data source tag
    firewall_tag = Column(String(50), nullable=True, index=True)  # Firewall tag
    is_auto_blocked = Column(Boolean, default=False)  # Auto-blocked by compliance check
    auto_unblocked = Column(Boolean, default=False)  # Auto-unblocked after becoming compliant
    unblocked_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Timestamp when unblocked
    unblocked_by = Column(String(50), nullable=True)  # User who unblocked

    # Index for efficient queries
    __table_args__ = (
        Index('idx_blacklist_ip', 'ip_address'),
        Index('idx_blacklist_mac', 'mac_address'),
        Index('idx_blacklist_auto', 'is_auto_blocked', 'auto_unblocked'),
        Index('idx_blacklist_unblocked', 'unblocked_at'),
        Index('idx_blacklist_unique_active', 'ip_address', 'mac_address_normalized', unique=True, postgresql_where=(unblocked_at.is_(None) & (auto_unblocked == False))),
    )

    def __repr__(self):
        return f"<Blacklist(ip='{self.ip_address}', mac='{self.mac_address}')>"
