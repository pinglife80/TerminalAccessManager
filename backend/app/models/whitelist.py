from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class Whitelist(Base):
    """Whitelist model for approved terminals (MAC + IP patterns)"""

    __tablename__ = "whitelist"
    __table_args__ = (
        UniqueConstraint('ip_pattern', 'pattern_type', 'mac_address_normalized', name='uq_whitelist_pattern'),
    )

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(17), unique=False, nullable=True, index=True)
    mac_address_normalized = Column(String(12), nullable=True, index=True)
    ip_pattern = Column(String(100), nullable=True, index=True)  # IP, CIDR, or IP range pattern
    pattern_type = Column(String(20), default="single_ip")  # single_ip / cidr / ip_range / mac_only / both
    comments = Column(Text, nullable=True)
    added_by = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    def __repr__(self):
        return f"<Whitelist(mac='{self.mac_address}', ip_pattern='{self.ip_pattern}')>"
