import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, formatDateTime } from '@/lib/utils';
import {
  FileText, Plus, Edit2, Trash2, Save, X, Eye, Code, CheckCircle,
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

export interface ChannelTypeInfo {
  type: string;
  name: string;
  description: string;
  config_fields: string[];
}

interface NotificationTemplate {
  id: number;
  name: string;
  event_type: string;
  channel_type: string;
  subject_template: string | null;
  body_template: string;
  is_default: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

interface TemplateFormData {
  name: string;
  event_type: string;
  channel_type: string;
  subject_template: string;
  body_template: string;
  is_default: boolean;
}

const SEVERITY_BADGE_COLORS: Record<string, string> = {
  info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200',
  warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200',
  critical: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200',
};

const DEFAULT_BODY_TEMPLATE = `【{{ event_name }}】
事件类型: {{ event_type }}
严重级别: {{ severity }}
来源: {{ source }}
时间: {{ timestamp }}
描述: {{ description }}
{% if data %}附加数据: {{ data }}{% endif %}`;

const NotificationTemplates: React.FC<{
  eventTypes: EventMeta[];
  channelTypes: ChannelTypeInfo[];
}> = ({ eventTypes, channelTypes }) => {
  const { t } = useTranslation();

  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<NotificationTemplate | null>(null);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewResult, setPreviewResult] = useState<{ subject: string; body: string } | null>(null);

  // Filters
  const [filterEventType, setFilterEventType] = useState('');
  const [filterChannelType, setFilterChannelType] = useState('');

  // Form state (managed manually because templates need fine-grained control)
  const [formData, setFormData] = useState<TemplateFormData>({
    name: '',
    event_type: '',
    channel_type: '',
    subject_template: '',
    body_template: DEFAULT_BODY_TEMPLATE,
    is_default: false,
  });

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterEventType) params.event_type = filterEventType;
      if (filterChannelType) params.channel_type = filterChannelType;
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_TEMPLATES, { params });
      setTemplates(response.data);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationTemplates.failedToLoad')));
    } finally {
      setLoading(false);
    }
  }, [filterEventType, filterChannelType, t]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleOpenModal = (template?: NotificationTemplate) => {
    if (template) {
      setEditingTemplate(template);
      setFormData({
        name: template.name,
        event_type: template.event_type,
        channel_type: template.channel_type,
        subject_template: template.subject_template || '',
        body_template: template.body_template,
        is_default: template.is_default,
      });
    } else {
      setEditingTemplate(null);
      setFormData({
        name: '',
        event_type: eventTypes[0]?.type || '',
        channel_type: channelTypes[0]?.type || '',
        subject_template: '',
        body_template: DEFAULT_BODY_TEMPLATE,
        is_default: false,
      });
    }
    setPreviewResult(null);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingTemplate(null);
    setPreviewResult(null);
  };

  const handleSubmit = async () => {
    // Basic validation
    if (!formData.name.trim()) {
      toast.error(t('notificationTemplates.nameRequired'));
      return;
    }
    if (!formData.event_type) {
      toast.error(t('notificationTemplates.eventTypeRequired'));
      return;
    }
    if (!formData.channel_type) {
      toast.error(t('notificationTemplates.channelTypeRequired'));
      return;
    }
    if (!formData.body_template.trim()) {
      toast.error(t('notificationTemplates.bodyTemplateRequired'));
      return;
    }

    setSaving(true);
    try {
      // subject_template is only relevant for email; send null if empty
      const payload = {
        name: formData.name.trim(),
        event_type: formData.event_type,
        channel_type: formData.channel_type,
        subject_template: formData.subject_template.trim() || null,
        body_template: formData.body_template,
        is_default: formData.is_default,
      };

      if (editingTemplate) {
        await apiClient.put(
          API_ENDPOINTS.NOTIFICATION_TEMPLATES_BY_ID.replace('{{id}}', String(editingTemplate.id)),
          payload,
        );
        toast.success(t('notificationTemplates.updatedSuccessfully'));
      } else {
        await apiClient.post(API_ENDPOINTS.NOTIFICATION_TEMPLATES, payload);
        toast.success(t('notificationTemplates.createdSuccessfully'));
      }

      handleCloseModal();
      fetchTemplates();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationTemplates.failedToSave')));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(t('notificationTemplates.confirmDelete', { name }))) return;
    try {
      await apiClient.delete(
        API_ENDPOINTS.NOTIFICATION_TEMPLATES_BY_ID.replace('{{id}}', String(id)),
      );
      toast.success(t('notificationTemplates.deletedSuccessfully'));
      fetchTemplates();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationTemplates.failedToDelete')));
    }
  };

  const handlePreview = async () => {
    if (!formData.event_type || !formData.body_template.trim()) {
      toast.error(t('notificationTemplates.previewRequiresFields'));
      return;
    }
    setPreviewing(true);
    try {
      const response = await apiClient.post(API_ENDPOINTS.NOTIFICATION_TEMPLATES_PREVIEW, {
        event_type: formData.event_type,
        channel_type: formData.channel_type || 'email',
        subject_template: formData.subject_template.trim() || null,
        body_template: formData.body_template,
        sample_data: {},
      });
      setPreviewResult({
        subject: response.data.subject || '',
        body: response.data.body || '',
      });
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('notificationTemplates.previewFailed')));
    } finally {
      setPreviewing(false);
    }
  };

  // Lookup helpers
  const eventName = (type: string) => eventTypes.find((e) => e.type === type)?.name || type;
  const channelName = (type: string) => channelTypes.find((c) => c.type === type)?.name || type;
  const eventSeverity = (type: string) => eventTypes.find((e) => e.type === type)?.severity || 'info';

  // subject_template only meaningful for email channel
  const showSubjectField = formData.channel_type === 'email';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Templates List */}
      <div className="lg:col-span-2">
        <div className="bg-card rounded-2xl border border-border p-6">
          {/* Header row with add button */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              {t('notificationTemplates.templateList')}
            </h2>
            <PrimaryButton
              label={t('notificationTemplates.addTemplate')}
              onClick={() => handleOpenModal()}
              icon={Plus}
            />
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <select
              value={filterEventType}
              onChange={(e) => setFilterEventType(e.target.value)}
              className="px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">{t('common.all')} {t('notificationTemplates.eventType')}</option>
              {eventTypes.map((e) => (
                <option key={e.type} value={e.type}>{e.name}</option>
              ))}
            </select>
            <select
              value={filterChannelType}
              onChange={(e) => setFilterChannelType(e.target.value)}
              className="px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">{t('common.all')} {t('notificationTemplates.channelType')}</option>
              {channelTypes.map((c) => (
                <option key={c.type} value={c.type}>{c.name}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : templates.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">{t('notificationTemplates.noTemplates')}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('notificationTemplates.noTemplatesHint')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {templates.map((tpl) => {
                const sev = eventSeverity(tpl.event_type);
                return (
                  <div key={tpl.id} className="bg-background rounded-xl p-4 border border-border">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold text-foreground">{tpl.name}</h3>
                          {tpl.is_default && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200">
                              {t('notificationTemplates.default')}
                            </span>
                          )}
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_BADGE_COLORS[sev] || SEVERITY_BADGE_COLORS.info}`}>
                            {sev}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          {eventName(tpl.event_type)} → {channelName(tpl.channel_type)}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {t('notificationTemplates.updatedAt')}: {formatDateTime(tpl.updated_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-2">
                        <button
                          onClick={() => handleOpenModal(tpl)}
                          className="p-2 text-muted-foreground hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors"
                          title={t('common.edit')}
                        >
                          <Edit2 className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(tpl.id, tpl.name)}
                          className="p-2 text-muted-foreground hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                          title={t('common.delete')}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Help sidebar */}
      <div className="lg:col-span-1">
        <div className="bg-card rounded-2xl border border-border p-6 sticky top-6">
          <h2 className="text-lg font-semibold text-foreground mb-3 flex items-center gap-2">
            <Code className="h-5 w-5 text-muted-foreground" />
            {t('notificationTemplates.templateHelpTitle')}
          </h2>
          <p className="text-sm text-muted-foreground mb-3">
            {t('notificationTemplates.templateHelpIntro')}
          </p>
          <div className="space-y-2 text-xs">
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ event_type }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varEventType')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ event_name }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varEventName')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ severity }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varSeverity')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ source }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varSource')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ timestamp }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varTimestamp')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ description }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varDescription')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{{ data.key }}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varData')}</span>
            </div>
            <div>
              <code className="text-primary-600 dark:text-primary-400">{`{% if data %}...{% endif %}`}</code>
              <span className="text-muted-foreground ml-2">{t('notificationTemplates.varConditional')}</span>
            </div>
          </div>
          <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
            <p className="text-xs text-blue-700 dark:text-blue-300">
              {t('notificationTemplates.templateHelpNote')}
            </p>
          </div>
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-background rounded-2xl border border-border w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-background z-10">
              <h2 className="text-lg font-semibold text-foreground">
                {editingTemplate
                  ? t('notificationTemplates.editTemplate')
                  : t('notificationTemplates.addTemplate')}
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
                  {t('notificationTemplates.name')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                  placeholder={t('notificationTemplates.namePlaceholder')}
                />
              </div>

              {/* Event Type + Channel Type */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('notificationTemplates.eventType')} <span className="text-red-500">*</span>
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
                    {t('notificationTemplates.channelType')} <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={formData.channel_type}
                    onChange={(e) => setFormData((p) => ({ ...p, channel_type: e.target.value }))}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background"
                  >
                    <option value="">{t('common.select')}</option>
                    {channelTypes.map((c) => (
                      <option key={c.type} value={c.type}>{c.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Subject Template (only for email) */}
              {showSubjectField && (
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    {t('notificationTemplates.subjectTemplate')}
                    <span className="text-xs text-muted-foreground ml-2">
                      ({t('notificationTemplates.optional')})
                    </span>
                  </label>
                  <input
                    type="text"
                    value={formData.subject_template}
                    onChange={(e) => setFormData((p) => ({ ...p, subject_template: e.target.value }))}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background font-mono text-sm"
                    placeholder={t('notificationTemplates.subjectPlaceholder')}
                  />
                </div>
              )}

              {/* Body Template */}
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  {t('notificationTemplates.bodyTemplate')} <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={formData.body_template}
                  onChange={(e) => setFormData((p) => ({ ...p, body_template: e.target.value }))}
                  rows={10}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none bg-background font-mono text-sm"
                  placeholder={t('notificationTemplates.bodyPlaceholder')}
                />
              </div>

              {/* Is Default */}
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={formData.is_default}
                    onChange={(e) => setFormData((p) => ({ ...p, is_default: e.target.checked }))}
                    className="rounded border-border text-primary-600 focus:ring-primary-500"
                  />
                  {t('notificationTemplates.isDefault')}
                </label>
              </div>

              {/* Preview Result */}
              {previewResult && (
                <div className="border border-border rounded-lg p-4 space-y-3 bg-muted/30">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    {t('notificationTemplates.previewResult')}
                  </h3>
                  {previewResult.subject && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">{t('notificationTemplates.subjectLabel')}</p>
                      <pre className="text-sm bg-background p-2 rounded border border-border whitespace-pre-wrap">{previewResult.subject}</pre>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">{t('notificationTemplates.bodyLabel')}</p>
                    <pre className="text-sm bg-background p-2 rounded border border-border whitespace-pre-wrap">{previewResult.body}</pre>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-between gap-3 pt-4 border-t border-border sticky bottom-0 bg-background">
                <PrimaryButton
                  type="button"
                  variant="secondary"
                  label={t('notificationTemplates.preview')}
                  icon={Eye}
                  onClick={handlePreview}
                  loading={previewing}
                />
                <div className="flex gap-3">
                  <PrimaryButton
                    type="button"
                    variant="secondary"
                    label={t('common.cancel')}
                    onClick={handleCloseModal}
                  />
                  <PrimaryButton
                    type="button"
                    label={editingTemplate ? t('common.save') : t('common.create')}
                    icon={Save}
                    onClick={handleSubmit}
                    loading={saving}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationTemplates;
