from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class TerminalExclusion(Base):
    """
    Terminal exclusion rule (ingestion-level policy).

    Terminals matching an active rule are dropped before they are written to
    the ``terminals`` table, so they never take part in compliance calculation,
    auto block/unblock, notifications or statistics.

    ip_pattern_type:
      - 'single_ip': exact IP match, e.g. '192.168.1.10'
      - 'cidr': IP in network, e.g. '192.168.1.0/24'
      - 'ip_range': last-octet range within a /24, e.g. '192.168.1.1-100'
    mac_pattern_type:
      - 'mac': full MAC (6 segments / 12 hex chars)
      - 'mac_prefix': 3-5 segments (6 / 8 / 10 hex chars)

    A rule may define only the IP condition, only the MAC condition, or both
    (AND semantics). Multiple rules are OR'ed.
    """

    __tablename__ = "terminal_exclusions"

    id = Column(Integer, primary_key=True, index=True)
    ip_pattern = Column(String(100), nullable=True)
    ip_pattern_type = Column(String(20), nullable=True)
    mac_address = Column(String(17), nullable=True)
    mac_pattern_type = Column(String(20), nullable=True)
    comments = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        return (
            f"<TerminalExclusion(ip='{self.ip_pattern}', "
            f"mac='{self.mac_address}', active={self.is_active})>"
        )
