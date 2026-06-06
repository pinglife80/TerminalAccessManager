from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from datetime import datetime, timezone

from app.core.database import Base


class MacAddress(Base):
    """MAC Address model for tracking network devices"""
    
    __tablename__ = "mac_addresses"
    
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False, index=True)
    status = Column(String(20), default="unfrozen", index=True)  # unfrozen, frozen
    comments = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    source = Column(String(50), default="arp")  # arp, ipguard
    
    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_mac_timestamp', 'mac_address', 'timestamp'),
        Index('idx_ip_status', 'ip_address', 'status'),
    )
    
    def __repr__(self):
        return f"<MacAddress(ip='{self.ip_address}', mac='{self.mac_address}', status='{self.status}')>"
