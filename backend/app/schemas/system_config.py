from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ConfigValueType(str, Enum):
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    JSON = "json"


class ConfigCategory(str, Enum):
    SECURITY = "security"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    NETWORK = "network"
    SCHEDULER = "scheduler"
    GENERAL = "general"
    LOGGING = "logging"
    BRANDING = "branding"


class SystemConfigBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, description="Configuration key")
    value: str = Field(..., description="Configuration value")
    description: Optional[str] = Field(None, description="Human-readable description")
    category: ConfigCategory = Field(ConfigCategory.GENERAL, description="Config category")
    value_type: ConfigValueType = Field(ConfigValueType.STRING, description="Value type for parsing")


class SystemConfigCreate(SystemConfigBase):
    is_readonly: bool = Field(False, description="Whether this config is read-only in web UI")


class SystemConfigUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, description="Configuration key")
    value: str = Field(..., description="New configuration value")
    description: Optional[str] = None

    @field_validator('value')
    @classmethod
    def validate_value(cls, v):
        # Allow empty strings (e.g., for optional URLs)
        return v


class SystemConfigResponse(SystemConfigBase):
    id: int
    is_readonly: bool
    updated_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SystemConfigListResponse(BaseModel):
    configs: List[SystemConfigResponse]
    total: int


# Typed config responses for the frontend
class SecurityConfigResponse(BaseModel):
    """Security-related config values, parsed and typed"""
    max_login_attempts: int
    lockout_duration_minutes: int
    captcha_threshold: int
    allow_registration: bool
    access_token_expire_minutes: int
    refresh_token_expire_days: int


class RateLimitConfigResponse(BaseModel):
    """Rate limit config values, parsed and typed"""
    rate_limit_per_minute: int
    auth_rate_limit_per_minute: int


class NetworkConfigResponse(BaseModel):
    """Network integration config values"""
    sangfor_enabled: bool
    sangfor_base_url: Optional[str] = None
    switch_enabled: bool
    switch_host: Optional[str] = None
    ipguard_enabled: bool
    ipguard_host: Optional[str] = None


class GeneralConfigResponse(BaseModel):
    """General config values"""
    environment: str
    debug: bool
    log_level: str


class BrandingConfigResponse(BaseModel):
    """Branding customization config values"""
    app_name: str
    app_short_name: str
    app_subtitle: str
    login_heading: str
    login_subheading: str
    login_footer_text: str
    login_bg_url: str
    favicon_url: str
    footer_copyright: str
    footer_icp_number: str
    footer_icp_url: str


class SchedulerConfigResponse(BaseModel):
    """Scheduler interval config values (in seconds)"""
    scheduler_arp_collection_interval: int
    scheduler_ipguard_sync_interval: int
    scheduler_firewall_query_interval: int
    scheduler_compliance_check_interval: int
    scheduler_auto_unblock_interval: int


class AllConfigsResponse(BaseModel):
    """All config categories combined"""
    security: SecurityConfigResponse
    rate_limit: RateLimitConfigResponse
    network: NetworkConfigResponse
    scheduler: SchedulerConfigResponse
    general: GeneralConfigResponse
    branding: BrandingConfigResponse


class ConfigUpdateRequest(BaseModel):
    """Request body for updating multiple configs at once"""
    configs: List[SystemConfigUpdate] = Field(..., min_length=1)


class ConfigUpdateResult(BaseModel):
    """Result of a config update operation"""
    key: str
    success: bool
    message: Optional[str] = None
