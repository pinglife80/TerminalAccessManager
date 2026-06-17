export const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  blocked: { label: 'Blocked', className: 'bg-red-100 text-red-800' },
  unblocked: { label: 'Unblocked', className: 'bg-blue-100 text-blue-800' },
};

export const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', iconName: 'LayoutDashboard', adminOnly: false, requiredPermission: null },
  { path: '/terminals', label: 'Terminals', iconName: 'Network', adminOnly: false, requiredPermission: 'terminal:read' },
  { path: '/whitelist', label: 'Whitelist', iconName: 'List', adminOnly: false, requiredPermission: 'whitelist:read' },
  { path: '/blacklist', label: 'Blocked', iconName: 'ShieldOff', adminOnly: false, requiredPermission: 'blacklist:read' },
  { path: '/audit-logs', label: 'Audit Logs', iconName: 'FileText', adminOnly: false, requiredPermission: 'audit:read' },
  { path: '/data-sources', label: 'Data Sources', iconName: 'Database', adminOnly: true, requiredPermission: 'datasource:read' },
  { path: '/users', label: 'Users', iconName: 'Users', adminOnly: true, requiredPermission: 'user:read' },
  { path: '/roles', label: 'Roles', iconName: 'Shield', adminOnly: true, requiredPermission: 'role:read' },
];

export const API_ENDPOINTS = {
  STATS: '/stats/',
  SYSTEM_STATUS: '/stats/system-status',
  TERMINALS_SEARCH: '/terminals/search',
  TERMINALS_LIST: '/terminals/',
  TERMINALS_BLOCK: '/terminals/block/',
  TERMINALS_UNBLOCK: '/terminals/unblock/',
  WHITELIST: '/whitelist/',
  BLACKLIST: '/blacklist/',
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
  AUTH_USERS: '/auth/users',
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