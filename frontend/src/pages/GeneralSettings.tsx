import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';
import {
  Activity, Image as ImageIcon, Shield, Gauge, Network, Clock,
  Settings as SettingsIcon, Wrench, Save, Upload, Database, Trash2,
  Loader2,
} from 'lucide-react';
import { useSettings, useSettingsList, type AllConfigs, type ConfigEntry } from '@/hooks/useTerminalData';
import { useBrandingStore } from '@/store/branding';

// ==================== Helpers ====================

/** Deserialize a string form value back to the typed form for API submission. */
function deserializeValue(strVal: string, valueType: string): string | number | boolean {
  if (valueType === 'bool') return strVal === 'true';
  if (valueType === 'int') return Number(strVal);
  return strVal;
}

/** Field groups by category — drives section rendering. */
const SECTION_FIELDS: Record<string, string[]> = {
  branding: [
    'app_name', 'app_short_name', 'app_subtitle',
    'login_heading', 'login_subheading', 'login_footer_text',
    'footer_copyright', 'footer_icp_number', 'footer_icp_url',
    'login_bg_url', 'favicon_url',
  ],
  security: [
    'max_login_attempts', 'lockout_duration_minutes', 'captcha_threshold',
    'access_token_expire_minutes', 'refresh_token_expire_days', 'allow_registration',
  ],
  rate_limit: ['rate_limit_per_minute', 'auth_rate_limit_per_minute'],
  network: [
    'sangfor_enabled', 'sangfor_base_url',
    'switch_enabled', 'switch_host',
    'ipguard_enabled', 'ipguard_host',
  ],
  scheduler: [
    'scheduler_arp_collection_interval', 'scheduler_ipguard_sync_interval',
    'scheduler_firewall_query_interval', 'scheduler_compliance_check_interval',
    'scheduler_auto_unblock_interval',
  ],
  general: ['environment', 'debug', 'log_level'],
  compliance: ['compliance_confirm_threshold'],
  cache: ['cache_ipguard_ttl', 'cache_whitelist_ttl'],
};

/** Flatten AllConfigs grouped response into a key→string value map. */
function flattenConfigs(configs: AllConfigs | undefined): Record<string, string> {
  if (!configs) return {};
  const flat: Record<string, string> = {};
  const allGroups = [
    configs.security, configs.rate_limit, configs.network,
    configs.scheduler, configs.general, configs.branding,
    configs.compliance, configs.cache,
  ];
  for (const group of allGroups) {
    if (!group) continue;
    for (const [k, v] of Object.entries(group)) {
      flat[k] = typeof v === 'boolean' ? (v ? 'true' : 'false') : String(v);
    }
  }
  return flat;
}

// ==================== Section Card ====================

interface SectionCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  onSave?: () => void;
  saving?: boolean;
  hasChanges?: boolean;
}

const SectionCard: React.FC<SectionCardProps> = ({ title, description, icon, children, onSave, saving, hasChanges }) => {
  const { t } = useTranslation();
  return (
    <div className="bg-card rounded-lg border border-border shadow-sm">
      <div className="flex items-center justify-between p-4 sm:p-5 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-primary/10 text-primary-600">{icon}</div>
          <div>
            <h3 className="text-base font-semibold text-foreground">{title}</h3>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        {onSave && (
          <PrimaryButton
            icon={Save}
            label={t('common.save')}
            onClick={onSave}
            loading={saving}
            disabled={!hasChanges}
          />
        )}
      </div>
      <div className="p-4 sm:p-5">{children}</div>
    </div>
  );
};

// ==================== Field renderer ====================

interface FieldProps {
  entry: ConfigEntry | undefined;
  value: string;
  onChange: (v: string) => void;
}

const Field: React.FC<FieldProps> = ({ entry, value, onChange }) => {
  const { t } = useTranslation();
  if (!entry) return null;
  const readonly = entry.is_readonly;
  const baseClass = 'w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-60 disabled:cursor-not-allowed';

  let input: React.ReactNode;
  if (entry.value_type === 'bool') {
    input = (
      <label className="inline-flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={value === 'true'}
          onChange={(e) => onChange(e.target.checked ? 'true' : 'false')}
          disabled={readonly}
          className="h-4 w-4 rounded border-input text-primary-600 focus:ring-primary-500"
        />
        <span className="text-sm text-muted-foreground">{value === 'true' ? t('common.enabled') : t('common.disabled')}</span>
      </label>
    );
  } else if (entry.key === 'log_level') {
    input = (
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={readonly} className={baseClass}>
        {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((lv) => (
          <option key={lv} value={lv}>{lv}</option>
        ))}
      </select>
    );
  } else if (entry.value_type === 'int') {
    input = (
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={readonly}
        className={baseClass}
      />
    );
  } else {
    input = (
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={readonly}
        placeholder={entry.description || ''}
        className={baseClass}
      />
    );
  }

  return (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">
        {entry.key}
        {readonly && <span className="ml-2 text-xs text-muted-foreground">({t('generalSettings.readonly')})</span>}
      </label>
      {input}
      {entry.description && <p className="mt-1 text-xs text-muted-foreground">{entry.description}</p>}
    </div>
  );
};

