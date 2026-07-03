import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, formatDateTime } from '@/lib/utils';
import {
  Shield, Plus, Edit2, Trash2, Save, X, BellOff, TrendingUp, AlertTriangle,
} from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';

export interface EventMeta {
  type: string;
  name: string;
  description: string;
  severity: string;
  category: string;
}

interface NotificationChannel {
  id: number;
  name: string;
  type: string;
  enabled: boolean;
}

interface NotificationRule {
  id: number;
  name: string;
  event_type: string;
  channel_name: string | null;
  enabled: boolean;
  description: string | null;
  suppress_enabled: boolean;
  suppress_window: number;
  escalate_enabled: boolean;
  escalate_threshold: number;
  escalate_window: number;
  escalate_severity: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

interface RuleFormData {
  name: string;
  event_type: string;
  channel_name: string;
  enabled: boolean;
  description: string;
  suppress_enabled: boolean;
  suppress_window: number;
  escalate_enabled: boolean;
  escalate_threshold: number;
  escalate_window: number;
  escalate_severity: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
  warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
  critical: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200',
};

const NotificationRules: React.FC<{
  eventTypes: EventMeta[];
  channels: NotificationChannel[];
}> = ({ eventTypes, channels }) => {
  const { t } = useTranslation();

  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<NotificationRule | null>(null);
  const [saving, setSaving] = useState(false);
  const [filterEventType, setFilterEventType] = useState('');

  const [formData, setFormData] = useState<RuleFormData>({
    name: '',
    event_type: '',
    channel_name: '',
    enabled: true,
    description: '',
    suppress_enabled: false,
    suppress_window: 300,
    escalate_enabled: false,
    escalate_threshold: 5,
    escalate_window: 3600,
    escalate_severity: 'error',
  });

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterEventType) params.event_type = filterEventType;
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_RULES, { params });
      setRules(response.data);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationRules.failedToLoad')));
    } finally {
      setLoading(false);
    }
  }, [filterEventType, t]);

  useEffect(() => {
    fetchRules();
  }, [fetchRules]);

  const handleOpenModal = (rule?: NotificationRule) => {
    if (rule) {
      setEditingRule(rule);
      setFormData({
        name: rule.name,
        event_type: rule.event_type,
        channel_name: rule.channel_name || '',
        enabled: rule.enabled,
        description: rule.description || '',
        suppress_enabled: rule.suppress_enabled,
        suppress_window: rule.suppress_window,
        escalate_enabled: rule.escalate_enabled,
        escalate_threshold: rule.escalate_threshold,
        escalate_window: rule.escalate_window,
        escalate_severity: rule.escalate_severity,
      });
    } else {
      setEditingRule(null);
      setFormData({
        name: '',
        event_type: eventTypes[0]?.type || '',
        channel_name: '',
        enabled: true,
        description: '',
        suppress_enabled: false,
        suppress_window: 300,
        escalate_enabled: false,
        escalate_threshold: 5,
        escalate_window: 3600,
        escalate_severity: 'error',
      });
    }
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingRule(null);
  };

  const handleSubmit = async () => {
    if (!formData.name.trim()) {
      toast.error(t('notificationRules.nameRequired'));
      return;
    }
    if (!formData.event_type) {
      toast.error(t('notificationRules.eventTypeRequired'));
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: formData.name.trim(),
        event_type: formData.event_type,
        channel_name: formData.channel_name.trim() || null,
        enabled: formData.enabled,
        description: formData.description.trim() || null,
        suppress_enabled: formData.suppress_enabled,
        suppress_window: formData.suppress_window,
        escalate_enabled: formData.escalate_enabled,
        escalate_threshold: formData.escalate_threshold,
        escalate_window: formData.escalate_window,
        escalate_severity: formData.escalate_severity,
      };

      if (editingRule) {
        await apiClient.put(
          API_ENDPOINTS.NOTIFICATION_RULES_BY_ID.replace('{{id}}', String(editingRule.id)),
          payload,
        );
        toast.success(t('notificationRules.updatedSuccessfully'));
      } else {
        await apiClient.post(API_ENDPOINTS.NOTIFICATION_RULES, payload);
        toast.success(t('notificationRules.createdSuccessfully'));
      }

      handleCloseModal();
      fetchRules();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationRules.failedToSave')));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(t('notificationRules.confirmDelete', { name }))) return;
    try {
      await apiClient.delete(
        API_ENDPOINTS.NOTIFICATION_RULES_BY_ID.replace('{{id}}', String(id)),
      );
      toast.success(t('notificationRules.deletedSuccessfully'));
      fetchRules();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationRules.failedToDelete')));
    }
  };

  const eventName = (type: string) => eventTypes.find((e) => e.type === type)?.name || type;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Rules List */}
      <div className="lg:col-span-2">
        <div className="bg-card rounded-2xl border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Shield className="h-5 w-5 text-muted-foreground" />
              {t('notificationRules.ruleList')}
            </h2>
            <PrimaryButton
              label={t('notificationRules.addRule')}
              onClick={() => handleOpenModal()}
              icon={Plus}
            />
          </div>

          <div className="mb-4">
            <select
              value={filterEventType}
              onChange={(e) => setFilterEventType(e.target.value)}
              className="px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">{t('common.all')} {t('notificationRules.eventType')}</option>
              {eventTypes.map((e) => (
                <option key={e.type} value={e.type}>{e.name}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : rules.length === 0 ? (
            <div className="text-center py-12">
              <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">{t('notificationRules.noRules')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('notificationRules.noRulesHint')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {rules.map((rule) => (
                <div key={rule.id} className="bg-background rounded-xl p-4 border border-border">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-foreground">{rule.name}</h3>
                        {!rule.enabled && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                            {t('common.disabled')}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        {eventName(rule.event_type)}
                        {rule.channel_name ? ` → ${rule.channel_name}` : ` → ${t('notificationRules.allChannels')}`}
                      </p>
                      {/* Feature badges */}
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        {rule.suppress_enabled && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-200">
                            <BellOff className="h-3 w-3" />
                            {t('notificationRules.suppress')} {rule.suppress_window}s
                          </span>
                        )}
                        {rule.escalate_enabled && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200">
                            <TrendingUp className="h-3 w-3" />
                            {t('notificationRules.escalate')} ≥{rule.escalate_threshold}
                            <span className={`ml-1 px-1.5 py-0.5 rounded text-xs font-bold ${SEVERITY_COLORS[rule.escalate_severity] || SEVERITY_COLORS.error}`}>
                              {rule.escalate_severity}
                            </span>
                          </span>
                        )}
                        {!rule.suppress_enabled && !rule.escalate_enabled && (
                          <span className="text-xs text-muted-foreground italic">
                            {t('notificationRules.noFeatures')}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        {t('notificationRules.updatedAt')}: {formatDateTime(rule.updated_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-2">
                      <button
                        onClick={() => handleOpenModal(rule)}
                        className="p-2 text-muted-foreground hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors"
                        title={t('common.edit')}
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(rule.id, rule.name)}
                        className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title={t('common.delete')}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  {rule.description && (
                    <p className="text-sm text-muted-foreground mt-2">{rule.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Help sidebar */}
      <div className="lg:col-span-1">
        <div className="bg-card rounded-2xl border border-border p-6 sticky top-6">
          <h2 className="text-lg font-semibold text-foreground mb-3 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-muted-foreground" />
            {t('notificationRules.helpTitle')}
          </h2>
          <div className="space-y-4 text-sm">
            <div>
              <h3 className="font-medium text-foreground flex items-center gap-1.5 mb-1">
                <BellOff className="h-4 w-4 text-cyan-600" />
                {t('notificationRules.suppress')}
              </h3>
              <p className="text-xs text-muted-foreground">{t('notificationRules.suppressHelp')}</p>
            </div>
            <div>
              <h3 className="font-medium text-foreground flex items-center gap-1.5 mb-1">
                <TrendingUp className="h-4 w-4 text-orange-600" />
                {t('notificationRules.escalate')}
              </h3>
              <p className="text-xs text-muted-foreground">{t('notificationRules.escalateHelp')}</p>
            </div>
            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <p className="text-xs text-blue-700 dark:text-blue-300">
                {t('notificationRules.aggregationHelp')}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-background rounded-2xl border border-border w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-background z-10">
              <h2 className="text-lg font-semibold text-foreground">
                {editingRule
                  ? t('notificationRules.editRule')
                  : t('notificationRules.addRule')}
              </h2>
              <button
                onClick={handleCloseModal}
                className="p-1 hover:bg-accent rounded-lg transition-colors"
              >
                <X className="h-5 w-5 text-muted-foreground" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  {t('notificationRules.name')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                  placeholder={t('notificationRules.namePlaceholder')}
                />
              </div>

              {/* Event Type + Channel */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('notificationRules.eventType')} <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={formData.event_type}
                    onChange={(e) => setFormData((p) => ({ ...p, event_type: e.target.value }))}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                  >
                    <option value="">{t('common.select')}</option>
                    {eventTypes.map((e) => (
                      <option key={e.type} value={e.type}>{e.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('notificationRules.channel')}
                  </label>
                  <select
                    value={formData.channel_name}
                    onChange={(e) => setFormData((p) => ({ ...p, channel_name: e.target.value }))}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                  >
                    <option value="">{t('notificationRules.allChannels')}</option>
                    {channels.map((c) => (
                      <option key={c.id} value={c.name}>{c.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  {t('notificationRules.description')}
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData((p) => ({ ...p, description: e.target.value }))}
                  rows={2}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none resize-none bg-background"
                  placeholder={t('notificationRules.descriptionPlaceholder')}
                />
              </div>

              {/* Enabled */}
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={formData.enabled}
                    onChange={(e) => setFormData((p) => ({ ...p, enabled: e.target.checked }))}
                    className="rounded border-border text-primary-600 focus:ring-primary-500"
                  />
                  {t('notificationRules.enabled')}
                </label>
              </div>

              {/* Suppression Section */}
              <div className="border border-border rounded-lg p-4 space-y-3">
                <label className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <input
                    type="checkbox"
                    checked={formData.suppress_enabled}
                    onChange={(e) => setFormData((p) => ({ ...p, suppress_enabled: e.target.checked }))}
                    className="rounded border-border text-primary-600 focus:ring-primary-500"
                  />
                  <BellOff className="h-4 w-4 text-cyan-600" />
                  {t('notificationRules.suppress')}
                </label>
                {formData.suppress_enabled && (
                  <div className="pl-6">
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('notificationRules.suppressWindow')} ({t('notificationRules.seconds')})
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={86400}
                      value={formData.suppress_window}
                      onChange={(e) => setFormData((p) => ({ ...p, suppress_window: Number(e.target.value) }))}
                      className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      {t('notificationRules.suppressWindowHint')}
                    </p>
                  </div>
                )}
              </div>

              {/* Escalation Section */}
              <div className="border border-border rounded-lg p-4 space-y-3">
                <label className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <input
                    type="checkbox"
                    checked={formData.escalate_enabled}
                    onChange={(e) => setFormData((p) => ({ ...p, escalate_enabled: e.target.checked }))}
                    className="rounded border-border text-primary-600 focus:ring-primary-500"
                  />
                  <TrendingUp className="h-4 w-4 text-orange-600" />
                  {t('notificationRules.escalate')}
                </label>
                {formData.escalate_enabled && (
                  <div className="pl-6 grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('notificationRules.escalateThreshold')}
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={1000}
                        value={formData.escalate_threshold}
                        onChange={(e) => setFormData((p) => ({ ...p, escalate_threshold: Number(e.target.value) }))}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('notificationRules.escalateWindow')} ({t('notificationRules.seconds')})
                      </label>
                      <input
                        type="number"
                        min={60}
                        max={604800}
                        value={formData.escalate_window}
                        onChange={(e) => setFormData((p) => ({ ...p, escalate_window: Number(e.target.value) }))}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-muted-foreground mb-1">
                        {t('notificationRules.escalateSeverity')}
                      </label>
                      <select
                        value={formData.escalate_severity}
                        onChange={(e) => setFormData((p) => ({ ...p, escalate_severity: e.target.value }))}
                        className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                      >
                        <option value="info">Info</option>
                        <option value="warning">Warning</option>
                        <option value="error">Error</option>
                        <option value="critical">Critical</option>
                      </select>
                    </div>
                    <p className="text-xs text-muted-foreground md:col-span-3">
                      {t('notificationRules.escalateHint')}
                    </p>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-3 pt-4 border-t border-border sticky bottom-0 bg-background">
                <PrimaryButton
                  type="button"
                  variant="secondary"
                  label={t('common.cancel')}
                  onClick={handleCloseModal}
                />
                <PrimaryButton
                  type="button"
                  label={editingRule ? t('common.save') : t('common.create')}
                  icon={Save}
                  onClick={handleSubmit}
                  loading={saving}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationRules;
