import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';

export interface Terminal {
  id: number;
  ip_address: string;
  mac_address: string;
  status: string;
  comments: string | null;
  timestamp: string;
  source: string;
  source_tag: string | null;
  compliance_status: string;  // compliant / bypass / non_compliant / unknown
  wl_match_type: string | null;  // "mac" / "ip" / "both" / null
  firewall_tag: string | null;  // from blacklist data
  black_match_type: string | null;  // from blacklist data: "mac" / "ip" / null
}

export interface WhitelistEntry {
  id: number;
  mac_address: string | null;
  ip_pattern: string | null;
  pattern_type: string;
  comments: string | null;
  added_by: string;
  created_at: string;
}

export interface BlacklistEntry {
  id: number;
  ip_address: string | null;
  mac_address: string | null;
  reason: string | null;
  blocked_at: string;
  expires_at: string | null;
  blocked_by: string;
  source_tag: string | null;
  firewall_tag: string | null;
  is_auto_blocked: boolean;
  auto_unblocked: boolean;
}

export interface DashboardStats {
  total: number;
  whitelisted: number;
  blocked: number;
  active: number;
  inactive: number;
  pending: number;
}

export interface SangforStatus {
  connected: boolean;
  cpu: number | null;
  memory: number | null;
  error: string | null;
}

export interface SystemStatus {
  backend_api: string;
  database: string;
  sangfor: SangforStatus | null;
  network_scanner: string;
  uptime?: string;
  version?: string;
  environment?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

// -------------------------------------------------------------------
// Stats hooks - use backend aggregation API
// -------------------------------------------------------------------
export const useStats = () => {
  return useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const response = await apiClient.get('/stats/');
      return response.data as DashboardStats;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });
};

export const useSystemStatus = () => {
  return useQuery({
    queryKey: ['systemStatus'],
    queryFn: async () => {
      const response = await apiClient.get('/stats/system-status');
      return response.data as SystemStatus;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });
};

// -------------------------------------------------------------------
// Terminal hooks - server-side filtering
// -------------------------------------------------------------------
export interface TerminalSearchParams {
  ip?: string;
  mac?: string;
  status?: string;
  compliance_status?: string;
  source_tag?: string;
  firewall_tag?: string;
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number;
  refetchInterval?: number;
}

export const useTerminals = (params?: TerminalSearchParams) => {
  return useQuery({
    queryKey: ['terminals', params],
    queryFn: async () => {
      const response = await apiClient.get('/terminals/search', { params });
      return response.data as PaginatedResponse<Terminal>;
    },
    placeholderData: keepPreviousData,
    refetchInterval: params?.refetchInterval,
  });
};

export const useInvalidTerminals = () => {
  return useQuery({
    queryKey: ['invalidTerminals'],
    queryFn: async () => {
      const response = await apiClient.get('/terminals/');
      return response.data as Terminal[];
    },
  });
};

// -------------------------------------------------------------------
// Whitelist hooks - server-side filtering
// -------------------------------------------------------------------
export interface WhitelistSearchParams {
  search?: string;
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number;
}

export const useWhitelist = (params?: WhitelistSearchParams) => {
  return useQuery({
    queryKey: ['whitelist', params],
    queryFn: async () => {
      const response = await apiClient.get('/whitelist/', { params });
      return response.data as PaginatedResponse<WhitelistEntry>;
    },
    placeholderData: keepPreviousData,
  });
};

// -------------------------------------------------------------------
// Blacklist hooks - server-side filtering
// -------------------------------------------------------------------
export interface BlacklistSearchParams {
  search?: string;
  start_date?: string;
  end_date?: string;
  status?: string;  // active / unblocked / all
  skip?: number;
  limit?: number;
  refetchInterval?: number;
}

export const useBlacklist = (params?: BlacklistSearchParams) => {
  // Separate refetchInterval from API params to avoid sending it to backend
  const { refetchInterval, ...apiParams } = params || {};
  return useQuery({
    queryKey: ['blacklist', apiParams],
    queryFn: async () => {
      const response = await apiClient.get('/blacklist/', { params: apiParams });
      return response.data as PaginatedResponse<BlacklistEntry>;
    },
    placeholderData: keepPreviousData,
    refetchInterval: refetchInterval,
  });
};

// -------------------------------------------------------------------
// Blacklist batch check - for Terminals page efficient lookup
// -------------------------------------------------------------------
export interface BlacklistCheckItem {
  mac_address: string | null;
  ip_address: string | null;
  firewall_tag: string | null;
}

export interface BlacklistCheckParams {
  mac_addresses: string[];
  ip_addresses: string[];
}

export const useBlacklistCheck = (params: BlacklistCheckParams) => {
  return useQuery({
    queryKey: ['blacklist-check', params.mac_addresses, params.ip_addresses],
    queryFn: async () => {
      const response = await apiClient.post('/blacklist/check', {
        mac_addresses: params.mac_addresses,
        ip_addresses: params.ip_addresses,
      });
      return response.data as BlacklistCheckItem[];
    },
    enabled: params.mac_addresses.length > 0 || params.ip_addresses.length > 0,
    placeholderData: keepPreviousData,
  });
};

// -------------------------------------------------------------------
// Audit Logs hooks - server-side filtering with cursor pagination
// -------------------------------------------------------------------
export interface AuditLogSearchParams {
  username?: string;
  action?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
  cursor?: string;
  skip?: number;
  limit?: number;
}

export interface CursorPaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  next_cursor: string | null;
}

export interface AuditLog {
  id: number;
  action: string;
  resource_type?: string;
  resource_id?: string;
  resource_name?: string;
  username: string;
  ip_address?: string;
  timestamp: string;
  details?: string;
}

