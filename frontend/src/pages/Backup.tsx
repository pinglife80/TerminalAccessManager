import React, { useState, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { formatDate, getErrorMessage } from '@/lib/utils';
import { HardDrive, Plus, Download, RotateCcw, Trash2, Play, Settings, CheckCircle, AlertCircle, TestTube, Save, X } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';
import { Pagination } from '@/components/Pagination';

interface BackupConfig {
  enabled: boolean;
  schedule: string;
  retention_days: number;
  storage_type: string;
  storage_config: Record<string, unknown>;
  backup_database: boolean;
  backup_config: boolean;
  backup_whitelist: boolean;
  backup_logs: boolean;
  encrypt_backup: boolean;
}

interface BackupInfo {
  filename: string;
  file_path?: string;
  file_size?: number;
  created_at?: string;
  storage: string;
}

interface BackupJob {
  id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  file_path?: string;
  file_size?: number;
  checksum?: string;
  error_message?: string;
}

interface BackupContentInfo {
  filename: string;
  file_size: number;
  compress_size: number;
}

interface BackupContents {
  filename: string;
  file_size: number;
  created_at: string;
  contents: BackupContentInfo[];
}

const STORAGE_TYPES = [
  { value: 'local', label: 'local' },
  { value: 'sftp', label: 'sftp' },
  { value: 'ftp', label: 'ftp' },
];

const BACKUP_TYPES = [
  { value: 'full', label: 'full' },
  { value: 'database', label: 'database' },
  { value: 'config', label: 'config' },
  { value: 'whitelist', label: 'whitelist' },
  { value: 'logs', label: 'logs' },
];

const CRON_REGEX = /^(\*|[0-5]?\d)\s+(\*|[01]?\d|2[0-3])\s+(\*|[1-9]|[12]\d|3[01])\s+(\*|[1-9]|1[0-2])\s+(\*|[0-6])$/;

const validateCron = (value: string): boolean => {
  return CRON_REGEX.test(value.trim());
};

const Backup: React.FC = () => {
  const { t } = useTranslation();
  const schedulePresets = useMemo(() => [
    { label: t('backup.schedulePresets.daily2am'), value: '0 2 * * *' },
    { label: t('backup.schedulePresets.daily3am'), value: '0 3 * * *' },
    { label: t('backup.schedulePresets.daily4am'), value: '0 4 * * *' },
    { label: t('backup.schedulePresets.weeklySunday2am'), value: '0 2 * * 0' },
    { label: t('backup.schedulePresets.weeklySaturday2am'), value: '0 2 * * 6' },
    { label: t('backup.schedulePresets.monthly1st2am'), value: '0 2 1 * *' },
    { label: t('backup.schedulePresets.custom'), value: 'custom' },
  ], [t]);
  const [config, setConfig] = useState<BackupConfig | null>(null);
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [whitelistBackups, setWhitelistBackups] = useState<BackupInfo[]>([]);
  const [runningJob, setRunningJob] = useState<BackupJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('0 2 * * *');
  const [customCronError, setCustomCronError] = useState<string>('');
  const [selectedBackupType, setSelectedBackupType] = useState<string>('full');
  const [showRestoreModal, setShowRestoreModal] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<string | null>(null);
  const [restoreContents, setRestoreContents] = useState<BackupContents | null>(null);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [isWhitelistRestore, setIsWhitelistRestore] = useState(false);
  const [backupPage, setBackupPage] = useState(1);
  const [backupPageSize, setBackupPageSize] = useState(10);
  const [whitelistPage, setWhitelistPage] = useState(1);
  const [whitelistPageSize, setWhitelistPageSize] = useState(10);

  const { register, handleSubmit, reset, watch, setValue } = useForm<BackupConfig>({
    defaultValues: {
      enabled: false,
      schedule: '0 2 * * *',
      retention_days: 7,
      storage_type: 'local',
      storage_config: {},
      backup_database: true,
      backup_config: true,
      backup_whitelist: true,
      backup_logs: false,
    },
  });

  const storageType = watch('storage_type');

  useEffect(() => {
    fetchConfig();
    fetchBackups();
    fetchWhitelistBackups();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.BACKUP_CONFIG);
      setConfig(response.data);
      reset(response.data);
      const schedule = response.data.schedule || '0 2 * * *';
      const preset = schedulePresets.find(p => p.value === schedule);
      setSelectedPreset(preset ? schedule : 'custom');
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToLoadConfig')));
    }
  };

  const fetchBackups = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(API_ENDPOINTS.BACKUP_LIST);
      setBackups(response.data.backups || []);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToLoadBackups')));
    } finally {
      setLoading(false);
    }
  };

  const fetchWhitelistBackups = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.BACKUP_WHITELIST_LIST);
      setWhitelistBackups(response.data.backups || []);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToLoadBackups')));
    }
  };

  const onSubmit = async (data: BackupConfig) => {
    try {
      await apiClient.put(API_ENDPOINTS.BACKUP_CONFIG, data);
      setConfig(data);
      toast.success(t('backup.configUpdated'));
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToUpdateConfig')));
    }
  };

  const handleRunBackup = async () => {
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.BACKUP_RUN}?backup_type=${selectedBackupType}`);
      setRunningJob(response.data);
      toast.info(t('backup.backupStarted'));
      setTimeout(() => {
        fetchBackups();
        if (selectedBackupType === 'whitelist') {
          fetchWhitelistBackups();
        }
        setRunningJob(null);
      }, 5000);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToRunBackup')));
    }
  };

  const handleCreateWhitelistBackup = async () => {
    try {
      const response = await apiClient.post(API_ENDPOINTS.BACKUP_WHITELIST);
      setRunningJob(response.data);
      toast.info(t('backup.backupStarted'));
      setTimeout(() => {
        fetchWhitelistBackups();
        setRunningJob(null);
      }, 5000);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToRunBackup')));
    }
  };

  const handleDownload = async (filename: string) => {
    try {
      const response = await apiClient.get(
        API_ENDPOINTS.BACKUP_DOWNLOAD.replace('{{filename}}', filename),
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToDownload')));
    }
  };

  const handleRestore = async (filename: string, isWhitelist = false) => {
    setRestoreTarget(filename);
    setIsWhitelistRestore(isWhitelist);
    setRestoreLoading(true);
    try {
      const response = await apiClient.get(API_ENDPOINTS.BACKUP_CONTENTS.replace('{{filename}}', filename));
      setRestoreContents(response.data);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToLoadBackups')));
    } finally {
      setRestoreLoading(false);
      setShowRestoreModal(true);
    }
  };

  const executeRestore = async (filename: string, isWhitelist = false) => {
    try {
      if (isWhitelist) {
        await apiClient.post(API_ENDPOINTS.BACKUP_WHITELIST_RESTORE.replace('{{filename}}', filename));
      } else {
        await apiClient.post(API_ENDPOINTS.BACKUP_RESTORE.replace('{{filename}}', filename));
      }
      toast.success(t('backup.restoredSuccessfully'));
      setShowRestoreModal(false);
      setRestoreTarget(null);
      setRestoreContents(null);
      fetchBackups();
      fetchWhitelistBackups();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToRestore')));
    }
  };

  const handleDelete = async (filename: string) => {
    if (!confirm(t('backup.confirmDelete', { filename }))) return;
    try {
      await apiClient.delete(API_ENDPOINTS.BACKUP_DELETE.replace('{{filename}}', filename));
      toast.success(t('backup.deletedSuccessfully'));
      fetchBackups();
      fetchWhitelistBackups();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('backup.failedToDelete')));
    }
  };

  const handleTest = async () => {
    setTestLoading(true);
    try {
      const response = await apiClient.post(API_ENDPOINTS.BACKUP_TEST);
      setTestResult({ success: response.data.success, message: response.data.message });
    } catch (err: unknown) {
      setTestResult({ success: false, message: getErrorMessage(err, t('backup.testFailed')) });
    } finally {
      setTestLoading(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const backupTotalPages = Math.max(1, Math.ceil(backups.length / backupPageSize));
  const pagedBackups = backups.slice((backupPage - 1) * backupPageSize, backupPage * backupPageSize);
  const whitelistTotalPages = Math.max(1, Math.ceil(whitelistBackups.length / whitelistPageSize));
  const pagedWhitelistBackups = whitelistBackups.slice(
    (whitelistPage - 1) * whitelistPageSize,
    whitelistPage * whitelistPageSize,
  );

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2">
              <HardDrive className="h-6 w-6" />
              {t('backup.title')}
            </h1>
            <p className="text-muted-foreground mt-1">{t('backup.description')}</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleTest}
              disabled={testLoading}
              className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg text-muted-foreground hover:text-blue-600 hover:border-blue-500 transition-colors"
            >
              {testLoading ? (
                <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              ) : (
                <TestTube className="h-4 w-4" />
              )}
              {t('backup.testConfig')}
            </button>
            <div className="flex items-center gap-2">
              <select
                value={selectedBackupType}
                onChange={(e) => setSelectedBackupType(e.target.value)}
                className="px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              >
                {BACKUP_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {t(`backup.backupType.${type.value}`)}
                  </option>
                ))}
              </select>
              <PrimaryButton
                label={t('backup.runBackup')}
                onClick={handleRunBackup}
                disabled={!!runningJob}
                icon={Play}
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <div className="bg-card rounded-2xl border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <Settings className="h-5 w-5 text-muted-foreground" />
                {t('backup.settings')}
              </h2>
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <input {...register('enabled')} type="checkbox" className="rounded border-border" />
                    {t('backup.enabled')}
                  </label>
                  {config?.enabled && (
                    <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded-full">
                      {t('common.enabled')}
                    </span>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('backup.schedule')}
                  </label>
                  <select
                    value={selectedPreset}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                    onChange={(e) => {
                      setSelectedPreset(e.target.value);
                      if (e.target.value !== 'custom') {
                        setValue('schedule', e.target.value);
                        setCustomCronError('');
                      }
                    }}
                  >
                    {schedulePresets.map((preset) => (
                      <option key={preset.value} value={preset.value}>{preset.label}</option>
                    ))}
                  </select>
                  {selectedPreset === 'custom' && (
                    <>
                      <input
                        {...register('schedule')}
                        className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-blue-500 outline-none mt-2 ${
                          customCronError ? 'border-red-500 focus:border-red-500' : 'border-border focus:border-blue-500'
                        }`}
                        placeholder="0 2 * * *"
                        onBlur={(e) => {
                          const value = e.target.value.trim();
                          if (!value) {
                            setCustomCronError(t('backup.cronRequired'));
                          } else if (!validateCron(value)) {
                            setCustomCronError(t('backup.cronInvalid'));
                          } else {
                            setCustomCronError('');
                          }
                        }}
                      />
                      {customCronError && (
                        <p className="text-xs text-red-500 mt-1">{customCronError}</p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">{t('backup.cronHint')}</p>
                    </>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('backup.retentionDays')}
                  </label>
                  <input
                    {...register('retention_days', { valueAsNumber: true })}
                    type="number"
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('backup.storageType')}
                  </label>
                  <select
                    {...register('storage_type')}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  >
                    {STORAGE_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>{t(`backup.${type.label}`)}</option>
                    ))}
                  </select>
                </div>

                {(storageType === 'sftp' || storageType === 'ftp') && (
                  <div className="border border-border rounded-lg p-4 space-y-3">
                    <h3 className="font-medium text-foreground text-sm">{t('backup.remoteSettings')}</h3>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">{t('backup.host')}</label>
                      <input
                        {...register('storage_config.host' as any)}
                        className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="backup.example.com"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">{t('backup.port')}</label>
                        <input
                          {...register('storage_config.port' as any, { valueAsNumber: true })}
                          type="number"
                          className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder={storageType === 'sftp' ? '22' : '21'}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-muted-foreground mb-1">{t('backup.username')}</label>
                        <input
                          {...register('storage_config.username' as any)}
                          className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="backup"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">{t('backup.password')}</label>
                      <input
                        {...register('storage_config.password' as any)}
                        type="password"
                        className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="********"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-muted-foreground mb-1">{t('backup.remotePath')}</label>
                      <input
                        {...register('storage_config.path' as any)}
                        className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="/backups/tam"
                      />
                    </div>
                    {storageType === 'ftp' && (
                      <label className="flex items-center gap-2 text-sm text-muted-foreground">
                        <input {...register('storage_config.use_ssl' as any)} type="checkbox" className="rounded border-border" />
                        {t('backup.useSsl')}
                      </label>
                    )}
                  </div>
                )}

                <div className="space-y-2">
                  <h3 className="font-medium text-foreground text-sm">{t('backup.backupOptions')}</h3>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input {...register('backup_database')} type="checkbox" className="rounded border-border" />
                    {t('backup.backupDatabase')}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input {...register('backup_config')} type="checkbox" className="rounded border-border" />
                    {t('backup.backupConfig')}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input {...register('backup_whitelist')} type="checkbox" className="rounded border-border" />
                    {t('backup.backupWhitelist')}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input {...register('backup_logs')} type="checkbox" className="rounded border-border" />
                    {t('backup.backupLogs')}
                  </label>
                </div>

                {testResult && (
                  <div className={`p-3 rounded-lg flex items-center gap-2 ${
                    testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                  }`}>
                    {testResult.success ? (
                      <CheckCircle className="h-4 w-4" />
                    ) : (
                      <AlertCircle className="h-4 w-4" />
                    )}
                    <span className="text-sm">{testResult.message}</span>
                  </div>
                )}

                <PrimaryButton
                  type="submit"
                  label={t('common.save')}
                  icon={Save}
                />
              </form>
            </div>
          </div>

          <div className="lg:col-span-2 space-y-6">
            <div className="bg-card rounded-2xl border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-muted-foreground" />
                {t('backup.backupList')}
                {runningJob && (
                  <span className="ml-auto text-sm text-blue-600 flex items-center gap-1">
                    <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                    {t('backup.running')}
                  </span>
                )}
              </h2>

              {loading ? (
                <div className="flex justify-center items-center py-12">
                  <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : backups.length === 0 ? (
                <div className="text-center py-12">
                  <HardDrive className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">{t('backup.noBackups')}</p>
                  <PrimaryButton
                    label={t('backup.createFirstBackup')}
                    onClick={handleRunBackup}
                    className="mt-4"
                    icon={Plus}
                  />
                </div>
              ) : (
                <div className="space-y-3">
                  {pagedBackups.map((backup) => (
                    <div key={backup.filename} className="flex items-center justify-between p-4 bg-background rounded-xl">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                          <HardDrive className="h-5 w-5 text-blue-600" />
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{backup.filename}</p>
                          <p className="text-sm text-muted-foreground">
                            {backup.file_size !== undefined ? formatFileSize(backup.file_size) : '-'}
                            {' - '}
                            {formatDate(backup.created_at)}
                            {' - '}
                            <span className={backup.storage === 'remote' ? 'text-blue-500' : 'text-gray-500'}>
                              {t(`backup.storageLocation.${backup.storage}`)}
                            </span>
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleDownload(backup.filename)}
                          className="p-2 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title={t('common.download')}
                        >
                          <Download className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleRestore(backup.filename, false)}
                          className="p-2 text-muted-foreground hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          title={t('backup.restore')}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(backup.filename)}
                          className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title={t('common.delete')}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {backups.length > 0 && (
                <Pagination
                  currentPage={backupPage}
                  totalPages={backupTotalPages}
                  onPageChange={setBackupPage}
                  pageSize={backupPageSize}
                  onPageSizeChange={(size) => { setBackupPageSize(size); setBackupPage(1); }}
                  totalItems={backups.length}
                  variant="bottom"
                />
              )}
            </div>

            <div className="bg-card rounded-2xl border border-border p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <HardDrive className="h-5 w-5 text-muted-foreground" />
                  {t('backup.whitelistBackup.title')}
                </h2>
                <PrimaryButton
                  label={t('backup.whitelistBackup.createWhitelistBackup')}
                  onClick={handleCreateWhitelistBackup}
                  disabled={!!runningJob}
                  icon={Plus}
                  size="sm"
                />
              </div>

              {whitelistBackups.length === 0 ? (
                <div className="text-center py-8">
                  <HardDrive className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground text-sm">{t('backup.noBackups')}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {pagedWhitelistBackups.map((backup) => (
                    <div key={backup.filename} className="flex items-center justify-between p-4 bg-background rounded-xl">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                          <HardDrive className="h-5 w-5 text-green-600" />
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{backup.filename}</p>
                          <p className="text-sm text-muted-foreground">
                            {backup.file_size !== undefined ? formatFileSize(backup.file_size) : '-'}
                            {' - '}
                            {formatDate(backup.created_at)}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleDownload(backup.filename)}
                          className="p-2 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title={t('common.download')}
                        >
                          <Download className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleRestore(backup.filename, true)}
                          className="p-2 text-muted-foreground hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          title={t('backup.restore')}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(backup.filename)}
                          className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title={t('common.delete')}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {whitelistBackups.length > 0 && (
                <Pagination
                  currentPage={whitelistPage}
                  totalPages={whitelistTotalPages}
                  onPageChange={setWhitelistPage}
                  pageSize={whitelistPageSize}
                  onPageSizeChange={(size) => { setWhitelistPageSize(size); setWhitelistPage(1); }}
                  totalItems={whitelistBackups.length}
                  variant="bottom"
                />
              )}
            </div>
          </div>
        </div>

        {showRestoreModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-card rounded-2xl border border-border w-full max-w-md max-h-[80vh] overflow-hidden">
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground">{t('backup.restoreConfirm.title')}</h3>
                <button
                  onClick={() => {
                    setShowRestoreModal(false);
                    setRestoreTarget(null);
                    setRestoreContents(null);
                  }}
                  className="p-1 hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="h-5 w-5 text-muted-foreground" />
                </button>
              </div>
              <div className="p-4 overflow-y-auto">
                {restoreLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="w-6 h-6 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : restoreContents && (
                  <>
                    <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 mb-4">
                      <AlertCircle className="h-4 w-4 text-warning inline mr-2" />
                      <span className="text-sm text-warning">{t('backup.restoreConfirm.warning')}</span>
                    </div>

                    <div className="mb-4">
                      <p className="text-sm font-medium text-foreground mb-2">{t('backup.backupContents.title')}</p>
                      <div className="bg-background rounded-lg p-3 space-y-2 max-h-48 overflow-y-auto">
                        {restoreContents.contents.map((content) => (
                          <div key={content.filename} className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">{content.filename}</span>
                            <span className="text-muted-foreground">{formatFileSize(content.file_size)}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">{t('backup.backupContents.filename')}</span>
                        <span className="text-foreground">{restoreContents.filename}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">{t('backup.size')}</span>
                        <span className="text-foreground">{formatFileSize(restoreContents.file_size)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">{t('backup.lastBackup')}</span>
                        <span className="text-foreground">{formatDate(restoreContents.created_at)}</span>
                      </div>
                    </div>
                  </>
                )}
              </div>
              <div className="flex items-center justify-end gap-3 p-4 border-t border-border">
                <button
                  onClick={() => {
                    setShowRestoreModal(false);
                    setRestoreTarget(null);
                    setRestoreContents(null);
                  }}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('backup.restoreConfirm.cancel')}
                </button>
                <PrimaryButton
                  label={t('backup.restoreConfirm.confirm')}
                  onClick={() => restoreTarget && executeRestore(restoreTarget, isWhitelistRestore)}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Backup;
