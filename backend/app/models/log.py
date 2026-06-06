from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.core.database import Base


class AuditLog(Base):
    """Audit log model for tracking user actions"""
    
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)  # mac, whitelist, blacklist
    resource_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationship
    user_rel = relationship("User", back_populates="audit_logs")
    
    # Index for efficient queries
    __table_args__ = (
        Index('idx_audit_user_timestamp', 'username', 'timestamp'),
        Index('idx_audit_action', 'action'),
    )
    
    def __repr__(self):
        return f"<AuditLog(user='{self.username}', action='{self.action}')>"
