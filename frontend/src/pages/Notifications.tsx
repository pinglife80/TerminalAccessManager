import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { Bell, Plus, Edit2, Trash2, CheckCircle, AlertCircle, TestTube, Save, X, Mail, Link2, MessageCircle } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';

interface NotificationChannel {
  id: number;
  name: string;
  channel_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface ChannelFormData {
  name: string;
  channel_type: string;
  description: string;
  enabled: boolean;
  // Email config
  smtp_server: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  smtp_use_ssl: boolean;
  default_from: string;
  // Webhook config
  webhook_url: string;
  webhook_secret: string;
  // Feishu/DingTalk/WeCom config
  bot_webhook_url: string;
}

const CHANNEL_TYPES = [
  { value: 'email', label: 'Email', icon: Mail },
  { value: 'webhook', label: 'Webhook', icon: Link2 },
  { value: 'feishu', label: 'Feishu', icon: MessageCircle },
  { value: 'dingtalk', label: 'DingTalk', icon: MessageCircle },
  { value: 'wecom', label: 'WeCom', icon: MessageCircle },
];

const Notifications: React.FC = () => {
  const { t } = useTranslation();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);
  const [testLoading, setTestLoading] = useState<number | null>(null);
  const [eventTypes, setEventTypes] = useState<{ id: string; name: string; description: string }[]>([]);

  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<ChannelFormData>({
    defaultValues: {
      name: '',
      channel_type: 'email',
      description: '',
      enabled: true,
      smtp_server: '',
      smtp_port: 587,
      smtp_username: '',
      smtp_password: '',
      smtp_use_ssl: false,
      default_from: '',
      webhook_url: '',
      webhook_secret: '',
      bot_webhook_url: '',
    },
  });

  const channelType = watch('channel_type');

  useEffect(() => {
    fetchChannels();
    fetchEventTypes();
  }, []);

