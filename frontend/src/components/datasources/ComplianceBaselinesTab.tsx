import { useState, useMemo, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  Trash2,
  Server,
  Clock,
  Plug,
  RefreshCw,
  CheckCircle,
  XCircle,
  Pencil,
  Shield,
  ShieldCheck,
  Ban,
  Unlock,
} from 'lucide-react';
import { useComplianceBaselines, ComplianceBaselineItem, useDataSources, useSettings, BLOCK_TIME_PRESETS } from '@/hooks/useTerminalData';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, formatDate } from '@/lib/utils';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { DeletePreviewModal, DeletePreviewData } from '@/components/DeletePreviewModal';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { Modal } from '@/components/Modal';
import {
  BASELINE_CONFIG_FIELDS,
  BASELINE_TYPE_BADGE,
  buildConfigPayload,
  populateConfigFromItem,
  getDefaultConfig,
} from './shared';

interface ComplianceBaselinesTabProps {
  onAddClick: () => void;
}

const ComplianceBaselinesTab = forwardRef<{ openAddModal: () => void }, ComplianceBaselinesTabProps>(({ onAddClick }, ref) => {
  const { t } = useTranslation();
  const { data: baselines, isLoading: blLoading, refetch: blRefetch } = useComplianceBaselines();

  // Expose openAddModal to parent via ref
  useImperativeHandle(ref, () => ({
    openAddModal: () => {
      resetBlForm();
      handleBlTypeChange('ipguard');
      setShowAddBlModal(true);
    },
  }));

  // Pagination
  const [blPage, setBlPage] = useState(1);
  const [blPageSize, setBlPageSize] = useState(10);

  // Add Baseline modal
  const [showAddBlModal, setShowAddBlModal] = useState(false);
  const [blForm, setBlForm] = useState({
    name: '',
    type: 'ipguard',
    tag: '',
    enabled: true,
  });
  const [blConfig, setBlConfig] = useState<Record<string, string>>({});
  const [isAddingBl, setIsAddingBl] = useState(false);

  // Delete Baseline modal
  const [showDeleteBlModal, setShowDeleteBlModal] = useState(false);
  const [deleteBlItem, setDeleteBlItem] = useState<ComplianceBaselineItem | null>(null);
  const [isDeletingBl, setIsDeletingBl] = useState(false);
  const [blPreviewData, setBlPreviewData] = useState<DeletePreviewData | null>(null);
  const [isLoadingBlPreview, setIsLoadingBlPreview] = useState(false);

  // Test Baseline connection
  const [blTestingId, setBlTestingId] = useState<number | null>(null);
  const [blTestResult, setBlTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);

  // Edit Baseline modal
  const [showEditBlModal, setShowEditBlModal] = useState(false);
  const [editBlForm, setEditBlForm] = useState({
    id: 0,
    name: '',
    type: 'ipguard',
    tag: '',
    enabled: true,
  });
  const [editBlConfig, setEditBlConfig] = useState<Record<string, string>>({});
  const [isEditingBl, setIsEditingBl] = useState(false);

  // Sync Baseline
  const [blSyncingId, setBlSyncingId] = useState<number | null>(null);

  // Derived data
  const blList = baselines || [];
  const blTotalPages = Math.max(1, Math.ceil(blList.length / blPageSize));
  const paginatedBl = useMemo(() => {
    const start = (blPage - 1) * blPageSize;
    return blList.slice(start, start + blPageSize);
  }, [blList, blPage, blPageSize]);

  // Handlers
  const handleBlTypeChange = (newType: string) => {
    setBlForm((prev) => ({ ...prev, type: newType }));
    const fields = BASELINE_CONFIG_FIELDS[newType] || [];
    setBlConfig(getDefaultConfig(fields));
  };

  const handleAddBl = async () => {
    if (!blForm.name.trim()) {
      toast.error(t('baselines.pleaseEnterName'));
      return;
    }
    if (!blForm.tag.trim()) {
      toast.error(t('baselines.pleaseEnterTag'));
      return;
    }

    setIsAddingBl(true);
    try {
      const fields = BASELINE_CONFIG_FIELDS[blForm.type] || [];
      const config = buildConfigPayload(fields, blConfig);

      await apiClient.post(API_ENDPOINTS.COMPLIANCE_BASELINES, {
        name: blForm.name,
        type: blForm.type,
        tag: blForm.tag,
        config,
        enabled: blForm.enabled,
      });
      toast.success(t('baselines.baselineCreated'));
      setShowAddBlModal(false);
      resetBlForm();
      blRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('baselines.failedToCreateBaseline')));
    } finally {
      setIsAddingBl(false);
    }
  };

  const resetBlForm = () => {
    setBlForm({ name: '', type: 'ipguard', tag: '', enabled: true });
    setBlConfig({});
  };

  const openDeleteBlModal = async (bl: ComplianceBaselineItem) => {
    setDeleteBlItem(bl);
    setShowDeleteBlModal(true);
    setIsLoadingBlPreview(true);
    setBlPreviewData(null);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.COMPLIANCE_BASELINE_DELETE_PREVIEW}${bl.id}/delete-preview`);
      setBlPreviewData(response.data);
    } catch (error: unknown) {
      setBlPreviewData(null);
      toast.error(getErrorMessage(error, t('deletePreview.failedToAnalyze')));
    } finally {
      setIsLoadingBlPreview(false);
    }
  };

  const handleDeleteBl = async () => {
    if (!deleteBlItem) return;
    setIsDeletingBl(true);
    try {
      await apiClient.delete(`${API_ENDPOINTS.COMPLIANCE_BASELINES}${deleteBlItem.id}`);
      toast.success(t('baselines.baselineDeleted'));
      blRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('baselines.failedToDeleteBaseline')));
    } finally {
      setIsDeletingBl(false);
      setShowDeleteBlModal(false);
      setDeleteBlItem(null);
      setBlPreviewData(null);
    }
  };

  const handleTestBlConnection = async (bl: ComplianceBaselineItem) => {
    setBlTestingId(bl.id);
    setBlTestResult(null);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.COMPLIANCE_BASELINES}${bl.id}/test`);
      const data = response.data;
      setBlTestResult({ id: bl.id, success: data.success ?? true, message: data.message || data.detail || t('baselines.connectionSuccessful') });
      if (data.success ?? true) {
        toast.success(t('baselines.connectionSuccessful'));
      } else {
        toast.error(`${t('baselines.connectionFailed')}: ${data.message || data.detail || ''}`);
      }
    } catch (error: unknown) {
      const msg = getErrorMessage(error, t('baselines.connectionFailed'));
      setBlTestResult({ id: bl.id, success: false, message: msg });
      toast.error(`${t('baselines.connectionFailed')}: ${msg}`);
    } finally {
      setBlTestingId(null);
    }
  };

  const openEditBlModal = (bl: ComplianceBaselineItem) => {
    setEditBlForm({
      id: bl.id,
      name: bl.name,
      type: bl.type,
      tag: bl.tag,
      enabled: bl.enabled,
    });
    const fields = BASELINE_CONFIG_FIELDS[bl.type] || [];
    const rawConfig = bl.config || {};
    setEditBlConfig(populateConfigFromItem(fields, rawConfig));
    setShowEditBlModal(true);
  };

  const handleEditBl = async () => {
    if (!editBlForm.name.trim()) {
      toast.error(t('baselines.pleaseEnterName'));
      return;
    }
    if (!editBlForm.tag.trim()) {
      toast.error(t('baselines.pleaseEnterTag'));
      return;
    }

    setIsEditingBl(true);
    try {
      const fields = BASELINE_CONFIG_FIELDS[editBlForm.type] || [];
      const config = buildConfigPayload(fields, editBlConfig);

      await apiClient.put(`${API_ENDPOINTS.COMPLIANCE_BASELINES}${editBlForm.id}`, {
        name: editBlForm.name,
        type: editBlForm.type,
        tag: editBlForm.tag,
        config,
        enabled: editBlForm.enabled,
      });
      toast.success(t('baselines.baselineUpdated'));
      setShowEditBlModal(false);
      blRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('baselines.failedToUpdateBaseline')));
    } finally {
      setIsEditingBl(false);
    }
  };

  const handleSyncBl = async (bl: ComplianceBaselineItem) => {
    setBlSyncingId(bl.id);
    try {
      await apiClient.post(`${API_ENDPOINTS.COMPLIANCE_BASELINES}${bl.id}/sync`);
      toast.success(t('baselines.syncedSuccessfully'));
      blRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('baselines.failedToSync')));
    } finally {
      setBlSyncingId(null);
    }
  };

  // Render helpers
  const renderEnabledBadge = (enabled: boolean) => (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${enabled ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
      {enabled ? t('common.enabled') : t('common.disabled')}
    </span>
  );

  const renderLastSync = (bl: ComplianceBaselineItem) => {
    if (!bl.last_sync_at) {
      return <span className="text-sm text-muted-foreground">{t('common.never')}</span>;
    }
    const statusColor = bl.last_sync_status === 'success'
      ? 'text-green-600'
      : bl.last_sync_status === 'failed'
        ? 'text-red-600'
        : 'text-muted-foreground';
    return (
      <div>
        <span className={`text-sm font-medium ${statusColor}`}>
          {bl.last_sync_status === 'success' ? t('baselines.lastSyncStatus.success') : bl.last_sync_status === 'failed' ? t('baselines.lastSyncStatus.failed') : bl.last_sync_status}
        </span>
        <div className="flex items-center text-xs text-muted-foreground mt-0.5">
          <Clock className="h-3 w-3 mr-1" />
          {formatDate(bl.last_sync_at)}
        </div>
        {bl.last_sync_error && (
          <p className="text-xs text-red-500 mt-0.5 max-w-xs truncate" title={bl.last_sync_error}>
            {bl.last_sync_error}
          </p>
        )}
      </div>
    );
  };

  // E1: Compliance operations state
  const queryClient = useQueryClient();
  const { data: dataSources } = useDataSources();
  const { data: configs } = useSettings();
  const arpSources = useMemo(
    () => (dataSources || []).filter((ds) => ds.type === 'arp_ssh' || ds.type === 'arp_api'),
    [dataSources],
  );
  const [selectedTag, setSelectedTag] = useState('');
  const [complianceLoading, setComplianceLoading] = useState(false);
  const [autoBlockLoading, setAutoBlockLoading] = useState(false);
  const [autoUnblockLoading, setAutoUnblockLoading] = useState(false);
  const [forceCheck, setForceCheck] = useState(false);
  const [showAutoBlockModal, setShowAutoBlockModal] = useState(false);
  const [autoBlockTime, setAutoBlockTime] = useState('30d');

  const handleComplianceCheck = async () => {
    setComplianceLoading(true);
    try {
      const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_CHECK, {
        arp_source_tag: selectedTag || undefined,
        force: forceCheck,
      });
      const r = response.data;
      toast.success(t('compliance.checkComplete', {
        total: r.total_checked, compliant: r.compliant,
        bypass: r.bypass, nonCompliant: r.non_compliant,
      }));
      queryClient.invalidateQueries({ queryKey: ['terminals'] });
    } catch (err) {
      toast.error(getErrorMessage(err, t('compliance.checkFailed')));
    } finally {
      setComplianceLoading(false);
    }
  };

  const handleAutoBlockClick = () => {
    if (!selectedTag) { toast.warning(t('compliance.selectSourceTag')); return; }
    setAutoBlockTime(configs?.compliance?.block_time || '30d');
    setShowAutoBlockModal(true);
  };

  const handleAutoBlockConfirm = async () => {
    setShowAutoBlockModal(false);
    setAutoBlockLoading(true);
    try {
      const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_BLOCK, {
        arp_source_tag: selectedTag,
        block_time: autoBlockTime,
        dry_run: false,
      });
      const r = response.data;
      toast.success(t('compliance.autoBlockComplete', {
        total: r.total_non_compliant, blocked: r.blocked, skipped: r.skipped,
      }));
      if (r.total_non_compliant === 0) {
        toast.info(t('compliance.autoBlockNoAction'));
      }
      if (r.errors?.length) toast.warning(t('compliance.partialErrors', { count: r.errors.length }));
      queryClient.invalidateQueries({ queryKey: ['terminals'] });
      queryClient.invalidateQueries({ queryKey: ['blacklist'] });
    } catch (err) {
      toast.error(getErrorMessage(err, t('compliance.autoBlockFailed')));
    } finally {
      setAutoBlockLoading(false);
    }
  };

  const handleAutoUnblock = async () => {
    setAutoUnblockLoading(true);
    try {
      const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_UNBLOCK);
      const r = response.data;
      toast.success(t('compliance.autoUnblockComplete', {
        total: r.total_auto_blocked, unblocked: r.unblocked, skipped: r.skipped,
      }));
      if (r.unblocked === 0 && r.skipped > 0) {
        toast.info(t('compliance.autoUnblockNoAction'));
      }
      if (r.errors?.length) toast.warning(t('compliance.partialErrors', { count: r.errors.length }));
      queryClient.invalidateQueries({ queryKey: ['terminals'] });
      queryClient.invalidateQueries({ queryKey: ['blacklist'] });
    } catch (err) {
      toast.error(getErrorMessage(err, t('compliance.autoUnblockFailed')));
    } finally {
      setAutoUnblockLoading(false);
    }
  };

  return (
    <>
      {/* E1: Compliance operations */}
      <div className="mb-4 bg-card rounded-2xl border border-border p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('compliance.sourceTagLabel')}</label>
            <select
              value={selectedTag}
              onChange={(e) => setSelectedTag(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">{t('common.all')}</option>
              {arpSources.map((ds) => (
                <option key={ds.id} value={ds.tag}>{ds.tag} ({ds.name})</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer pb-2">
            <input
              type="checkbox"
              checked={forceCheck}
              onChange={(e) => setForceCheck(e.target.checked)}
              className="rounded border-input"
            />
            {t('compliance.forceRecheck')}
          </label>
          <PrimaryButton
            icon={ShieldCheck}
            label={t('compliance.runCheck')}
            onClick={handleComplianceCheck}
            loading={complianceLoading}
            variant="primary"
          />
          <PrimaryButton
            icon={Ban}
            label={t('compliance.autoBlock')}
            onClick={handleAutoBlockClick}
            loading={autoBlockLoading}
            variant="danger"
          />
          <PrimaryButton
            icon={Unlock}
            label={t('compliance.autoUnblock')}
            onClick={handleAutoUnblock}
            loading={autoUnblockLoading}
            variant="success"
          />
        </div>
      </div>
      {/* Auto Block confirmation modal */}
      <Modal isOpen={showAutoBlockModal} onClose={() => setShowAutoBlockModal(false)} title={t('compliance.confirmAutoBlock')} size="sm">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
              <Ban className="h-5 w-5 text-red-600" />
            </div>
            <p className="text-sm text-muted-foreground">{t('compliance.autoBlockWarning')}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('blacklist.blockDuration')}</label>
            <select
              value={autoBlockTime}
              onChange={(e) => setAutoBlockTime(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {BLOCK_TIME_PRESETS.map((bt) => (
                <option key={bt} value={bt}>{bt}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <PrimaryButton label={t('common.cancel')} onClick={() => setShowAutoBlockModal(false)} variant="secondary" />
            <PrimaryButton label={t('common.confirm')} onClick={handleAutoBlockConfirm} variant="danger" loading={autoBlockLoading} />
          </div>
        </div>
      </Modal>
      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('baselines.name')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('baselines.type')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('baselines.tag')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('baselines.enabled')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('baselines.lastSync')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {blLoading ? (
                <tr>
                  <td colSpan={6}>
                    <LoadingState message={t('baselines.loadingBaselines')} />
                  </td>
                </tr>
              ) : blList.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={Shield}
                      title={t('baselines.noBaselines')}
                      description={t('baselines.addBaselineDescription')}
                      action={{ label: t('baselines.addBaseline'), onClick: onAddClick }}
                    />
                  </td>
                </tr>
              ) : (
                paginatedBl.map((bl) => (
                  <tr key={bl.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 text-muted-foreground mr-2 flex-shrink-0" />
                        <span className="text-sm font-medium text-foreground">{bl.name}</span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {(() => {
                        const badge = BASELINE_TYPE_BADGE[bl.type];
                        if (!badge) return <span className="text-sm text-muted-foreground">{bl.type}</span>;
                        return (
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>
                            {badge.label}
                          </span>
                        );
                      })()}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground">
                        {bl.tag}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {renderEnabledBadge(bl.enabled)}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {renderLastSync(bl)}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={blTestingId === bl.id ? RefreshCw : Plug}
                          variant="primary"
                          size="md"
                          title={t('baselines.testConnection')}
                          onClick={() => handleTestBlConnection(bl)}
                          loading={blTestingId === bl.id}
                        />
                        <IconButton
                          icon={Pencil}
                          variant="primary"
                          size="md"
                          title={t('baselines.editBaseline')}
                          onClick={() => openEditBlModal(bl)}
                        />
                        <IconButton
                          icon={RefreshCw}
                          variant="secondary"
                          size="md"
                          title={t('baselines.syncBaseline')}
                          onClick={() => handleSyncBl(bl)}
                          loading={blSyncingId === bl.id}
                        />
                        <IconButton
                          icon={Trash2}
                          variant="danger"
                          size="md"
                          title={t('baselines.deleteBaseline')}
                          onClick={() => openDeleteBlModal(bl)}
                        />
                      </ButtonGroup>
                      {/* Test result inline */}
                      {blTestResult && blTestResult.id === bl.id && (
                        <div className={`mt-1 text-xs flex items-center gap-1 ${blTestResult.success ? 'text-green-600' : 'text-red-600'}`}>
                          {blTestResult.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                          <span className="max-w-[200px] truncate" title={blTestResult.message}>{blTestResult.message}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          currentPage={blPage}
          totalPages={blTotalPages}
          onPageChange={setBlPage}
          pageSize={blPageSize}
          onPageSizeChange={(s) => { setBlPageSize(s); setBlPage(1); }}
          totalItems={blList.length}
          variant="bottom"
        />
      </div>

      {/* Add Compliance Baseline Modal */}
      <Modal isOpen={showAddBlModal} onClose={() => { setShowAddBlModal(false); resetBlForm(); }} title={t('baselines.addBaseline')} size="lg">
        <p className="text-sm text-muted-foreground mb-6">{t('baselines.configureNewBaseline')}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('baselines.name')}</label>
            <input
              type="text"
              placeholder="My Compliance Baseline"
              value={blForm.name}
              onChange={(e) => setBlForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('baselines.type')}</label>
            <select
              value={blForm.type}
              onChange={(e) => handleBlTypeChange(e.target.value)}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="ipguard">IP-Guard</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('baselines.tag')}</label>
            <input
              type="text"
              placeholder="unique-tag"
              value={blForm.tag}
              onChange={(e) => setBlForm((prev) => ({ ...prev, tag: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          {(BASELINE_CONFIG_FIELDS[blForm.type] || []).map((field) => (
            <div key={field.key}>
              <label className="block text-sm font-medium text-muted-foreground mb-1">{field.label}</label>
              {field.type === 'select' ? (
                <select
                  value={blConfig[field.key] ?? field.defaultValue ?? ''}
                  onChange={(e) => setBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  {field.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.type}
                  placeholder={field.placeholder}
                  value={blConfig[field.key] ?? field.defaultValue ?? ''}
                  onChange={(e) => setBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              )}
            </div>
          ))}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="bl-enabled"
              checked={blForm.enabled}
              onChange={(e) => setBlForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              className="h-4 w-4 text-blue-600 border-border rounded focus:ring-blue-500"
            />
            <label htmlFor="bl-enabled" className="text-sm font-medium text-muted-foreground">{t('baselines.enabled')}</label>
          </div>
          <div className="flex gap-3 pt-4">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => { setShowAddBlModal(false); resetBlForm(); }}
              className="flex-1"
            />
            <PrimaryButton
              icon={Plus}
              label={t('common.create')}
              variant="success"
              onClick={handleAddBl}
              loading={isAddingBl}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Edit Compliance Baseline Modal */}
      <Modal isOpen={showEditBlModal} onClose={() => setShowEditBlModal(false)} title={t('baselines.editBaselineTitle')} size="lg">
        <p className="text-sm text-muted-foreground mb-6">{t('baselines.updateBaselineSettings')}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('baselines.name')}</label>
            <input
              type="text"
              placeholder="My Compliance Baseline"
              value={editBlForm.name}
              onChange={(e) => setEditBlForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('baselines.type')}</label>
            <select
              value={editBlForm.type}
              onChange={(e) => {
                setEditBlForm((prev) => ({ ...prev, type: e.target.value }));
                const fields = BASELINE_CONFIG_FIELDS[e.target.value] || [];
                const defaults: Record<string, string> = {};
                fields.forEach((f) => {
                  defaults[f.key] = editBlConfig[f.key] ?? f.defaultValue ?? '';
                });
                setEditBlConfig(defaults);
              }}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="ipguard">IP-Guard</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('baselines.tag')}</label>
            <input
              type="text"
              placeholder="unique-tag"
              value={editBlForm.tag}
              onChange={(e) => setEditBlForm((prev) => ({ ...prev, tag: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          {(BASELINE_CONFIG_FIELDS[editBlForm.type] || []).map((field) => (
            <div key={field.key}>
              <label className="block text-sm font-medium text-muted-foreground mb-1">{field.label}</label>
              {field.type === 'select' ? (
                <select
                  value={editBlConfig[field.key] ?? field.defaultValue ?? ''}
                  onChange={(e) => setEditBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  {field.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.type}
                  placeholder={field.placeholder}
                  value={editBlConfig[field.key] ?? field.defaultValue ?? ''}
                  onChange={(e) => setEditBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              )}
            </div>
          ))}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="edit-bl-enabled"
              checked={editBlForm.enabled}
              onChange={(e) => setEditBlForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              className="h-4 w-4 text-blue-600 border-border rounded focus:ring-blue-500"
            />
            <label htmlFor="edit-bl-enabled" className="text-sm font-medium text-muted-foreground">{t('baselines.enabled')}</label>
          </div>
          <div className="flex gap-3 pt-4">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => setShowEditBlModal(false)}
              className="flex-1"
            />
            <PrimaryButton
              icon={Pencil}
              label={t('common.update')}
              variant="primary"
              onClick={handleEditBl}
              loading={isEditingBl}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Delete Compliance Baseline Modal */}
      <DeletePreviewModal
        isOpen={showDeleteBlModal}
        onClose={() => { setShowDeleteBlModal(false); setDeleteBlItem(null); setBlPreviewData(null); }}
        onConfirm={handleDeleteBl}
        title={t('baselines.deleteBaselineTitle')}
        itemName={deleteBlItem?.name || ''}
        itemTag={deleteBlItem?.tag}
        previewData={blPreviewData}
        isLoadingPreview={isLoadingBlPreview}
        isDeleting={isDeletingBl}
      />
    </>
  );
});

ComplianceBaselinesTab.displayName = 'ComplianceBaselinesTab';

export default ComplianceBaselinesTab;
