from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


IpPatternType = Literal["single_ip", "cidr", "ip_range"]
MacPatternType = Literal["mac", "mac_prefix"]


class TerminalExclusionCreate(BaseModel):
    ip_type: IpPatternType | None = Field(
        default=None,
        description="IP condition type: single_ip, cidr or ip_range",
    )
    ip_value: str | None = Field(
        default=None,
        description="IP condition value: 192.168.1.10 / 192.168.1.0/24 / 192.168.1.1-100",
    )
    mac_type: MacPatternType | None = Field(
        default=None,
        description="MAC condition type: mac (full) or mac_prefix",
    )
    mac_value: str | None = Field(
        default=None,
        description="MAC condition value: AA:BB:CC:DD:EE:FF or AA:BB:CC",
    )
    comments: str = Field(..., min_length=1, description="Why these terminals are excluded")


class TerminalExclusionUpdate(BaseModel):
    ip_type: IpPatternType | None = None
    ip_value: str | None = None
    mac_type: MacPatternType | None = None
    mac_value: str | None = None
    comments: str | None = None
    is_active: bool | None = None


class TerminalExclusionPreview(BaseModel):
    ip_type: IpPatternType | None = None
    ip_value: str | None = None
    mac_type: MacPatternType | None = None
    mac_value: str | None = None


class TerminalExclusionResponse(BaseModel):
    id: int
    ip_type: IpPatternType | None = None
    ip_value: str | None = None
    mac_type: MacPatternType | None = None
    mac_value: str | None = None
    comments: str | None = None
    is_active: bool
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, rule) -> "TerminalExclusionResponse":
        return cls(
            id=rule.id,
            ip_type=rule.ip_pattern_type,
            ip_value=rule.ip_pattern,
            mac_type=rule.mac_pattern_type,
            mac_value=rule.mac_address,
            comments=rule.comments,
            is_active=rule.is_active,
            created_by=rule.created_by,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )


class ExclusionSample(BaseModel):
    ip_address: str
    mac_address: str
    status: str
    reason: str


class ExclusionImpact(BaseModel):
    matched: int = 0
    purgeable: int = 0
    retained: int = 0
    samples: list[ExclusionSample] = Field(default_factory=list)


class TerminalExclusionWithImpact(BaseModel):
    rule: TerminalExclusionResponse
    impact: ExclusionImpact


class TerminalExclusionListResponse(BaseModel):
    items: list[TerminalExclusionResponse]
    total: int
