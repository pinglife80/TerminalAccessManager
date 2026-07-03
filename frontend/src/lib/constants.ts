export const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  blocked: { label: 'Blocked', className: 'bg-red-100 text-red-800' },
  unblocked: { label: 'Unblocked', className: 'bg-blue-100 text-blue-800' },
};

export interface NavItem {
  path: string;
  label: string;
  iconName: string;
  adminOnly: boolean;
  requiredPermission: string | null;
  children?: NavItem[];
}

export const NAV_ITEMS: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', iconName: 'LayoutDashboard', adminOnly: false, requiredPermission: null },
  { path: '/terminals', label: 'Terminals', iconName: 'Network', adminOnly: false, requiredPermission: 'terminal:read' },
  { path: '/whitelist', label: 'Whitelist', iconName: 'List', adminOnly: false, requiredPermission: 'whitelist:read' },
  { path: '/blacklist', label: 'Blocked', iconName: 'ShieldOff', adminOnly: false, requiredPermission: 'blacklist:read' },
  { path: '/audit-logs', label: 'Audit Logs', iconName: 'FileText', adminOnly: false, requiredPermission: 'audit:read' },
  { path: '/data-sources', label: 'Data Sources', iconName: 'Database', adminOnly: true, requiredPermission: 'datasource:read' },
  { 
    path: '/system-settings', 
    label: 'System Settings', 
    iconName: 'Settings', 
    adminOnly: true, 
    requiredPermission: 'settings:read',
    children: [
      { path: '/general-settings', label: 'General', iconName: 'Settings', adminOnly: true, requiredPermission: 'settings:read' },
      { path: '/auth-providers', label: 'Auth Providers', iconName: 'Key', adminOnly: true, requiredPermission: 'settings:write' },
      { path: '/backup', label: 'Backup', iconName: 'HardDrive', adminOnly: true, requiredPermission: 'backup:read' },
      { path: '/notifications', label: 'Notifications', iconName: 'Bell', adminOnly: true, requiredPermission: 'notification:read' },
      { path: '/email-settings', label: 'Email', iconName: 'Mail', adminOnly: true, requiredPermission: 'settings:read' },
      { path: '/users', label: 'Users', iconName: 'Users', adminOnly: true, requiredPermission: 'user:read' },
      { path: '/roles', label: 'Roles', iconName: 'Shield', adminOnly: true, requiredPermission: 'role:read' },
    ]
  },
];

export const API_ENDPOINTS = {
  STATS: '/stats/',
  SYSTEM_STATUS: '/system/status',
  SYSTEM_CONFIG: '/system/config',
  TERMINALS_SEARCH: '/terminals/search',
  TERMINALS_LIST: '/terminals/',
  TERMINALS_BLOCK: '/terminals/block/',
  TERMINALS_UNBLOCK: '/terminals/unblock/',
  WHITELIST: '/whitelist/',
  BLACKLIST: '/blacklist/',
  BLACKLIST_CHECK: '/blacklist/check',
  AUDIT_LOGS: '/logs/',
  AUDIT_LOGS_SEARCH: '/logs/search',
  AUDIT_LOGS_EXPORT: '/logs/export',
  AUTH_LOGIN: '/auth/login',
  AUTH_CAPTCHA: '/auth/captcha',
  AUTH_ME: '/auth/me',
  AUTH_ME_PROFILE: '/auth/me/profile',
  AUTH_ME_PASSWORD: '/auth/me/password',
  AUTH_REFRESH: '/auth/refresh',
  AUTH_REGISTER: '/auth/register',
  AUTH_USERS: '/auth/users/',
  AUTH_PROVIDERS: '/auth/providers/',
  AUTH_PROVIDERS_TEST: '/auth/providers/{{id}}/test',
  DATA_SOURCES: '/data-sources/',
  DATA_SOURCE_BINDINGS: '/data-sources/bindings/',
  DATA_SOURCE_DELETE_PREVIEW: '/data-sources/',
  DATA_SOURCE_BINDING_DELETE_PREVIEW: '/data-sources/bindings/',
  COMPLIANCE_CHECK: '/data-sources/compliance/check',
  COMPLIANCE_AUTO_BLOCK: '/data-sources/compliance/auto-block',
  COMPLIANCE_AUTO_UNBLOCK: '/data-sources/compliance/auto-unblock',
  COMPLIANCE_BASELINES: '/compliance-baselines/',
  COMPLIANCE_BASELINE_DELETE_PREVIEW: '/compliance-baselines/',
  SETTINGS: '/settings/',
  SETTINGS_BRANDING: '/settings/branding',
  ROLES: '/roles/',
  ROLES_PERMISSIONS: '/roles/permissions',
  AUTH_USER_ROLES: '/roles/users/',
  BACKUP_CONFIG: '/backup/config',
  BACKUP_RUN: '/backup/run',
  BACKUP_LIST: '/backup/list',
  BACKUP_DOWNLOAD: '/backup/download/{{filename}}',
  BACKUP_RESTORE: '/backup/restore/{{filename}}',
  BACKUP_DELETE: '/backup/{{filename}}',
  BACKUP_TEST: '/backup/test',
  NOTIFICATION_CHANNELS: '/notifications/channels/',
  NOTIFICATION_CHANNELS_TEST: '/notifications/channels/{{id}}/test',
  NOTIFICATION_CHANNEL_TYPES: '/notifications/channel-types',
  NOTIFICATION_LOGS: '/notifications/logs',
  NOTIFICATION_EVENTS: '/notifications/events',
  NOTIFICATION_TEMPLATES: '/notifications/templates',
  NOTIFICATION_TEMPLATES_BY_ID: '/notifications/templates/{{id}}',
  NOTIFICATION_TEMPLATES_PREVIEW: '/notifications/templates/preview',
  NOTIFICATION_RULES: '/notifications/rules',
  NOTIFICATION_RULES_BY_ID: '/notifications/rules/{{id}}',
  NOTIFICATION_STATS: '/notifications/stats',
  NOTIFICATION_LOGS_RETRY: '/notifications/logs/{{id}}/retry',
  NOTIFICATION_LOGS_RETRY_ALL: '/notifications/logs/retry-all',
  SETTINGS_LIST: '/settings/list',
  SETTINGS_UPDATE: '/settings/update',
  SETTINGS_SEED: '/settings/seed',
  SETTINGS_INVALIDATE_CACHE: '/settings/invalidate-cache',
  SETTINGS_UPLOAD: '/settings/upload',
};

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export const DATE_FORMATS = {
  DISPLAY: 'YYYY-MM-DD HH:mm:ss',
  INPUT: 'YYYY-MM-DD',
};

export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'access_token',
  REFRESH_TOKEN: 'refresh_token',
};

export const COLORS = {
  PRIMARY: 'text-primary-600',
  SUCCESS: 'text-green-600',
  WARNING: 'text-yellow-600',
  ERROR: 'text-red-600',
  INFO: 'text-blue-600',
};
