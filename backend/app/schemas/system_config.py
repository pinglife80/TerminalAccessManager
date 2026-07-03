from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class ConfigValueType(StrEnum):
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    JSON = "json"


class ConfigCategory(StrEnum):
    SECURITY = "security"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    NETWORK = "network"
    SCHEDULER = "scheduler"
    GENERAL = "general"
    LOGGING = "logging"
    BRANDING = "branding"
    EMAIL = "email"


class SystemConfigBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, description="Configuration key")
    value: str = Field(..., description="Configuration value")
    description: str | None = Field(None, description="Human-readable description")
    category: ConfigCategory = Field(ConfigCategory.GENERAL, description="Config category")
    value_type: ConfigValueType = Field(ConfigValueType.STRING, description="Value type for parsing")


class SystemConfigCreate(SystemConfigBase):
    is_readonly: bool = Field(False, description="Whether this config is read-only in web UI")


class SystemConfigUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, description="Configuration key")
    value: str = Field(..., description="New configuration value")
    description: str | None = None

    @field_validator('value')
    @classmethod
    def validate_value(cls, v):
        # Allow empty strings (e.g., for optional URLs)
        return v


class SystemConfigResponse(SystemConfigBase):
    id: int
    is_readonly: bool
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SystemConfigListResponse(BaseModel):
    configs: list[SystemConfigResponse]
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
    sangfor_base_url: str | None = None
    switch_enabled: bool
    switch_host: str | None = None
    ipguard_enabled: bool
    ipguard_host: str | None = None


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


class EmailConfigResponse(BaseModel):
    """Email SMTP server configuration values.

    Used by both the password-reset/verification-code flow and the
    notification email channel. Password is returned masked to avoid
    leaking credentials to the frontend."""
    email_enabled: bool
    email_host: str
    email_port: int
    email_use_tls: bool
    email_use_ssl: bool
    email_username: str
    email_password: str
    email_from: str
    email_from_name: str
    email_rate_limit: int


class AllConfigsResponse(BaseModel):
    """All config categories combined"""
    security: SecurityConfigResponse
    rate_limit: RateLimitConfigResponse
    network: NetworkConfigResponse
    scheduler: SchedulerConfigResponse
    general: GeneralConfigResponse
    branding: BrandingConfigResponse
    email: EmailConfigResponse


class ConfigUpdateRequest(BaseModel):
    """Request body for updating multiple configs at once"""
    configs: list[SystemConfigUpdate] = Field(..., min_length=1)


class ConfigUpdateResult(BaseModel):
    """Result of a config update operation"""
    key: str
    success: bool
    message: str | None = None
