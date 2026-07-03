import React, { useState, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, formatDateTime } from '@/lib/utils';
import {
  Bell, Plus, Edit2, Trash2, CheckCircle, AlertCircle, TestTube, Save, X,
  Mail, Link2, MessageCircle, FileText, ChevronDown, Send, XCircle,
  LayoutTemplate, Shield, BarChart3,
} from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import {
  useNotificationLogs,
  useNotificationChannelTypes,
  type NotificationLogItem,
  type ChannelTypeInfo,
} from '@/hooks/useTerminalData';
import {
  CHANNEL_CONFIG_FIELDS,
} from '@/components/notifications/shared';
import NotificationTemplates from '@/components/notifications/NotificationTemplates';
import NotificationRules from '@/components/notifications/NotificationRules';
import NotificationMonitor from '@/components/notifications/NotificationMonitor';
import {
  buildConfigPayload,
  populateConfigFromItem,
  type ConfigFieldDef,
} from '@/components/datasources/shared';

interface NotificationChannel {
  id: number;
  name: string;
  type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  events: string[];
  description?: string;
  created_at: string;
  updated_at: string;
}

interface EventMeta {
  type: string;
  name: string;
  description: string;
  severity: string;
  category: string;
}

interface ChannelFormData {
  name: string;
  channel_type: string;
  description: string;
  enabled: boolean;
  events: string[];
}

// Icon mapping kept on frontend (backend does not return icons)
const CHANNEL_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  email: Mail,
  webhook: Link2,
  feishu: MessageCircle,
  dingtalk: MessageCircle,
  wecom: MessageCircle,
};

const CHANNEL_ICON_COLORS: Record<string, string> = {
  email: 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400',
  webhook: 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400',
  feishu: 'bg-cyan-100 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-400',
  dingtalk: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400',
  wecom: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400',
};

const CATEGORY_CHIP_COLORS: Record<string, string> = {
  terminal: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
  security: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
  admin: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200',
  system: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200',
  alert: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
};

const STATUS_BADGE_COLORS: Record<string, string> = {
  sent: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
};

