"""
Notification Event Types for TerminalAccessManager.

Defines all event types that can trigger notifications.
"""

from enum import StrEnum


class EventType(StrEnum):
    """Event type enumeration"""

    # Terminal events
    TERMINAL_COMPLIANT = "terminal.compliant"
    TERMINAL_NON_COMPLIANT = "terminal.non_compliant"
    TERMINAL_BLOCKED = "terminal.blocked"
    TERMINAL_UNBLOCKED = "terminal.unblocked"
    TERMINAL_ONLINE = "terminal.online"
    TERMINAL_OFFLINE = "terminal.offline"

    # Security events
    LOGIN_SUCCESS = "security.login_success"
    LOGIN_FAILED = "security.login_failed"
    LOGIN_LOCKED = "security.login_locked"
    PASSWORD_CHANGED = "security.password_changed"
    PASSWORD_RESET = "security.password_reset"
    PASSWORD_RESET_REQUESTED = "security.password_reset_requested"
    VERIFICATION_CODE_SENT = "security.verification_code_sent"
    USER_CREATED = "security.user_created"
    USER_DELETED = "security.user_deleted"
    USER_UPDATED = "security.user_updated"
    EMAIL_VERIFIED = "security.email_verified"

    # System events
    DATASOURCE_SYNC_FAILED = "system.datasource_sync_failed"
    DATASOURCE_SYNC_SUCCESS = "system.datasource_sync_success"
    FIREWALL_CONNECTION_LOST = "system.firewall_connection_lost"
    FIREWALL_CONNECTION_RESTORED = "system.firewall_connection_restored"
    BACKUP_COMPLETED = "system.backup_completed"
    BACKUP_FAILED = "system.backup_failed"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"

    # Compliance events
    COMPLIANCE_RATE_LOW = "alert.compliance_rate_low"
    COMPLIANCE_RATE_CRITICAL = "alert.compliance_rate_critical"
    BLOCK_THRESHOLD_EXCEEDED = "alert.block_threshold"
    AUTO_BLOCK_TRIGGERED = "alert.auto_block_triggered"
    AUTO_UNBLOCK_TRIGGERED = "alert.auto_unblock_triggered"

    # Admin events
    CONFIG_CHANGED = "admin.config_changed"
    ROLE_CHANGED = "admin.role_changed"
    PERMISSION_CHANGED = "admin.permission_changed"


class ChannelType(StrEnum):
    """Notification channel type enumeration"""

    EMAIL = "email"
    WEBHOOK = "webhook"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECOM = "wecom"


