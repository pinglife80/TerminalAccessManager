from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class ComplianceBaseline(Base):
    """Compliance baseline model for managing IP Guard and other compliance data sources"""

    __tablename__ = "compliance_baselines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # Baseline name
    type = Column(String(20), nullable=False)  # ipguard (extensible for future types)
    tag = Column(String(50), unique=True, nullable=False, index=True)  # Tag identifier
    config = Column(JSON, nullable=False, default={})  # Connection config (JSON)
    enabled = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String(20), nullable=True)  # success / failed
    last_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ComplianceBaseline(name='{self.name}', type='{self.type}', tag='{self.tag}')>"