const Notifications: React.FC = () => {
  const { t } = useTranslation();

  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);
  const [testLoading, setTestLoading] = useState<number | null>(null);
  const [eventTypes, setEventTypes] = useState<EventMeta[]>([]);
  const [activeTab, setActiveTab] = useState<'channels' | 'logs' | 'templates' | 'rules' | 'monitor'>('channels');
  const [expandedCats, setExpandedCats] = useState<Record<string, boolean>>({});
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [savingChannel, setSavingChannel] = useState(false);

  // Logs tab state
  const [logFilters, setLogFilters] = useState<{ channel_name: string; event_type: string; status: string }>({
    channel_name: '', event_type: '', status: '',
  });
  const [logPage, setLogPage] = useState(1);
  const [logPageSize, setLogPageSize] = useState(20);

  const { data: channelTypesData } = useNotificationChannelTypes();
  const channelTypes: ChannelTypeInfo[] = channelTypesData || [];

  // Stats: fetch recent logs for 24h calculation (shared cache with Logs tab)
  const logParams = useMemo(() => ({
    channel_name: logFilters.channel_name || undefined,
    event_type: logFilters.event_type || undefined,
    status: logFilters.status || undefined,
    limit: logPageSize,
    offset: (logPage - 1) * logPageSize,
  }), [logFilters, logPage, logPageSize]);

  const { data: logsData, isLoading: logsLoading } = useNotificationLogs(logParams);

  // Fetch 500 recent logs for 24h stats (separate query, shared via queryKey)
  const { data: statsLogsData } = useNotificationLogs({ limit: 500 });

  const { register, handleSubmit, reset, watch, setValue, formState: { errors } } = useForm<ChannelFormData>({
    defaultValues: {
      name: '',
      channel_type: 'email',
      description: '',
      enabled: true,
      events: [],
    },
  });

  const channelType = watch('channel_type');

  useEffect(() => {
    fetchChannels();
    fetchEventTypes();
  }, []);

  // Default expand all categories
  useEffect(() => {
    if (eventTypes.length > 0) {
      const cats = new Set(eventTypes.map((e) => e.category));
      const init: Record<string, boolean> = {};
      cats.forEach((c) => { init[c] = true; });
      setExpandedCats(init);
    }
  }, [eventTypes]);

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

  // Group events by category for accordion
  const eventsByCategory = useMemo(() => {
    const groups: Record<string, EventMeta[]> = {};
    eventTypes.forEach((evt) => {
      if (!groups[evt.category]) groups[evt.category] = [];
      groups[evt.category].push(evt);
    });
    return groups;
  }, [eventTypes]);

  const categoryLabels: Record<string, string> = {
    terminal: t('notifications.categories.terminal'),
    security: t('notifications.categories.security'),
    admin: t('notifications.categories.admin'),
    system: t('notifications.categories.system'),
    alert: t('notifications.categories.alert'),
  };

  // Current config field defs for the selected channel type
  const currentConfigFields: ConfigFieldDef[] = CHANNEL_CONFIG_FIELDS[channelType] || [];

  const onSubmit = async (data: ChannelFormData) => {
    setSavingChannel(true);
    try {
      const config = buildConfigPayload(currentConfigFields, configValues);
      // 'mode' is a UI-only field used to toggle between webhook/app form
      // sections; the backend infers the mode from which credentials are
      // present, so strip it before sending.
      delete config.mode;
      // For DingTalk, convert to_all_user string to boolean
      if ('to_all_user' in config) {
        config.to_all_user = config.to_all_user === 'true';
      }
      const payload = {
        name: data.name,
        type: data.channel_type,
        description: data.description,
        enabled: data.enabled,
        events: data.events,
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
      setConfigValues({});
      fetchChannels();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notifications.failedToSave')));
    } finally {
      setSavingChannel(false);
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

  const handleToggleEnabled = async (channel: NotificationChannel, enabled: boolean) => {
    try {
      await apiClient.put(`${API_ENDPOINTS.NOTIFICATION_CHANNELS}${channel.id}/`, { enabled });
      toast.success(enabled ? t('common.enabled') : t('common.disabled'));
      fetchChannels();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notifications.failedToSave')));
    }
  };

  const handleOpenModal = (channel?: NotificationChannel) => {
    if (channel) {
      setEditingChannel(channel);
      reset({
        name: channel.name,
        channel_type: channel.type,
        description: channel.description || '',
        enabled: channel.enabled,
        events: channel.events || [],
      });
      const fields = CHANNEL_CONFIG_FIELDS[channel.type] || [];
      const rawConfig = channel.config as Record<string, string | number | boolean | object | null>;
      const vals = populateConfigFromItem(fields, rawConfig);
      // Detect mode from existing config so the correct fields render when
      // editing an IM channel. The backend stores either webhook_url or
      // app credentials, so we infer which mode was configured.
      const cfg = rawConfig as Record<string, unknown>;
      if (fields.length > 0 && fields[0].key === 'mode') {
        if (cfg.app_id || cfg.app_key || cfg.corp_id) {
          vals.mode = 'app';
        } else {
          vals.mode = 'webhook';
        }
      }
      // Convert boolean to_all_user back to string for the select input
      if (typeof cfg.to_all_user === 'boolean') {
        vals.to_all_user = cfg.to_all_user ? 'true' : 'false';
      }
      setConfigValues(vals);
    } else {
      setEditingChannel(null);
      reset();
      setConfigValues({});
    }
    setShowModal(true);
  };

  const toggleEvent = (eventType: string) => {
    const currentEvents = watch('events');
    if (currentEvents.includes(eventType)) {
      setValue('events', currentEvents.filter((e) => e !== eventType));
    } else {
      setValue('events', [...currentEvents, eventType]);
    }
  };

  const toggleCategory = (cat: string) => {
    setExpandedCats((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  const getChannelIcon = (type: string) => CHANNEL_ICONS[type] || Bell;

  // Event type lookup map (type → EventMeta)
  const eventTypeMap = useMemo(() => {
    const m: Record<string, EventMeta> = {};
    eventTypes.forEach((e) => { m[e.type] = e; });
    return m;
  }, [eventTypes]);

  // 24h stats from statsLogsData
  const stats = useMemo(() => {
    const allLogs = statsLogsData?.items || [];
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    const recent = allLogs.filter((l) => new Date(l.sent_at).getTime() >= cutoff);
    return {
      totalChannels: channels.length,
      enabledChannels: channels.filter((c) => c.enabled).length,
      sent24h: recent.filter((l) => l.status === 'sent').length,
      failed24h: recent.filter((l) => l.status === 'failed').length,
    };
  }, [statsLogsData, channels]);

  // Logs pagination
  const logs = logsData?.items || [];
  const logTotal = logsData?.total || 0;
  const logTotalPages = Math.max(1, Math.ceil(logTotal / logPageSize));

  const handleLogFilterChange = (key: 'channel_name' | 'event_type' | 'status', value: string) => {
    setLogFilters((prev) => ({ ...prev, [key]: value }));
    setLogPage(1);
  };

  const statCards = [
    { label: t('notifications.title'), value: stats.totalChannels, icon: Bell, color: 'text-blue-600' },
    { label: t('common.enabled'), value: stats.enabledChannels, icon: CheckCircle, color: 'text-green-600' },
    { label: '24h ' + t('notifications.sendLogs'), value: stats.sent24h, icon: Send, color: 'text-cyan-600' },
    { label: '24h Failed', value: stats.failed24h, icon: XCircle, color: 'text-red-600' },
  ];

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
          {activeTab === 'channels' && (
            <PrimaryButton
              label={t('notifications.addChannel')}
              onClick={() => handleOpenModal()}
              icon={Plus}
            />
          )}
        </div>

        {/* Stats Bar (D3) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {statCards.map((s, i) => {
            const Icon = s.icon;
            return (
              <div key={i} className="bg-card rounded-lg border border-border p-4 flex items-center gap-3">
                <div className={`p-2 rounded-md bg-opacity-10 ${s.color.replace('text-', 'bg-')} bg-opacity-10`}>
                  <Icon className={`h-5 w-5 ${s.color}`} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">{s.value}</p>
                  <p className="text-xs text-muted-foreground">{s.label}</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Tabs (D4) */}
        <div className="mb-6 border-b border-border">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('channels')}
              className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === 'channels'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <Bell className="h-4 w-4" />
              {t('notifications.channels')}
            </button>
            <button
              onClick={() => setActiveTab('logs')}
              className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === 'logs'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <FileText className="h-4 w-4" />
              {t('notifications.sendLogs')}
            </button>
            <button
              onClick={() => setActiveTab('templates')}
              className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === 'templates'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <LayoutTemplate className="h-4 w-4" />
              {t('notificationTemplates.title')}
            </button>
            <button
              onClick={() => setActiveTab('rules')}
              className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === 'rules'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <Shield className="h-4 w-4" />
              {t('notificationRules.title')}
            </button>
            <button
              onClick={() => setActiveTab('monitor')}
              className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === 'monitor'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <BarChart3 className="h-4 w-4" />
              {t('notificationMonitor.title')}
            </button>
          </nav>
        </div>

        {/* === Channels Tab === */}
        {activeTab === 'channels' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Channels List */}
            <div className="lg:col-span-2">
              <div className="bg-card rounded-2xl border border-border p-6">
                {loading ? (
                  <div className="flex justify-center items-center py-12">
                    <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : channels.length === 0 ? (
                  <div className="text-center py-12">
                    <Bell className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                    <p className="text-muted-foreground">{t('notifications.noChannels')}</p>
                    <PrimaryButton
                      label={t('notifications.addFirstChannel')}
                      onClick={() => handleOpenModal()}
                    />
                  </div>
                ) : (
                  <div className="space-y-3">
                    {channels.map((channel) => {
                      const Icon = getChannelIcon(channel.type);
                      const iconColor = CHANNEL_ICON_COLORS[channel.type] || 'bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400';
                      return (
                        <div key={channel.id} className="bg-background rounded-xl p-4 border border-border">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${iconColor}`}>
                                <Icon className="h-5 w-5" />
                              </div>
                              <div>
                                <h3 className="font-semibold text-foreground">{channel.name}</h3>
                                <p className="text-sm text-muted-foreground">
                                  {channelTypes.find((c) => c.type === channel.type)?.name || channel.type}
                                </p>
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  {t('notifications.subscribedEvents', { count: channel.events?.length || 0 })}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {/* Toggle (D5) */}
                              <label className="inline-flex items-center cursor-pointer mr-2" title={channel.enabled ? t('common.enabled') : t('common.disabled')}>
                                <input
                                  type="checkbox"
                                  checked={channel.enabled}
                                  onChange={(e) => handleToggleEnabled(channel, e.target.checked)}
                                  className="sr-only peer"
                                />
                                <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-500 relative" />
                              </label>
                              <button
                                onClick={() => handleTest(channel.id)}
                                disabled={testLoading === channel.id}
                                className="p-2 text-muted-foreground hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors"
                                title={t('notifications.testChannel')}
                              >
                                {testLoading === channel.id ? (
                                  <div className="w-4 h-4 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
                                ) : (
                                  <TestTube className="h-4 w-4" />
                                )}
                              </button>
                              <button
                                onClick={() => handleOpenModal(channel)}
                                className="p-2 text-muted-foreground hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors"
                                title={t('common.edit')}
                              >
                                <Edit2 className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => handleDelete(channel.id, channel.name)}
                                className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                title={t('common.delete')}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </div>
                          </div>
                          {channel.description && (
                            <p className="text-sm text-muted-foreground mt-3">{channel.description}</p>
                          )}
                          {/* Subscribed events as colored chips (D5) */}
                          {channel.events && channel.events.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-3">
                              {channel.events.slice(0, 3).map((evtType) => {
                                const meta = eventTypeMap[evtType];
                                const cat = meta?.category || 'system';
                                return (
                                  <span key={evtType} className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${CATEGORY_CHIP_COLORS[cat] || CATEGORY_CHIP_COLORS.system}`}>
                                    {meta?.name || evtType}
                                  </span>
                                );
                              })}
                              {channel.events.length > 3 && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                                  +{channel.events.length - 3}
                                </span>
                              )}
                            </div>
                          )}
                          {testResult?.id === channel.id && (
                            <div className={`mt-3 p-3 rounded-lg flex items-center gap-2 ${
                              testResult.success
                                ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300'
                                : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
                            }`}>
                              {testResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
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

            {/* Event Types sidebar */}
            <div className="lg:col-span-1">
              <div className="bg-card rounded-2xl border border-border p-6 sticky top-6">
                <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                  <Bell className="h-5 w-5 text-muted-foreground" />
                  {t('notifications.eventTypes')}
                </h2>
                <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                  {Object.entries(eventsByCategory).map(([cat, events]) => {
                    const selectedCount = events.filter((e) => watch('events').includes(e.type)).length;
                    return (
                      <div key={cat} className="border border-border rounded-lg overflow-hidden">
                        <button
                          onClick={() => toggleCategory(cat)}
                          className="w-full flex items-center justify-between p-3 hover:bg-accent transition-colors"
                        >
                          <span className="text-sm font-medium text-foreground">{categoryLabels[cat] || cat}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">({selectedCount}/{events.length})</span>
                            <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${expandedCats[cat] ? 'rotate-180' : ''}`} />
                          </div>
                        </button>
                        {expandedCats[cat] && (
                          <div className="p-2 space-y-1 border-t border-border">
                            {events.map((evt) => (
                              <div key={evt.type} className="bg-background rounded-lg p-2">
                                <p className="font-medium text-foreground text-sm">{evt.name}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{evt.description}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* === Logs Tab (D7) === */}
        {activeTab === 'logs' && (
          <div className="bg-card rounded-2xl border border-border p-6">
            {/* Filters */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">{t('notifications.channels')}</label>
                <select
                  value={logFilters.channel_name}
                  onChange={(e) => handleLogFilterChange('channel_name', e.target.value)}
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="">{t('common.all')}</option>
                  {channels.map((c) => (
                    <option key={c.id} value={c.name}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">{t('notifications.eventTypes')}</label>
                <select
                  value={logFilters.event_type}
                  onChange={(e) => handleLogFilterChange('event_type', e.target.value)}
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="">{t('common.all')}</option>
                  {eventTypes.map((e) => (
                    <option key={e.type} value={e.type}>{e.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">{t('common.status')}</label>
                <select
                  value={logFilters.status}
                  onChange={(e) => handleLogFilterChange('status', e.target.value)}
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="">{t('common.all')}</option>
                  <option value="sent">Sent</option>
                  <option value="failed">Failed</option>
                  <option value="pending">Pending</option>
                </select>
              </div>
            </div>

            {/* Logs Table */}
            {logsLoading ? (
              <div className="flex justify-center items-center py-12">
                <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : logs.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">{t('common.noData')}</p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-muted-foreground">
                        <th className="py-2 px-3 font-medium">Event ID</th>
                        <th className="py-2 px-3 font-medium">{t('notifications.channels')}</th>
                        <th className="py-2 px-3 font-medium">{t('notifications.eventTypes')}</th>
                        <th className="py-2 px-3 font-medium">{t('common.status')}</th>
                        <th className="py-2 px-3 font-medium">Recipient</th>
                        <th className="py-2 px-3 font-medium">Sent At</th>
                        <th className="py-2 px-3 font-medium">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map((log: NotificationLogItem) => (
                        <tr key={log.id} className="border-b border-border hover:bg-accent/50">
                          <td className="py-2 px-3 font-mono text-xs text-muted-foreground max-w-[120px] truncate" title={log.event_id}>{log.event_id}</td>
                          <td className="py-2 px-3">{log.channel_name}</td>
                          <td className="py-2 px-3">{eventTypeMap[log.event_type]?.name || log.event_type}</td>
                          <td className="py-2 px-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE_COLORS[log.status] || ''}`}>
                              {log.status}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-muted-foreground max-w-[150px] truncate" title={log.recipient || ''}>{log.recipient || '-'}</td>
                          <td className="py-2 px-3 text-muted-foreground whitespace-nowrap">{formatDateTime(log.sent_at)}</td>
                          <td className="py-2 px-3 text-red-600 dark:text-red-400 text-xs max-w-[200px] truncate" title={log.error_message || ''}>{log.error_message || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {/* Pagination */}
                <div className="mt-4">
                  <Pagination
                    currentPage={logPage}
                    totalPages={logTotalPages}
                    onPageChange={setLogPage}
                    pageSize={logPageSize}
                    onPageSizeChange={(s) => { setLogPageSize(s); setLogPage(1); }}
                    pageSizeOptions={[10, 20, 50, 100]}
                    totalItems={logTotal}
                    showPageSizeSelector
                  />
                </div>
              </>
            )}
          </div>
        )}

        {/* === Templates Tab === */}
        {activeTab === 'templates' && (
          <NotificationTemplates eventTypes={eventTypes} channelTypes={channelTypes} />
        )}

        {/* === Rules Tab === */}
        {activeTab === 'rules' && (
          <NotificationRules eventTypes={eventTypes} channels={channels} />
        )}

        {/* === Monitor Tab === */}
        {activeTab === 'monitor' && (
          <NotificationMonitor />
        )}

        {/* Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-background rounded-2xl border border-border w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-background z-10">
                <h2 className="text-lg font-semibold text-foreground">
                  {editingChannel ? t('notifications.editChannel') : t('notifications.addChannel')}
                </h2>
                <button
                  onClick={() => { setShowModal(false); setEditingChannel(null); reset(); setConfigValues({}); }}
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
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                      placeholder={t('notifications.namePlaceholder')}
                    />
                    {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('notifications.type')} <span className="text-red-500">*</span>
                    </label>
                    <select
                      {...register('channel_type')}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                    >
                      {channelTypes.map((ct) => (
                        <option key={ct.type} value={ct.type}>{ct.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('notifications.description')}
                  </label>
                  <textarea
                    {...register('description')}
                    rows={2}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none resize-none bg-background"
                    placeholder={t('notifications.descriptionPlaceholder')}
                  />
                </div>

                <div>
                  <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <input {...register('enabled')} type="checkbox" className="rounded border-border text-primary-600 focus:ring-primary-500" />
                    {t('notifications.enabled')}
                  </label>
                </div>

                {/* Event subscription accordion (D6) */}
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-2">
                    {t('notifications.subscribedEvents')}
                  </label>
                  <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                    {Object.entries(eventsByCategory).map(([cat, events]) => {
                      const selectedCount = events.filter((e) => watch('events').includes(e.type)).length;
                      return (
                        <div key={cat} className="border border-border rounded-lg overflow-hidden">
                          <button
                            type="button"
                            onClick={() => toggleCategory(cat)}
                            className="w-full flex items-center justify-between p-3 hover:bg-accent transition-colors"
                          >
                            <span className="text-sm font-medium text-foreground">{categoryLabels[cat] || cat}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">({selectedCount}/{events.length})</span>
                              <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${expandedCats[cat] ? 'rotate-180' : ''}`} />
                            </div>
                          </button>
                          {expandedCats[cat] && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3 border-t border-border">
                              {events.map((evt) => {
                                const checked = watch('events').includes(evt.type);
                                return (
                                  <label
                                    key={evt.type}
                                    className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer border transition-colors ${
                                      checked
                                        ? 'bg-primary-50 border-primary-200 text-primary-700 dark:bg-primary-900/20 dark:border-primary-700 dark:text-primary-300'
                                        : 'bg-background border-border text-foreground hover:border-primary-200'
                                    }`}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={() => toggleEvent(evt.type)}
                                      className="rounded border-border text-primary-600 focus:ring-primary-500"
                                    />
                                    <div className="flex-1 min-w-0">
                                      <p className="text-sm font-medium truncate">{evt.name}</p>
                                      <p className="text-xs text-muted-foreground truncate">{evt.description}</p>
                                    </div>
                                  </label>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Dynamic config fields (D2) */}
                {currentConfigFields.length > 0 && (
                  <div className="border border-border rounded-lg p-4 space-y-4">
                    <h3 className="font-medium text-foreground">
                      {channelTypes.find((c) => c.type === channelType)?.name || channelType} {t('notifications.botSettings')}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {currentConfigFields
                        .filter((field) => {
                          if (!field.showWhen) return true;
                          return Object.entries(field.showWhen).every(
                            ([key, val]) => (configValues[key] ?? '') === val,
                          );
                        })
                        .map((field) => (
                        <div key={field.key} className={field.key === 'mode' ? 'md:col-span-2' : ''}>
                          <label className="block text-sm font-medium text-muted-foreground mb-1">{field.label}</label>
                          {field.type === 'select' ? (
                            <select
                              value={configValues[field.key] ?? field.defaultValue ?? ''}
                              onChange={(e) => setConfigValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                              className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                            >
                              {field.options?.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                          ) : (
                            <input
                              type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
                              value={configValues[field.key] ?? ''}
                              onChange={(e) => setConfigValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                              placeholder={field.placeholder}
                              className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex justify-end gap-3 pt-4 border-t border-border sticky bottom-0 bg-background">
                  <PrimaryButton
                    type="button"
                    variant="secondary"
                    label={t('common.cancel')}
                    onClick={() => { setShowModal(false); setEditingChannel(null); reset(); setConfigValues({}); }}
                  />
                  <PrimaryButton
                    type="submit"
                    label={editingChannel ? t('common.save') : t('common.create')}
                    icon={Save}
                    loading={savingChannel}
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
