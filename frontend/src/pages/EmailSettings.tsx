import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';
import {
  Mail, Save, Send, Loader2, Eye, EyeOff,
} from 'lucide-react';
import { useSettings, type EmailConfig } from '@/hooks/useTerminalData';
import { getErrorMessage } from '@/lib/utils';

interface EmailFormState {
  email_enabled: boolean;
  email_host: string;
  email_port: number;
  email_use_tls: boolean;
  email_use_ssl: boolean;
  email_username: string;
  email_password: string;
  email_from: string;
  email_from_name: string;
  email_rate_limit: number;
}

const DEFAULT_FORM: EmailFormState = {
  email_enabled: false,
  email_host: '',
  email_port: 465,
  email_use_tls: false,
  email_use_ssl: true,
  email_username: '',
  email_password: '',
  email_from: '',
  email_from_name: 'TAM System',
  email_rate_limit: 10,
};

function configToForm(cfg: EmailConfig | undefined): EmailFormState {
  if (!cfg) return { ...DEFAULT_FORM };
  return {
    email_enabled: cfg.email_enabled,
    email_host: cfg.email_host || '',
    email_port: cfg.email_port || 465,
    email_use_tls: cfg.email_use_tls,
    email_use_ssl: cfg.email_use_ssl,
    email_username: cfg.email_username || '',
    email_password: cfg.email_password || '',
    email_from: cfg.email_from || '',
    email_from_name: cfg.email_from_name || 'TAM System',
    email_rate_limit: cfg.email_rate_limit || 10,
  };
}

function formToUpdates(form: EmailFormState) {
  return [
    { key: 'email_enabled', value: form.email_enabled ? 'true' : 'false' },
    { key: 'email_host', value: form.email_host },
    { key: 'email_port', value: String(form.email_port) },
    { key: 'email_use_tls', value: form.email_use_tls ? 'true' : 'false' },
    { key: 'email_use_ssl', value: form.email_use_ssl ? 'true' : 'false' },
    { key: 'email_username', value: form.email_username },
    { key: 'email_password', value: form.email_password },
    { key: 'email_from', value: form.email_from },
    { key: 'email_from_name', value: form.email_from_name },
    { key: 'email_rate_limit', value: String(form.email_rate_limit) },
  ];
}

