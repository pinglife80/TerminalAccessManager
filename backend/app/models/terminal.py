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
    updated_at = Column(DateTime(timezone=True), nullable=True, index=True)
    source = Column(String(50), default="arp")  # arp, ipguard, whitelist, manual
    source_tag = Column(String(50), nullable=True, index=True)  # Data source tag
    compliance_status = Column(String(20), default="unknown", index=True)  # compliant / bypass / non_compliant / unknown
    wl_match_type = Column(String(10), nullable=True)  # "mac" / "ip" / "both" / null (whitelist match type)
    firewall_tag = Column(String(50), nullable=True, index=True)  # Firewall tag from block operation
    non_compliant_confirm_count = Column(Integer, default=0)  # Consecutive non_compliant detections during compliant/bypass/unknown→non_compliant transition
    compliant_confirm_count = Column(Integer, default=0)  # Consecutive compliant/bypass detections during non_compliant→compliant transition
    ip_changed_at = Column(DateTime(timezone=True), nullable=True)  # Timestamp of last IP change (for grace period)
    block_state = Column(String(30), nullable=True, index=True)
    # None          -> 正常（已封锁 或 不适用）
    # 'no_firewall' -> non_compliant 且 ARP 源无绑定防火墙（不可封锁）
    # 'block_failed'-> non_compliant 且封锁失败（可恢复，等待 retry-block）
    non_compliant_type = Column(String(10), nullable=True)  # "ip" / "mac" / "both" / null（真实不合规因素）

    # Composite index for efficient queries
    # One record per MAC address (network interface); IP is an updatable attribute
    __table_args__ = (
        UniqueConstraint('mac_address_normalized', name='uq_terminal_mac'),
        Index('idx_mac_timestamp', 'mac_address', 'timestamp'),
        Index('idx_ip_status', 'ip_address', 'status'),
    )

    def __repr__(self):
        return f"<Terminal(ip='{self.ip_address}', mac='{self.mac_address}', status='{self.status}')>"