# Event metadata for UI display
EVENT_METADATA = {
    EventType.TERMINAL_COMPLIANT: {
        "name": "终端合规",
        "description": "终端通过合规检查",
        "severity": "info",
        "category": "terminal",
    },
    EventType.TERMINAL_NON_COMPLIANT: {
        "name": "终端不合规",
        "description": "终端未通过合规检查",
        "severity": "warning",
        "category": "terminal",
    },
    EventType.TERMINAL_BLOCKED: {
        "name": "终端被封锁",
        "description": "终端已被添加到黑名单",
        "severity": "error",
        "category": "terminal",
    },
    EventType.TERMINAL_UNBLOCKED: {
        "name": "终端解封",
        "description": "终端已从黑名单移除",
        "severity": "info",
        "category": "terminal",
    },
    EventType.TERMINAL_ONLINE: {
        "name": "终端上线",
        "description": "终端网络连接已恢复",
        "severity": "info",
        "category": "terminal",
    },
    EventType.TERMINAL_OFFLINE: {
        "name": "终端离线",
        "description": "终端网络连接已断开",
        "severity": "warning",
        "category": "terminal",
    },
    EventType.LOGIN_SUCCESS: {
        "name": "登录成功",
        "description": "用户登录成功",
        "severity": "info",
        "category": "security",
    },
    EventType.LOGIN_FAILED: {
        "name": "登录失败",
        "description": "用户登录失败",
        "severity": "warning",
        "category": "security",
    },
    EventType.LOGIN_LOCKED: {
        "name": "账户锁定",
        "description": "账户因多次失败被锁定",
        "severity": "error",
        "category": "security",
    },
    EventType.PASSWORD_CHANGED: {
        "name": "密码变更",
        "description": "用户密码已更改",
        "severity": "info",
        "category": "security",
    },
    EventType.PASSWORD_RESET: {
        "name": "密码重置",
        "description": "用户密码已被重置",
        "severity": "info",
        "category": "security",
    },
    EventType.PASSWORD_RESET_REQUESTED: {
        "name": "密码重置请求",
        "description": "用户请求重置密码",
        "severity": "info",
        "category": "security",
    },
    EventType.VERIFICATION_CODE_SENT: {
        "name": "验证码发送",
        "description": "验证码已发送给用户",
        "severity": "info",
        "category": "security",
    },
    EventType.EMAIL_VERIFIED: {
        "name": "邮箱验证",
        "description": "用户邮箱已验证",
        "severity": "info",
        "category": "security",
    },
    EventType.USER_CREATED: {
        "name": "用户创建",
        "description": "新用户已创建",
        "severity": "info",
        "category": "admin",
    },
    EventType.USER_DELETED: {
        "name": "用户删除",
        "description": "用户已被删除",
        "severity": "warning",
        "category": "admin",
    },
    EventType.USER_UPDATED: {
        "name": "用户更新",
        "description": "用户信息已更新",
        "severity": "info",
        "category": "admin",
    },
    EventType.DATASOURCE_SYNC_FAILED: {
        "name": "数据源同步失败",
        "description": "数据源同步操作失败",
        "severity": "error",
        "category": "system",
    },
    EventType.DATASOURCE_SYNC_SUCCESS: {
        "name": "数据源同步成功",
        "description": "数据源同步操作成功",
        "severity": "info",
        "category": "system",
    },
    EventType.FIREWALL_CONNECTION_LOST: {
        "name": "防火墙连接断开",
        "description": "无法连接到防火墙",
        "severity": "error",
        "category": "system",
    },
    EventType.FIREWALL_CONNECTION_RESTORED: {
        "name": "防火墙连接恢复",
        "description": "防火墙连接已恢复",
        "severity": "info",
        "category": "system",
    },
    EventType.BACKUP_COMPLETED: {
        "name": "备份完成",
        "description": "数据备份成功完成",
        "severity": "info",
        "category": "system",
    },
    EventType.BACKUP_FAILED: {
        "name": "备份失败",
        "description": "数据备份失败",
        "severity": "error",
        "category": "system",
    },
    EventType.SYSTEM_ERROR: {
        "name": "系统错误",
        "description": "系统发生错误",
        "severity": "error",
        "category": "system",
    },
    EventType.SYSTEM_WARNING: {
        "name": "系统警告",
        "description": "系统发出警告",
        "severity": "warning",
        "category": "system",
    },
    EventType.COMPLIANCE_RATE_LOW: {
        "name": "合规率低",
        "description": "终端合规率低于阈值",
        "severity": "warning",
        "category": "alert",
    },
    EventType.COMPLIANCE_RATE_CRITICAL: {
        "name": "合规率危险",
        "description": "终端合规率严重低于阈值",
        "severity": "error",
        "category": "alert",
    },
    EventType.AUTO_BLOCK_TRIGGERED: {
        "name": "自动封锁触发",
        "description": "系统自动封锁了不合规终端",
        "severity": "warning",
        "category": "alert",
    },
    EventType.AUTO_UNBLOCK_TRIGGERED: {
        "name": "自动解封触发",
        "description": "系统自动解封了合规终端",
        "severity": "info",
        "category": "alert",
    },
    EventType.BLOCK_THRESHOLD_EXCEEDED: {
        "name": "封禁阈值超限",
        "description": "封禁数量超过预设阈值",
        "severity": "warning",
        "category": "alert",
    },
    EventType.CONFIG_CHANGED: {
        "name": "配置变更",
        "description": "系统配置已修改",
        "severity": "info",
        "category": "admin",
    },
    EventType.ROLE_CHANGED: {
        "name": "角色变更",
        "description": "用户角色已更改",
        "severity": "warning",
        "category": "admin",
    },
    EventType.PERMISSION_CHANGED: {
        "name": "权限变更",
        "description": "用户权限已变更",
        "severity": "warning",
        "category": "admin",
    },
}

CHANNEL_METADATA = {
    ChannelType.EMAIL: {
        "name": "邮件",
        "description": "通过SMTP发送邮件通知",
        "config_fields": ["recipients"],
    },
    ChannelType.WEBHOOK: {
        "name": "Webhook",
        "description": "通过HTTP POST发送Webhook通知",
        "config_fields": ["url", "method", "headers", "secret"],
    },
    ChannelType.FEISHU: {
        "name": "飞书",
        "description": "通过飞书机器人发送通知",
        "config_fields": ["webhook_url"],
    },
    ChannelType.DINGTALK: {
        "name": "钉钉",
        "description": "通过钉钉机器人发送通知",
        "config_fields": ["webhook_url", "secret"],
    },
    ChannelType.WECOM: {
        "name": "企业微信",
        "description": "通过企业微信机器人发送通知",
        "config_fields": ["webhook_url"],
    },
}
