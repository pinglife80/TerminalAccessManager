import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { HardDrive, Plus, Download, RotateCcw, Trash2, Play, Settings, CheckCircle, AlertCircle, TestTube, Save } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';

interface BackupConfig {
  enabled: boolean;
  schedule: string;
  retention_days: number;
  storage_type: string;
  storage_config: Record<string, unknown>;
  backup_database: boolean;
  backup_config: boolean;
  backup_logs: boolean;
  encrypt_backup: boolean;
}

interface BackupInfo {
  filename: string;
  file_path: string;
  file_size: number;
  created_at: string;
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

const STORAGE_TYPES = [
  { value: 'local', label: 'local' },
  { value: 'sftp', label: 'sftp' },
  { value: 'ftp', label: 'ftp' },
];

const SCHEDULE_PRESETS = [
  { label: '每天凌晨2点', value: '0 2 * * *' },
  { label: '每天凌晨3点', value: '0 3 * * *' },
  { label: '每天凌晨4点', value: '0 4 * * *' },
  { label: '每周日凌晨2点', value: '0 2 * * 0' },
  { label: '每周六凌晨2点', value: '0 2 * * 6' },
  { label: '每月1号凌晨2点', value: '0 2 1 * *' },
  { label: '自定义', value: 'custom' },
];

const CRON_REGEX = /^(\*|[0-5]?\d)\s+(\*|[01]?\d|2[0-3])\s+(\*|[1-9]|[12]\d|3[01])\s+(\*|[1-9]|1[0-2])\s+(\*|[0-6])$/;

const validateCron = (value: string): boolean => {
  return CRON_REGEX.test(value.trim());
};

const Backup: React.FC = () => {
  const { t } = useTranslation();
  const [config, setConfig] = useState<BackupConfig | null>(null);
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [runningJob, setRunningJob] = useState<BackupJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('0 2 * * *');
  const [customCronError, setCustomCronError] = useState<string>('');

  const { register, handleSubmit, reset, watch, setValue } = useForm<BackupConfig>({
    defaultValues: {
      enabled: false,
      schedule: '0 2 * * *',
      retention_days: 7,
      storage_type: 'local',
      storage_config: {},
      backup_database: true,
      backup_config: true,
      backup_logs: false,
      encrypt_backup: true,
    },
  });

  const storageType = watch('storage_type');

  useEffect(() => {
    fetchConfig();
    fetchBackups();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.BACKUP_CONFIG);
      setConfig(response.data);
      reset(response.data);
      const schedule = response.data.schedule || '0 2 * * *';
      const preset = SCHEDULE_PRESETS.find(p => p.value === schedule);
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
      const response = await apiClient.post(API_ENDPOINTS.BACKUP_RUN);
      setRunningJob(response.data);
      toast.info(t('backup.backupStarted'));
      setTimeout(() => {
        fetchBackups();
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

  const handleRestore = async (filename: string) => {
    if (!confirm(t('backup.confirmRestore', { filename }))) return;
    try {
      await apiClient.post(API_ENDPOINTS.BACKUP_RESTORE.replace('{{filename}}', filename));
      toast.success(t('backup.restoredSuccessfully'));
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

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Page Header */}
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
            <PrimaryButton
              label={t('backup.runBackup')}
              onClick={handleRunBackup}
              disabled={!!runningJob}
              icon={Play}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Config Section */}
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
                    {SCHEDULE_PRESETS.map((preset) => (
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

                {/* Remote Storage Config */}
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

                {/* Backup Options */}
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
                    <input {...register('backup_logs')} type="checkbox" className="rounded border-border" />
                    {t('backup.backupLogs')}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input {...register('encrypt_backup')} type="checkbox" className="rounded border-border" />
                    {t('backup.encryptBackup')}
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

          {/* Backups List Section */}
          <div className="lg:col-span-2">
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
                  {backups.map((backup) => (
                    <div key={backup.filename} className="flex items-center justify-between p-4 bg-background rounded-xl">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                          <HardDrive className="h-5 w-5 text-blue-600" />
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{backup.filename}</p>
                          <p className="text-sm text-muted-foreground">
                            {formatFileSize(backup.file_size)} - {new Date(backup.created_at).toLocaleString()}
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
                          onClick={() => handleRestore(backup.filename)}
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
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Backup;
