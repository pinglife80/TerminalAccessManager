from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# MAC Address schemas
class MacAddressBase(BaseModel):
    """Base MAC address schema"""
    ip_address: str = Field(..., description="IP address")
    mac_address: str = Field(..., description="MAC address")
    comments: Optional[str] = None


class MacAddressCreate(MacAddressBase):
    """Schema for creating MAC address record"""
    source: Optional[str] = "arp"


class MacAddressUpdate(BaseModel):
    """Schema for updating MAC address"""
    status: Optional[str] = None
    comments: Optional[str] = None


class MacAddressResponse(MacAddressBase):
    """MAC address response schema"""
    id: int
    status: str
    timestamp: datetime
    source: str
    
    class Config:
        from_attributes = True


class MacAddressQuery(BaseModel):
    """Query parameters for MAC address search"""
    ip: Optional[str] = None
    mac: Optional[str] = None
    status: Optional[str] = None
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


# Whitelist schemas
class WhitelistBase(BaseModel):
    """Base whitelist schema"""
    mac_address: Optional[str] = Field(None, description="MAC address")
    comments: Optional[str] = None


class WhitelistCreate(BaseModel):
    """Schema for adding to whitelist"""
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    comments: Optional[str] = None


class WhitelistResponse(WhitelistBase):
    """Whitelist response schema"""
    id: int
    ip_address: Optional[str] = None
    added_by: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Blacklist schemas
class BlacklistBase(BaseModel):
    """Base blacklist schema"""
    ip_address: Optional[str] = Field(None, description="IP address")
    mac_address: Optional[str] = Field(None, description="MAC address")
    reason: Optional[str] = None


class BlacklistCreate(BlacklistBase):
    """Schema for adding to blacklist"""
    pass


class BlacklistResponse(BlacklistBase):
    """Blacklist response schema"""
    id: int
    blocked_at: datetime
    expires_at: Optional[datetime] = None
    blocked_by: str
    
    class Config:
        from_attributes = True


# Audit Log schemas
class AuditLogBase(BaseModel):
    """Base audit log schema"""
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None


class AuditLogResponse(AuditLogBase):
    """Audit log response schema"""
    id: int
    username: str
    ip_address: Optional[str] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True


# Generic response schema
class ResponseMessage(BaseModel):
    """Generic response message"""
    message: str
    success: bool = True