// ==================== Main Component ====================

const GeneralSettings: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: configs, isLoading: configsLoading } = useSettings();
  const { data: entries } = useSettingsList();

  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [originalValues, setOriginalValues] = useState<Record<string, string>>({});
  const [savingSection, setSavingSection] = useState<string | null>(null);
  const [systemStatus, setSystemStatus] = useState<{ uptime?: string; database?: string; version?: string; environment?: string; platform?: string; python_version?: string } | null>(null);
  const [health, setHealth] = useState<{ status?: string; db?: string; redis?: string } | null>(null);
  const [operationLoading, setOperationLoading] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const fileBgRef = useRef<HTMLInputElement>(null);
  const fileFaviconRef = useRef<HTMLInputElement>(null);

  // Initialize form values from configs
  useEffect(() => {
    if (configs) {
      const flat = flattenConfigs(configs);
      setFormValues(flat);
      setOriginalValues(flat);
    }
  }, [configs]);

  // Fetch system status + health
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [statusRes, healthRes] = await Promise.all([
          apiClient.get(API_ENDPOINTS.SYSTEM_STATUS),
          fetch('/health').then((r) => r.json()).catch(() => null),
        ]);
        setSystemStatus(statusRes.data);
        if (healthRes) setHealth(healthRes);
      } catch {
        // ignore — non-critical
      }
    };
    fetchStatus();
  }, []);

  const entryMap = useMemo(() => {
    const m: Record<string, ConfigEntry> = {};
    entries?.forEach((e) => { m[e.key] = e; });
    return m;
  }, [entries]);

  const getChanges = (category: string): { key: string; value: string }[] => {
    const fields = SECTION_FIELDS[category] || [];
    return fields
      .filter((k) => formValues[k] !== originalValues[k])
      .map((k) => ({ key: k, value: formValues[k] }));
  };

  const hasSectionChanges = (category: string): boolean => getChanges(category).length > 0;

  const handleSave = async (category: string) => {
    const changes = getChanges(category);
    if (changes.length === 0) {
      toast.info(t('generalSettings.noChanges'));
      return;
    }
    setSavingSection(category);
    try {
      const payload = changes.map((c) => {
        const entry = entryMap[c.key];
        const typed = deserializeValue(c.value, entry?.value_type || 'string');
        return { key: c.key, value: String(typed) };
      });
      const response = await apiClient.put(API_ENDPOINTS.SETTINGS_UPDATE, payload);
      const results = response.data as Array<{ key: string; success: boolean; message?: string }>;
      const failed = results.filter((r) => !r.success);
      if (failed.length === 0) {
        toast.success(t('generalSettings.saveSuccess'));
      } else if (failed.length === results.length) {
        toast.error(t('generalSettings.saveFailed'));
      } else {
        toast.warning(`${t('generalSettings.partialFail')}: ${failed.map((f) => f.key).join(', ')}`);
      }
      // Update original values for successfully saved keys
      const newOriginal = { ...originalValues };
      results.forEach((r) => { if (r.success) newOriginal[r.key] = formValues[r.key]; });
      setOriginalValues(newOriginal);
      // Invalidate settings cache
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['settings-list'] });
      // Branding changes need to refresh global branding store
      if (category === 'branding') {
        await useBrandingStore.getState().loadFromBackend();
      }
    } catch (err) {
      toast.error(getErrorMessage(err, t('generalSettings.saveFailed')));
    } finally {
      setSavingSection(null);
    }
  };

  const handleUpload = async (purpose: 'login_bg' | 'favicon', file: File) => {
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/x-icon', 'image/vnd.microsoft.icon'];
    if (!validTypes.includes(file.type)) {
      toast.error(t('generalSettings.invalidFileType'));
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error(t('generalSettings.fileTooLarge'));
      return;
    }
    setUploading(purpose);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await apiClient.post(`${API_ENDPOINTS.SETTINGS_UPLOAD}?purpose=${purpose}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const { url, config_key } = response.data;
      setFormValues((prev) => ({ ...prev, [config_key]: url }));
      setOriginalValues((prev) => ({ ...prev, [config_key]: url }));
      toast.success(t('generalSettings.uploadSuccess'));
      await useBrandingStore.getState().loadFromBackend();
    } catch (err) {
      toast.error(getErrorMessage(err, t('generalSettings.uploadFailed')));
    } finally {
      setUploading(null);
    }
  };

  const handleSeed = async () => {
    if (!window.confirm(t('generalSettings.seedConfirm'))) return;
    setOperationLoading('seed');
    try {
      const response = await apiClient.post(API_ENDPOINTS.SETTINGS_SEED);
      const { count } = response.data;
      if (count === 0) {
        toast.info(t('generalSettings.seedNoChange'));
      } else {
        toast.success(t('generalSettings.seedSuccess', { count }));
      }
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['settings-list'] });
    } catch (err) {
      toast.error(getErrorMessage(err, t('generalSettings.saveFailed')));
    } finally {
      setOperationLoading(null);
    }
  };

  const handleInvalidateCache = async () => {
    if (!window.confirm(t('generalSettings.invalidateConfirm'))) return;
    setOperationLoading('invalidate');
    try {
      await apiClient.post(API_ENDPOINTS.SETTINGS_INVALIDATE_CACHE);
      toast.success(t('generalSettings.invalidateSuccess'));
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['settings-list'] });
    } catch (err) {
      toast.error(getErrorMessage(err, t('generalSettings.saveFailed')));
    } finally {
      setOperationLoading(null);
    }
  };

  const handleFirewallReconciliation = async () => {
    if (!window.confirm(t('generalSettings.firewallReconciliationConfirm'))) return;
    setOperationLoading('reconcile');
    try {
      const res = await apiClient.post(API_ENDPOINTS.FIREWALL_RECONCILIATION);
      const result = res.data;
      toast.success(t('generalSettings.firewallReconciliationSuccess', {
        firewallCount: result.firewall_ip_count || 0,
        dbCount: result.db_entry_count || 0,
        created: result.created_in_db || 0,
        missingDb: result.missing_in_db?.length || 0,
        missingFirewall: result.missing_in_firewall?.length || 0,
      }));
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['settings-list'] });
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setOperationLoading(null);
    }
  };

  const setField = (key: string, value: string) => {
    setFormValues((prev) => ({ ...prev, [key]: value }));
  };

  if (configsLoading && !configs) {
    return (
      <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  const isHealthy = health?.status === 'healthy';

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('generalSettings.title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('generalSettings.description')}</p>
        </div>

        {/* 1. System Status */}
        <SectionCard
          title={t('generalSettings.systemStatus')}
          description={t('generalSettings.healthCheck')}
          icon={<Activity className="h-5 w-5" />}
        >
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.status')}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className={`h-2.5 w-2.5 rounded-full ${isHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm font-medium">{isHealthy ? t('generalSettings.healthy') : t('generalSettings.unhealthy')}</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.uptime')}</p>
              <p className="text-sm font-medium mt-1">{systemStatus?.uptime || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.version')}</p>
              <p className="text-sm font-medium mt-1">{systemStatus?.version || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.environment')}</p>
              <p className="text-sm font-medium mt-1">{systemStatus?.environment || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.database')}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className={`h-2.5 w-2.5 rounded-full ${health?.db === 'ok' || systemStatus?.database === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm font-medium">{health?.db === 'ok' || systemStatus?.database === 'healthy' ? t('generalSettings.healthy') : t('generalSettings.unhealthy')}</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.redis')}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className={`h-2.5 w-2.5 rounded-full ${health?.redis === 'ok' ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm font-medium">{health?.redis === 'ok' ? t('generalSettings.healthy') : t('generalSettings.unhealthy')}</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.platform')}</p>
              <p className="text-sm font-medium mt-1 truncate" title={systemStatus?.platform}>{systemStatus?.platform || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('generalSettings.pythonVersion')}</p>
              <p className="text-sm font-medium mt-1">{systemStatus?.python_version || '-'}</p>
            </div>
          </div>
        </SectionCard>

        {/* 2. Branding */}
        <SectionCard
          title={t('generalSettings.branding')}
          description={t('generalSettings.brandingDesc')}
          icon={<ImageIcon className="h-5 w-5" />}
          onSave={() => handleSave('branding')}
          saving={savingSection === 'branding'}
          hasChanges={hasSectionChanges('branding')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.branding.filter((k) => k !== 'login_bg_url' && k !== 'favicon_url').map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] || ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
          {/* File uploads */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t('generalSettings.loginBgUrl')}</label>
              <p className="text-xs text-muted-foreground mb-2 truncate" title={formValues.login_bg_url}>{formValues.login_bg_url || '-'}</p>
              <input
                ref={fileBgRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/x-icon"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload('login_bg', f); e.target.value = ''; }}
              />
              <PrimaryButton icon={Upload} label={t('generalSettings.uploadBg')} onClick={() => fileBgRef.current?.click()} loading={uploading === 'login_bg'} variant="secondary" />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t('generalSettings.faviconUrl')}</label>
              <p className="text-xs text-muted-foreground mb-2 truncate" title={formValues.favicon_url}>{formValues.favicon_url || '-'}</p>
              <input
                ref={fileFaviconRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/x-icon"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload('favicon', f); e.target.value = ''; }}
              />
              <PrimaryButton icon={Upload} label={t('generalSettings.uploadFavicon')} onClick={() => fileFaviconRef.current?.click()} loading={uploading === 'favicon'} variant="secondary" />
            </div>
          </div>
        </SectionCard>

        {/* 3. Security */}
        <SectionCard
          title={t('generalSettings.security')}
          description={t('generalSettings.securityDesc')}
          icon={<Shield className="h-5 w-5" />}
          onSave={() => handleSave('security')}
          saving={savingSection === 'security'}
          hasChanges={hasSectionChanges('security')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.security.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 4. Rate Limit */}
        <SectionCard
          title={t('generalSettings.rateLimit')}
          description={t('generalSettings.rateLimitDesc')}
          icon={<Gauge className="h-5 w-5" />}
          onSave={() => handleSave('rate_limit')}
          saving={savingSection === 'rate_limit'}
          hasChanges={hasSectionChanges('rate_limit')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.rate_limit.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 5. Network */}
        <SectionCard
          title={t('generalSettings.network')}
          description={t('generalSettings.networkDesc')}
          icon={<Network className="h-5 w-5" />}
          onSave={() => handleSave('network')}
          saving={savingSection === 'network'}
          hasChanges={hasSectionChanges('network')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.network.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 6. Scheduler */}
        <SectionCard
          title={t('generalSettings.scheduler')}
          description={t('generalSettings.schedulerDesc')}
          icon={<Clock className="h-5 w-5" />}
          onSave={() => handleSave('scheduler')}
          saving={savingSection === 'scheduler'}
          hasChanges={hasSectionChanges('scheduler')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.scheduler.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 7. General */}
        <SectionCard
          title={t('generalSettings.general')}
          description={t('generalSettings.generalDesc')}
          icon={<SettingsIcon className="h-5 w-5" />}
          onSave={() => handleSave('general')}
          saving={savingSection === 'general'}
          hasChanges={hasSectionChanges('general')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.general.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 8. Compliance */}
        <SectionCard
          title={t('generalSettings.compliance')}
          description={t('generalSettings.complianceDesc')}
          icon={<Activity className="h-5 w-5" />}
          onSave={() => handleSave('compliance')}
          saving={savingSection === 'compliance'}
          hasChanges={hasSectionChanges('compliance')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.compliance.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 9. Cache */}
        <SectionCard
          title={t('generalSettings.cache')}
          description={t('generalSettings.cacheDesc')}
          icon={<Database className="h-5 w-5" />}
          onSave={() => handleSave('cache')}
          saving={savingSection === 'cache'}
          hasChanges={hasSectionChanges('cache')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SECTION_FIELDS.cache.map((key) => (
              <Field key={key} entry={entryMap[key]} value={formValues[key] ?? ''} onChange={(v) => setField(key, v)} />
            ))}
          </div>
        </SectionCard>

        {/* 10. Operations */}
        <SectionCard
          title={t('generalSettings.operations')}
          description={t('generalSettings.operationsDesc')}
          icon={<Wrench className="h-5 w-5" />}
        >
          <div className="flex flex-wrap gap-3">
            <PrimaryButton
              icon={Database}
              label={t('generalSettings.seedDefaults')}
              onClick={handleSeed}
              loading={operationLoading === 'seed'}
              variant="secondary"
            />
            <PrimaryButton
              icon={Trash2}
              label={t('generalSettings.invalidateCache')}
              onClick={handleInvalidateCache}
              loading={operationLoading === 'invalidate'}
              variant="warning"
            />
            <PrimaryButton
              icon={Shield}
              label={t('generalSettings.firewallReconciliation')}
              onClick={handleFirewallReconciliation}
              loading={operationLoading === 'reconcile'}
              variant="secondary"
            />
          </div>
        </SectionCard>
      </div>
    </div>
  );
};

export default GeneralSettings;