export const useAuditLogs = (params?: AuditLogSearchParams) => {
  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: async () => {
      const response = await apiClient.get('/logs/search', { params });
      return response.data as CursorPaginatedResponse<AuditLog>;
    },
    placeholderData: keepPreviousData,
  });
};

// Settings interfaces
export interface SecurityConfig {
  max_login_attempts: number;
  lockout_duration_minutes: number;
  captcha_threshold: number;
  allow_registration: boolean;
  access_token_expire_minutes: number;
  refresh_token_expire_days: number;
}

export interface RateLimitConfig {
  rate_limit_per_minute: number;
  auth_rate_limit_per_minute: number;
}

export interface NetworkConfig {
  sangfor_enabled: boolean;
  sangfor_base_url: string;
  switch_enabled: boolean;
  switch_host: string;
  ipguard_enabled: boolean;
  ipguard_host: string;
}

export interface SchedulerConfig {
  scheduler_arp_collection_interval: number;
  scheduler_ipguard_sync_interval: number;
  scheduler_firewall_query_interval: number;
  scheduler_compliance_check_interval: number;
  scheduler_auto_unblock_interval: number;
}

export interface GeneralConfig {
  environment: string;
  debug: boolean;
  log_level: string;
}

export interface BrandingConfig {
  app_name: string;
  app_short_name: string;
  app_subtitle: string;
  login_heading: string;
  login_subheading: string;
  login_footer_text: string;
  login_bg_url: string;
  favicon_url: string;
  footer_copyright: string;
  footer_icp_number: string;
  footer_icp_url: string;
}

export interface AllConfigs {
  security: SecurityConfig;
  rate_limit: RateLimitConfig;
  network: NetworkConfig;
  scheduler: SchedulerConfig;
  general: GeneralConfig;
  branding: BrandingConfig;
}

export interface ConfigEntry {
  id: number;
  key: string;
  value: string;
  description: string | null;
  category: string;
  value_type: string;
  is_readonly: boolean;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export const useSettings = () => {
  return useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const response = await apiClient.get('/settings/');
      return response.data as AllConfigs;
    },
  });
};

export const useSettingsList = (category?: string) => {
  return useQuery({
    queryKey: ['settings-list', category],
    queryFn: async () => {
      const response = await apiClient.get('/settings/list', {
        params: category ? { category } : undefined,
      });
      return response.data as ConfigEntry[];
    },
  });
};

// User management interfaces
export interface UserItem {
  id: number;
  username: string;
  email: string | null;
  is_active: boolean;
  is_superuser: boolean;
  roles: string[];
  permissions: string[];
  provider: string;
  provider_user_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const useUsers = (search?: string) => {
  return useQuery({
    queryKey: ['users', search],
    queryFn: async () => {
      const response = await apiClient.get('/auth/users', {
        params: search ? { search } : undefined,
      });
      return response.data as UserItem[];
    },
    placeholderData: keepPreviousData,
  });
};

// -------------------------------------------------------------------
// Data Source hooks
// -------------------------------------------------------------------
export interface DataSourceItem {
  id: number;
  name: string;
  type: string;  // arp_ssh / arp_api / ipguard / sangfor
  tag: string;
  config: Record<string, string | number | boolean | object | null>;
  enabled: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DataSourceBindingItem {
  id: number;
  arp_source_tag: string;
  firewall_tag: string;
  created_at: string | null;
}

export const useDataSources = () => {
  return useQuery({
    queryKey: ['data-sources'],
    queryFn: async () => {
      const response = await apiClient.get('/data-sources/');
      return response.data as DataSourceItem[];
    },
    placeholderData: keepPreviousData,
  });
};

export const useDataSourceBindings = () => {
  return useQuery({
    queryKey: ['data-source-bindings'],
    queryFn: async () => {
      const response = await apiClient.get('/data-sources/bindings/');
      return response.data as DataSourceBindingItem[];
    },
    placeholderData: keepPreviousData,
  });
};

// -------------------------------------------------------------------
// Compliance Baselines hooks
// -------------------------------------------------------------------
export interface ComplianceBaselineItem {
  id: number;
  name: string;
  type: string;  // ipguard
  tag: string;
  config: Record<string, string | number | boolean | object | null>;
  enabled: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export function useComplianceBaselines() {
  return useQuery({
    queryKey: ['compliance-baselines'],
    queryFn: async () => {
      const { data } = await apiClient.get('/compliance-baselines/');
      return data as ComplianceBaselineItem[];
    },
    placeholderData: keepPreviousData,
  });
}


// ==================== Notification Logs (D8) ====================
export interface NotificationLogItem {
  id: number;
  event_id: string;
  channel_name: string;
  event_type: string;
  status: 'sent' | 'failed' | 'pending';
  recipient: string | null;
  error_message: string | null;
  details: Record<string, unknown> | null;
  sent_at: string;
}

export interface NotificationLogsResponse {
  items: NotificationLogItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface NotificationLogsParams {
  channel_name?: string;
  event_type?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export const useNotificationLogs = (params?: NotificationLogsParams) => {
  return useQuery({
    queryKey: ['notification-logs', params],
    queryFn: async () => {
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_LOGS, { params });
      return response.data as NotificationLogsResponse;
    },
    placeholderData: keepPreviousData,
  });
};

// ==================== Notification Channel Types (D1) ====================
export interface ChannelTypeInfo {
  type: string;
  name: string;
  description: string;
  config_fields: string[];
}

export const useNotificationChannelTypes = () => {
  return useQuery({
    queryKey: ['notification-channel-types'],
    queryFn: async () => {
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_CHANNEL_TYPES);
      return response.data.channels as ChannelTypeInfo[];
    },
  });
};