const EmailSettings: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: configs, isLoading } = useSettings();

  const [form, setForm] = useState<EmailFormState>({ ...DEFAULT_FORM });
  const [original, setOriginal] = useState<EmailFormState>({ ...DEFAULT_FORM });
  const [saving, setSaving] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    const next = configToForm(configs?.email);
    setForm(next);
    setOriginal(next);
  }, [configs]);

  const hasChanges = JSON.stringify(form) !== JSON.stringify(original);

  const updateField = <K extends keyof EmailFormState>(key: K, value: EmailFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setLocalError(null);
  };

  const handleSave = async () => {
    if (form.email_use_tls && form.email_use_ssl) {
      setLocalError(t('emailSettings.errorTlsSslMutuallyExclusive'));
      return;
    }
    if (form.email_enabled && !form.email_host) {
      setLocalError(t('emailSettings.errorHostRequired'));
      return;
    }
    setSaving(true);
    setLocalError(null);
    try {
      await apiClient.put('/settings/update', formToUpdates(form));
      setOriginal({ ...form });
      toast.success(t('emailSettings.saveSuccess'));
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    } catch (err) {
      setLocalError(getErrorMessage(err));
      toast.error(t('emailSettings.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleTestSend = async () => {
    if (!testEmail) {
      setTestResult({ success: false, message: t('emailSettings.errorTestEmailRequired') });
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const response = await apiClient.post('/settings/email/test', null, {
        params: { email: testEmail },
      });
      const data = response.data;
      setTestResult({ success: data.success, message: data.message });
      if (data.success) {
        toast.success(data.message);
      } else {
        toast.error(data.message);
      }
    } catch (err) {
      const msg = getErrorMessage(err);
      setTestResult({ success: false, message: msg });
      toast.error(msg);
    } finally {
      setTesting(false);
    }
  };

  const inputClass = 'w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-60 disabled:cursor-not-allowed';
  const labelClass = 'block text-sm font-medium text-foreground mb-1';

  if (isLoading) {
    return (
      <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-4xl mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2">
              <Mail className="h-6 w-6" />
              {t('emailSettings.title')}
            </h1>
            <p className="text-muted-foreground mt-1">{t('emailSettings.description')}</p>
          </div>
          <PrimaryButton
            icon={Save}
            label={t('common.save')}
            onClick={handleSave}
            loading={saving}
            disabled={!hasChanges}
          />
        </div>

        {/* Inline Error */}
        {localError && (
          <div className="mb-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            {localError}
          </div>
        )}

        {/* SMTP Configuration */}
        <div className="bg-card rounded-lg border border-border shadow-sm">
          <div className="flex items-center justify-between p-4 sm:p-5 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-md bg-primary/10 text-primary-600">
                <Mail className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-foreground">{t('emailSettings.smtpConfig')}</h3>
                <p className="text-sm text-muted-foreground">{t('emailSettings.smtpConfigDesc')}</p>
              </div>
            </div>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.email_enabled}
                onChange={(e) => updateField('email_enabled', e.target.checked)}
                className="h-4 w-4 rounded border-input text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-muted-foreground">
                {form.email_enabled ? t('common.enabled') : t('common.disabled')}
              </span>
            </label>
          </div>

          <div className="p-4 sm:p-5 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className={labelClass}>{t('emailSettings.smtpHost')}</label>
                <input
                  type="text"
                  value={form.email_host}
                  onChange={(e) => updateField('email_host', e.target.value)}
                  placeholder="smtp.example.com"
                  className={inputClass}
                />
                <p className="mt-1 text-xs text-muted-foreground">{t('emailSettings.smtpHostHint')}</p>
              </div>
              <div>
                <label className={labelClass}>{t('emailSettings.smtpPort')}</label>
                <input
                  type="number"
                  value={form.email_port}
                  onChange={(e) => updateField('email_port', Number(e.target.value))}
                  className={inputClass}
                />
                <p className="mt-1 text-xs text-muted-foreground">{t('emailSettings.smtpPortHint')}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className={labelClass}>{t('emailSettings.smtpUsername')}</label>
                <input
                  type="text"
                  value={form.email_username}
                  onChange={(e) => updateField('email_username', e.target.value)}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>{t('emailSettings.smtpPassword')}</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={form.email_password}
                    onChange={(e) => updateField('email_password', e.target.value)}
                    placeholder={t('emailSettings.smtpPasswordPlaceholder')}
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
                    aria-label={showPassword ? t('emailSettings.hidePassword') : t('emailSettings.showPassword')}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{t('emailSettings.smtpPasswordHint')}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className={labelClass}>{t('emailSettings.encryption')}</label>
                <div className="flex gap-6 pt-2">
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="encryption"
                      checked={form.email_use_ssl && !form.email_use_tls}
                      onChange={() => {
                        updateField('email_use_ssl', true);
                        updateField('email_use_tls', false);
                      }}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm">SSL</span>
                  </label>
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="encryption"
                      checked={form.email_use_tls && !form.email_use_ssl}
                      onChange={() => {
                        updateField('email_use_tls', true);
                        updateField('email_use_ssl', false);
                      }}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm">STARTTLS</span>
                  </label>
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="encryption"
                      checked={!form.email_use_ssl && !form.email_use_tls}
                      onChange={() => {
                        updateField('email_use_ssl', false);
                        updateField('email_use_tls', false);
                      }}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm">None</span>
                  </label>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{t('emailSettings.encryptionHint')}</p>
              </div>
              <div>
                <label className={labelClass}>{t('emailSettings.rateLimit')}</label>
                <input
                  type="number"
                  value={form.email_rate_limit}
                  onChange={(e) => updateField('email_rate_limit', Number(e.target.value))}
                  className={inputClass}
                />
                <p className="mt-1 text-xs text-muted-foreground">{t('emailSettings.rateLimitHint')}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Sender Configuration */}
        <div className="bg-card rounded-lg border border-border shadow-sm mt-4">
          <div className="p-4 sm:p-5 border-b border-border">
            <h3 className="text-base font-semibold text-foreground">{t('emailSettings.senderConfig')}</h3>
            <p className="text-sm text-muted-foreground">{t('emailSettings.senderConfigDesc')}</p>
          </div>
          <div className="p-4 sm:p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>{t('emailSettings.fromEmail')}</label>
              <input
                type="email"
                value={form.email_from}
                onChange={(e) => updateField('email_from', e.target.value)}
                placeholder="noreply@example.com"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass}>{t('emailSettings.fromName')}</label>
              <input
                type="text"
                value={form.email_from_name}
                onChange={(e) => updateField('email_from_name', e.target.value)}
                placeholder="TAM System"
                className={inputClass}
              />
            </div>
          </div>
        </div>

        {/* Test Send */}
        <div className="bg-card rounded-lg border border-border shadow-sm mt-4">
          <div className="p-4 sm:p-5 border-b border-border">
            <h3 className="text-base font-semibold text-foreground">{t('emailSettings.testSend')}</h3>
            <p className="text-sm text-muted-foreground">{t('emailSettings.testSendDesc')}</p>
          </div>
          <div className="p-4 sm:p-5">
            <div className="flex gap-3">
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder={t('emailSettings.testEmailPlaceholder')}
                className={inputClass}
              />
              <PrimaryButton
                icon={Send}
                label={t('emailSettings.sendTest')}
                onClick={handleTestSend}
                loading={testing}
                disabled={!testEmail || testing}
              />
            </div>
            {testResult && (
              <div
                className={`mt-3 rounded-md border p-3 text-sm ${
                  testResult.success
                    ? 'border-green-300 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-200'
                    : 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200'
                }`}
              >
                {testResult.message}
              </div>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              {t('emailSettings.testSendNote')}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmailSettings;
