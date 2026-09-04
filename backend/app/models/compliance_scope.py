from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class ComplianceScope(Base):
    """
    Compliance calculation scope (policy layer).
    Controls whether compliance matching uses IP-only or IP+MAC strategy.

    scope_type:
      - 'ip_cidr': Terminal IP in CIDR → IP-only match
      - 'ip_range': Terminal IP in range → IP-only match
      - 'mac_prefix_arp': Terminal MAC matches prefix (ARP source) → IP-only match
      - 'mac_prefix_ipguard': IPGuard baseline MAC matches prefix → IP-only match for that entry
      - 'ip_cidr_any': Terminal IP in CIDR → OR match (IP or MAC, either matches)
      - 'ip_range_any': Terminal IP in range → OR match (IP or MAC, either matches)
      - 'mac_prefix_any': Terminal MAC matches prefix (ARP source) → OR match (IP or MAC, either matches)
    scope_value:
      - ip_cidr / ip_cidr_any: '192.168.0.0/16'
      - ip_range / ip_range_any: '192.168.1.1-255'
      - mac_prefix_arp / mac_prefix_ipguard / mac_prefix_any: 'AA:BB:CC'
    """

    __tablename__ = "compliance_scope"

    id = Column(Integer, primary_key=True, index=True)
    scope_type = Column(String(20), nullable=False, index=True)
    scope_value = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<ComplianceScope(type='{self.scope_type}', value='{self.scope_value}')>"