  const fetchChannels = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_CHANNELS);
      setChannels(response.data);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notifications.failedToLoad')));
    } finally {
      setLoading(false);
    }
  };

  const fetchEventTypes = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_EVENTS);
      setEventTypes(response.data.events || []);
    } catch (err: unknown) {
      console.error('Failed to load event types:', err);
    }
  };

  const onSubmit = async (data: ChannelFormData) => {
    try {
      const config: Record<string, unknown> = {};
      
      if (data.channel_type === 'email') {
        config.smtp_server = data.smtp_server;
        config.smtp_port = data.smtp_port;
        config.smtp_username = data.smtp_username;
        config.smtp_password = data.smtp_password;
        config.smtp_use_ssl = data.smtp_use_ssl;
        config.default_from = data.default_from;
      } else if (data.channel_type === 'webhook') {
        config.url = data.webhook_url;
        config.secret = data.webhook_secret;
      } else {
        config.webhook_url = data.bot_webhook_url;
      }

      const payload = {
        name: data.name,
        channel_type: data.channel_type,
        description: data.description,
        enabled: data.enabled,
        config,
      };

      if (editingChannel) {
        await apiClient.put(`${API_ENDPOINTS.NOTIFICATION_CHANNELS}${editingChannel.id}/`, payload);
        toast.success(t('notifications.updatedSuccessfully'));
      } else {
        await apiClient.post(API_ENDPOINTS.NOTIFICATION_CHANNELS, payload);
        toast.success(t('notifications.createdSuccessfully'));
      }

      setShowModal(false);
      setEditingChannel(null);
      reset();
      fetchChannels();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notifications.failedToSave')));
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(t('notifications.confirmDelete', { name }))) return;
    try {
      await apiClient.delete(`${API_ENDPOINTS.NOTIFICATION_CHANNELS}${id}/`);
      toast.success(t('notifications.deletedSuccessfully'));
      fetchChannels();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notifications.failedToDelete')));
    }
  };

  const handleTest = async (id: number) => {
    setTestLoading(id);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.NOTIFICATION_CHANNELS}${id}/test`);
      setTestResult({ id, success: response.data.success, message: response.data.message });
    } catch (err: unknown) {
      setTestResult({ id, success: false, message: getErrorMessage(err, t('notifications.testFailed')) });
    } finally {
      setTestLoading(null);
    }
  };

  const handleOpenModal = (channel?: NotificationChannel) => {
    if (channel) {
      setEditingChannel(channel);
      reset({
        name: channel.name,
        channel_type: channel.channel_type,
        description: channel.description || '',
        enabled: channel.enabled,
        smtp_server: (channel.config as Record<string, unknown>).smtp_server as string || '',
        smtp_port: ((channel.config as Record<string, unknown>).smtp_port as number) || 587,
        smtp_username: (channel.config as Record<string, unknown>).smtp_username as string || '',
        smtp_password: '',
        smtp_use_ssl: (channel.config as Record<string, unknown>).smtp_use_ssl as boolean || false,
        default_from: (channel.config as Record<string, unknown>).default_from as string || '',
        webhook_url: (channel.config as Record<string, unknown>).url as string || '',
        webhook_secret: (channel.config as Record<string, unknown>).secret as string || '',
        bot_webhook_url: (channel.config as Record<string, unknown>).webhook_url as string || '',
      });
    } else {
      setEditingChannel(null);
      reset();
    }
    setShowModal(true);
  };

  const getChannelIcon = (type: string) => {
    const channel = CHANNEL_TYPES.find(c => c.value === type);
    return channel?.icon || Bell;
  };

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2">
              <Bell className="h-6 w-6" />
              {t('notifications.title')}
            </h1>
            <p className="text-muted-foreground mt-1">{t('notifications.description')}</p>
          </div>
          <PrimaryButton
            label={t('notifications.addChannel')}
            onClick={() => handleOpenModal()}
            icon={Plus}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Channels List */}
          <div className="lg:col-span-2">
            <div className="bg-card rounded-2xl border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <Bell className="h-5 w-5 text-muted-foreground" />
                {t('notifications.channels')}
              </h2>

              {loading ? (
                <div className="flex justify-center items-center py-12">
                  <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : channels.length === 0 ? (
                <div className="text-center py-12">
                  <Bell className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">{t('notifications.noChannels')}</p>
                  <PrimaryButton
                    label={t('notifications.addFirstChannel')}
                    onClick={() => handleOpenModal()}
                    className="mt-4"
                  />
                </div>
              ) : (
                <div className="space-y-3">
                  {channels.map((channel) => {
                    const Icon = getChannelIcon(channel.channel_type);
                    return (
                      <div key={channel.id} className="bg-background rounded-xl p-4 border border-border">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                              channel.channel_type === 'email' ? 'bg-blue-100 text-blue-600' :
                              channel.channel_type === 'webhook' ? 'bg-green-100 text-green-600' :
                              'bg-purple-100 text-purple-600'
                            }`}>
                              <Icon className="h-5 w-5" />
                            </div>
                            <div>
                              <h3 className="font-semibold text-foreground">{channel.name}</h3>
                              <p className="text-sm text-muted-foreground">
                                {CHANNEL_TYPES.find(c => c.value === channel.channel_type)?.label}
                                {channel.enabled ? '' : ' - '}{channel.enabled ? '' : t('common.disabled')}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleTest(channel.id)}
                              disabled={testLoading === channel.id}
                              className="p-2 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                              title={t('notifications.testChannel')}
                            >
                              {testLoading === channel.id ? (
                                <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                              ) : (
                                <TestTube className="h-4 w-4" />
                              )}
                            </button>
                            <button
                              onClick={() => handleOpenModal(channel)}
                              className="p-2 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                              title={t('common.edit')}
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(channel.id, channel.name)}
                              className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                              title={t('common.delete')}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                        {channel.description && (
                          <p className="text-sm text-muted-foreground mt-3">{channel.description}</p>
                        )}
                        {testResult?.id === channel.id && (
                          <div className={`mt-3 p-3 rounded-lg flex items-center gap-2 ${
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
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Event Types */}
          <div className="lg:col-span-1">
            <div className="bg-card rounded-2xl border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <Bell className="h-5 w-5 text-muted-foreground" />
                {t('notifications.eventTypes')}
              </h2>
              <div className="space-y-3">
                {eventTypes.map((event) => (
                  <div key={event.id} className="bg-background rounded-lg p-3">
                    <p className="font-medium text-foreground text-sm">{event.name}</p>
                    <p className="text-xs text-muted-foreground mt-1">{event.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-background rounded-2xl border border-border w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h2 className="text-lg font-semibold text-foreground">
                  {editingChannel ? t('notifications.editChannel') : t('notifications.addChannel')}
                </h2>
                <button
                  onClick={() => { setShowModal(false); setEditingChannel(null); reset(); }}
                  className="p-1 hover:bg-accent rounded-lg transition-colors"
                >
                  <X className="h-5 w-5 text-muted-foreground" />
                </button>
              </div>
              <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('notifications.name')} <span className="text-red-500">*</span>
                    </label>
                    <input
                      {...register('name', { required: t('notifications.nameRequired') })}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder={t('notifications.namePlaceholder')}
                    />
                    {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('notifications.type')} <span className="text-red-500">*</span>
                    </label>
                    <select
                      {...register('channel_type', { required: t('notifications.typeRequired') })}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                    >
                      {CHANNEL_TYPES.map((type) => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                    {errors.channel_type && <p className="text-xs text-red-600 mt-1">{errors.channel_type.message}</p>}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('notifications.description')}
                  </label>
                  <textarea
                    {...register('description')}
                    rows={2}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none"
                    placeholder={t('notifications.descriptionPlaceholder')}
                  />
                </div>

                <div>
                  <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <input {...register('enabled')} type="checkbox" className="rounded border-border" />
                    {t('notifications.enabled')}
                  </label>
                </div>

                {/* Email Config */}
                {channelType === 'email' && (
                  <div className="border border-border rounded-lg p-4 space-y-4">
                    <h3 className="font-medium text-foreground">{t('notifications.emailSettings')}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('notifications.smtpServer')} <span className="text-red-500">*</span>
                        </label>
                        <input
                          {...register('smtp_server', { required: t('notifications.serverRequired') })}
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="smtp.example.com"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('notifications.smtpPort')}
                        </label>
                        <input
                          {...register('smtp_port', { valueAsNumber: true })}
                          type="number"
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="587"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('notifications.smtpUsername')}
                        </label>
                        <input
                          {...register('smtp_username')}
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="user@example.com"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('notifications.smtpPassword')}
                        </label>
                        <input
                          {...register('smtp_password')}
                          type="password"
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="********"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                        <input {...register('smtp_use_ssl')} type="checkbox" className="rounded border-border" />
                        {t('notifications.useSsl')}
                      </label>
                      <div>
                        <label className="block text-sm font-medium text-muted-foreground mb-1">
                          {t('notifications.defaultFrom')}
                        </label>
                        <input
                          {...register('default_from')}
                          className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                          placeholder="admin@example.com"
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Webhook Config */}
                {channelType === 'webhook' && (
                  <div className="border border-border rounded-lg p-4 space-y-4">
                    <h3 className="font-medium text-foreground">{t('notifications.webhookSettings')}</h3>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('notifications.webhookUrl')} <span className="text-red-500">*</span>
                      </label>
                      <input
                        {...register('webhook_url', { required: t('notifications.urlRequired') })}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="https://webhook.example.com"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('notifications.webhookSecret')}
                      </label>
                      <input
                        {...register('webhook_secret')}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder="Optional secret key"
                      />
                    </div>
                  </div>
                )}

                {/* Feishu/DingTalk/WeCom Config */}
                {(channelType === 'feishu' || channelType === 'dingtalk' || channelType === 'wecom') && (
                  <div className="border border-border rounded-lg p-4 space-y-4">
                    <h3 className="font-medium text-foreground">{t('notifications.botSettings')}</h3>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('notifications.botWebhookUrl')} <span className="text-red-500">*</span>
                      </label>
                      <input
                        {...register('bot_webhook_url', { required: t('notifications.urlRequired') })}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                        placeholder={`https://open.feishu.cn/open-apis/bot/v2/hook/...`}
                      />
                    </div>
                  </div>
                )}

                <div className="flex justify-end gap-3 pt-4 border-t border-border">
                  <PrimaryButton
                    type="button"
                    variant="secondary"
                    label={t('common.cancel')}
                    onClick={() => { setShowModal(false); setEditingChannel(null); reset(); }}
                  />
                  <PrimaryButton
                    type="submit"
                    label={editingChannel ? t('common.save') : t('common.create')}
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

export default Notifications;
