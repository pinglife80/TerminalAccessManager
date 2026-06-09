from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime, timezone

from app.core.database import Base


class Whitelist(Base):
    """Whitelist model for approved terminals (MAC + IP patterns)"""

    __tablename__ = "whitelist"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(17), unique=False, nullable=True, index=True)
    ip_pattern = Column(String(100), nullable=True, index=True)  # IP, CIDR, or IP range pattern
    pattern_type = Column(String(20), default="single_ip")  # single_ip / cidr / ip_range / mac_only
    comments = Column(Text, nullable=True)
    added_by = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<Whitelist(mac='{self.mac_address}', ip_pattern='{self.ip_pattern}')>"
