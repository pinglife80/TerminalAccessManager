from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class DataSource(Base):
    """Data source model for managing external data connections (ARP, Sangfor, etc.)"""

    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # Data source name
    type = Column(String(20), nullable=False)  # arp_ssh / arp_api / sangfor
    tag = Column(String(50), unique=True, nullable=False, index=True)  # Tag identifier
    config = Column(JSON, nullable=False, default={})  # Connection config (JSON)
    enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(20), nullable=True)  # success / failed
    last_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<DataSource(name='{self.name}', type='{self.type}', tag='{self.tag}')>"


class DataSourceBinding(Base):
    """Binding between ARP data source and firewall data source"""

    __tablename__ = "data_source_bindings"

    id = Column(Integer, primary_key=True, index=True)
    arp_source_tag = Column(String(50), nullable=False, index=True)  # ARP data source tag
    firewall_tag = Column(String(50), nullable=False, index=True)  # Firewall tag
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Unique constraint: same ARP source + firewall cannot bind twice
    __table_args__ = (
        UniqueConstraint('arp_source_tag', 'firewall_tag', name='uq_arp_firewall'),
    )

    def __repr__(self):
        return f"<DataSourceBinding(arp='{self.arp_source_tag}', firewall='{self.firewall_tag}')>"
