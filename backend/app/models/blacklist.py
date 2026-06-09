from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Index
from datetime import datetime, timedelta, timezone

from app.core.database import Base


class Blacklist(Base):
    """Blacklist model for blocked IP/MAC addresses"""

    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=True, index=True)
    mac_address = Column(String(17), nullable=True, index=True)
    mac_address_normalized = Column(String(12), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    blocked_by = Column(String(50), nullable=False)
    source_tag = Column(String(50), nullable=True, index=True)  # ARP data source tag
    firewall_tag = Column(String(50), nullable=True, index=True)  # Firewall tag
    is_auto_blocked = Column(Boolean, default=False)  # Auto-blocked by compliance check
    auto_unblocked = Column(Boolean, default=False)  # Auto-unblocked after becoming compliant

    # Index for efficient queries
    __table_args__ = (
        Index('idx_blacklist_ip', 'ip_address'),
        Index('idx_blacklist_mac', 'mac_address'),
        Index('idx_blacklist_auto', 'is_auto_blocked', 'auto_unblocked'),
    )
    
    def __repr__(self):
        return f"<Blacklist(ip='{self.ip_address}', mac='{self.mac_address}')>"
