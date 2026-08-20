from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class ComplianceScope(Base):
    """
    Compliance calculation scope (policy layer).
    When a terminal's IP/MAC falls within a scope, compliance calculation
    only checks IP address and ignores MAC address.

    scope_type: 'ip_cidr' | 'ip_range' | 'mac_prefix'
    scope_value:
      - ip_cidr: '192.168.0.0/16'
      - ip_range: '192.168.1.1-255'
      - mac_prefix: 'AA:BB:CC'
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
