import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { Key, Plus, Edit2, Trash2, CheckCircle, AlertCircle, TestTube, Save, X, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';

interface AuthProvider {
  id: number;
  name: string;
  provider_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  priority: number;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface ProviderFormData {
  name: string;
  provider_type: string;
  description: string;
  enabled: boolean;
  priority: number;
  // LDAP config
  server: string;
  port: number;
  use_ssl: boolean;
  use_starttls: boolean;
  bind_dn: string;
  bind_password: string;
  user_search_base: string;
  user_search_filter: string;
  email_attribute: string;
  skip_cert_verify: boolean;
}

const PROVIDER_TYPES = [
  { value: 'local', label: 'Local' },
  { value: 'ldap', label: 'LDAP/Active Directory' },
];

const AuthProviders: React.FC = () => {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingProvider, setEditingProvider] = useState<AuthProvider | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);
  const [testLoading, setTestLoading] = useState<number | null>(null);

  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<ProviderFormData>({
    defaultValues: {
      name: '',
      provider_type: 'local',
      description: '',
      enabled: true,
      priority: 100,
      server: '',
      port: 389,
      use_ssl: false,
      use_starttls: false,
      bind_dn: '',
      bind_password: '',
      user_search_base: '',
      user_search_filter: '(sAMAccountName={username})',
      email_attribute: 'mail',
      skip_cert_verify: false,
    },
  });

  const providerType = watch('provider_type');

  useEffect(() => {
    fetchProviders();
  }, []);

  const fetchProviders = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(API_ENDPOINTS.AUTH_PROVIDERS);
      setProviders(response.data);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('authProviders.failedToLoad')));
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (data: ProviderFormData) => {
    try {
      const config: Record<string, unknown> = {};
      if (data.provider_type === 'ldap') {
        config.server = data.server;
        config.port = data.port;
        config.use_ssl = data.use_ssl;
        config.use_starttls = data.use_starttls;
        config.bind_dn = data.bind_dn;
        config.bind_password = data.bind_password;
        config.user_search_base = data.user_search_base;
        config.user_search_filter = data.user_search_filter;
        config.email_attribute = data.email_attribute;
        config.skip_cert_verify = data.skip_cert_verify;
      }

      const payload = {
        name: data.name,
        provider_type: data.provider_type,
        description: data.description,
        enabled: data.enabled,
        priority: data.priority,
        config,
      };

      if (editingProvider) {
        await apiClient.put(`${API_ENDPOINTS.AUTH_PROVIDERS}${editingProvider.id}/`, payload);
        toast.success(t('authProviders.updatedSuccessfully'));
      } else {
        await apiClient.post(API_ENDPOINTS.AUTH_PROVIDERS, payload);
        toast.success(t('authProviders.createdSuccessfully'));
      }

      setShowModal(false);
      setEditingProvider(null);
      reset();
      fetchProviders();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('authProviders.failedToSave')));
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(t('authProviders.confirmDelete', { name }))) return;
    try {
      await apiClient.delete(`${API_ENDPOINTS.AUTH_PROVIDERS}${id}/`);
      toast.success(t('authProviders.deletedSuccessfully'));
      fetchProviders();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('authProviders.failedToDelete')));
    }
  };

  const handleTest = async (id: number) => {
    setTestLoading(id);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.AUTH_PROVIDERS}${id}/test`);
      setTestResult({ id, success: response.data.success, message: response.data.message });
    } catch (err: unknown) {
      setTestResult({ id, success: false, message: getErrorMessage(err, t('authProviders.testFailed')) });
    } finally {
      setTestLoading(null);
    }
  };

  const handleOpenModal = (provider?: AuthProvider) => {
    if (provider) {
      setEditingProvider(provider);
      reset({
        name: provider.name,
        provider_type: provider.provider_type,
        description: provider.description || '',
        enabled: provider.enabled,
        priority: provider.priority,
        server: (provider.config as Record<string, unknown>).server as string || '',
        port: ((provider.config as Record<string, unknown>).port as number) || 389,
        use_ssl: (provider.config as Record<string, unknown>).use_ssl as boolean || false,
        use_starttls: (provider.config as Record<string, unknown>).use_starttls as boolean || false,
        bind_dn: (provider.config as Record<string, unknown>).bind_dn as string || '',
        bind_password: '',
        user_search_base: (provider.config as Record<string, unknown>).user_search_base as string || '',
        user_search_filter: (provider.config as Record<string, unknown>).user_search_filter as string || '(sAMAccountName={username})',
        email_attribute: (provider.config as Record<string, unknown>).email_attribute as string || 'mail',
        skip_cert_verify: (provider.config as Record<string, unknown>).skip_cert_verify as boolean || false,
      });
    } else {
      setEditingProvider(null);
      reset();
    }
    setShowModal(true);
  };

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2">
              <Key className="h-6 w-6" />
              {t('authProviders.title')}
            </h1>
            <p className="text-muted-foreground mt-1">{t('authProviders.description')}</p>
          </div>
          <PrimaryButton
            label={t('authProviders.addProvider')}
            onClick={() => handleOpenModal()}
            icon={Plus}
          />
        </div>

        {/* Providers List */}
        {loading ? (
          <div className="flex justify-center items-center py-12">
            <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="space-y-4">
            {providers.length === 0 ? (
              <div className="bg-card rounded-2xl border border-border p-8 text-center">
                <Key className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">{t('authProviders.noProviders')}</p>
                <PrimaryButton
                  label={t('authProviders.addFirstProvider')}
                  onClick={() => handleOpenModal()}
                  className="mt-4"
                />
              </div>
            ) : (
              providers.map((provider) => (
                <div key={provider.id} className="bg-card rounded-2xl border border-border overflow-hidden">
                  <div
                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => setExpandedId(expandedId === provider.id ? null : provider.id)}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                        provider.provider_type === 'ldap' ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'
                      }`}>
                        <Key className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-foreground">{provider.name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {PROVIDER_TYPES.find(p => p.value === provider.provider_type)?.label || provider.provider_type}
                          {provider.enabled ? '' : ' - '}{provider.enabled ? '' : t('common.disabled')}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleTest(provider.id); }}
                        disabled={testLoading === provider.id}
                        className="p-2 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                        title={t('authProviders.testConnection')}
                      >
                        {testLoading === provider.id ? (
                          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <TestTube className="h-4 w-4" />
                        )}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleOpenModal(provider); }}
                        className="p-2 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                        title={t('common.edit')}
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(provider.id, provider.name); }}
                        className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title={t('common.delete')}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                      {expandedId === provider.id ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </div>

                  {expandedId === provider.id && (
                    <div className="px-4 pb-4 border-t border-border">
                      <div className="pt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground">{t('authProviders.type')}</p>
                          <p className="font-medium">{PROVIDER_TYPES.find(p => p.value === provider.provider_type)?.label}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">{t('authProviders.status')}</p>
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            provider.enabled ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                          }`}>
                            {provider.enabled ? t('common.enabled') : t('common.disabled')}
                          </span>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">{t('authProviders.priority')}</p>
                          <p className="font-medium">{provider.priority}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">{t('authProviders.updatedAt')}</p>
                          <p className="font-medium">{new Date(provider.updated_at).toLocaleString()}</p>
                        </div>
                      </div>
                      {provider.description && (
                        <div className="mt-4">
                          <p className="text-xs text-muted-foreground">{t('authProviders.fieldDescription')}</p>
                          <p className="font-medium">{provider.description}</p>
                        </div>
                      )}
                      {testResult?.id === provider.id && (
                        <div className={`mt-4 p-3 rounded-lg flex items-center gap-2 ${
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
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-background rounded-2xl border border-border w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h2 className="text-lg font-semibold text-foreground">
                  {editingProvider ? t('authProviders.editProvider') : t('authProviders.addProvider')}
                </h2>
                <button
                  onClick={() => { setShowModal(false); setEditingProvider(null); reset(); }}
                  className="p-1 hover:bg-accent rounded-lg transition-colors"
                >
                  <X className="h-5 w-5 text-muted-foreground" />
                </button>
              </div>
              <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
                {/* Basic Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('authProviders.name')} <span className="text-red-500">*</span>
                    </label>
                    <input
                      {...register('name', { required: t('authProviders.nameRequired') })}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder={t('authProviders.namePlaceholder')}
                    />
                    {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('authProviders.type')} <span className="text-red-500">*</span>
                    </label>
                    <select
                      {...register('provider_type', { required: t('authProviders.typeRequired') })}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                    >
                      {PROVIDER_TYPES.map((type) => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                    {errors.provider_type && <p className="text-xs text-red-600 mt-1">{errors.provider_type.message}</p>}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('authProviders.fieldDescription')}
                  </label>
                  <textarea
                    {...register('description')}
                    rows={2}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none"
                    placeholder={t('authProviders.descriptionPlaceholder')}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <input {...register('enabled')} type="checkbox" className="rounded border-border" />
                      {t('authProviders.enabled')}
                    </label>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('authProviders.priority')}
                    </label>
                    <input
                      {...register('priority', { valueAsNumber: true })}
                      type="number"
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder="100"
                    />
                  </div>
                </div>

                {/* LDAP Config */}
                {providerType === 'ldap' && (
                  <div className="border border-border rounded-lg p-4 space-y-4">
                    <h3 className="font-medium text-foreground">{t('authProviders.ldapSettings')}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('authProviders.server')} <span className="text-red-500">*</span>
                        </label>
                        <input
                          {...register('server', { required: t('authProviders.serverRequired') })}
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="ldap.example.com"
                        />
                        {errors.server && <p className="text-xs text-red-600 mt-1">{errors.server.message}</p>}
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('authProviders.port')}
                        </label>
                        <input
                          {...register('port', { valueAsNumber: true })}
                          type="number"
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="389"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                        <input {...register('use_ssl')} type="checkbox" className="rounded border-border" />
                        {t('authProviders.useSsl')}
                      </label>
                      <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                        <input {...register('use_starttls')} type="checkbox" className="rounded border-border" />
                        {t('authProviders.useStarttls')}
                      </label>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('authProviders.bindDn')}
                      </label>
                      <input
                        {...register('bind_dn')}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="cn=admin,dc=example,dc=com"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('authProviders.bindPassword')}
                      </label>
                      <input
                        {...register('bind_password')}
                        type="password"
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="********"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('authProviders.userSearchBase')}
                      </label>
                      <input
                        {...register('user_search_base')}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="ou=users,dc=example,dc=com"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('authProviders.userSearchFilter')}
                      </label>
                      <input
                        {...register('user_search_filter')}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="(sAMAccountName={username})"
                      />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('authProviders.emailAttribute')}
                        </label>
                        <input
                          {...register('email_attribute')}
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="mail"
                        />
                      </div>
                      <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                        <input {...register('skip_cert_verify')} type="checkbox" className="rounded border-border" />
                        {t('authProviders.skipCertVerify')}
                      </label>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex justify-end gap-3 pt-4 border-t border-border">
                  <PrimaryButton
                    type="button"
                    variant="secondary"
                    label={t('common.cancel')}
                    onClick={() => { setShowModal(false); setEditingProvider(null); reset(); }}
                  />
                  <PrimaryButton
                    type="submit"
                    label={editingProvider ? t('common.save') : t('common.create')}
                    icon={Save}
                  />
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuthProviders;
