import { useState, useMemo, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Trash2,
  Server,
  Clock,
  CheckCircle,
  XCircle,
  Pencil,
  Plug,
  AlertTriangle,
} from 'lucide-react';
import { useDataSources, DataSourceItem } from '@/hooks/useTerminalData';
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
  CONFIG_FIELDS,
  TYPE_BADGE,
  buildConfigPayload,
  populateConfigFromItem,
  getDefaultConfig,
} from './shared';

const OPERATION_SOURCE_TYPE = 'sangfor';

interface OperationSourceTabProps {
  onAddClick: () => void;
}

const OperationSourceTab = forwardRef<{ openAddModal: () => void }, OperationSourceTabProps>(({ onAddClick }, ref) => {
  const { t } = useTranslation();
  const { data: dataSources, isLoading: dsLoading, refetch: dsRefetch } = useDataSources();

  useImperativeHandle(ref, () => ({
    openAddModal: () => {
      resetOsForm();
      handleOsTypeChange(OPERATION_SOURCE_TYPE);
      setShowAddOsModal(true);
    },
  }));

  const [osPage, setOsPage] = useState(1);
  const [osPageSize, setOsPageSize] = useState(10);

  const [showAddOsModal, setShowAddOsModal] = useState(false);
  const [osForm, setOsForm] = useState({
    name: '',
    type: OPERATION_SOURCE_TYPE,
    tag: '',
    enabled: true,
  });
  const [osConfig, setOsConfig] = useState<Record<string, string>>({});
  const [isAddingOs, setIsAddingOs] = useState(false);

  const [showDeleteOsModal, setShowDeleteOsModal] = useState(false);
  const [deleteOsItem, setDeleteOsItem] = useState<DataSourceItem | null>(null);
  const [isDeletingOs, setIsDeletingOs] = useState(false);
  const [deletePreviewData, setDeletePreviewData] = useState<DeletePreviewData | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);

  const [showEditOsModal, setShowEditOsModal] = useState(false);
  const [editOsForm, setEditOsForm] = useState({
    id: 0,
    name: '',
    type: OPERATION_SOURCE_TYPE,
    tag: '',
    enabled: true,
  });
  const [editOsConfig, setEditOsConfig] = useState<Record<string, string>>({});
  const [isEditingOs, setIsEditingOs] = useState(false);

  const [showDisableWarning, setShowDisableWarning] = useState(false);
  const [disablePreviewData, setDisablePreviewData] = useState<{
    can_disable: boolean;
    warnings: string[];
    affected_terminals: number;
    actions: { action: string; description: string; firewall_tag?: string; count?: number }[];
  } | null>(null);

  const osList = useMemo(() => {
    return (dataSources || []).filter((ds: DataSourceItem) => ds.type === OPERATION_SOURCE_TYPE);
  }, [dataSources]);

  const osTotalPages = Math.max(1, Math.ceil(osList.length / osPageSize));
  const paginatedOs = useMemo(() => {
    const start = (osPage - 1) * osPageSize;
    return osList.slice(start, start + osPageSize);
  }, [osList, osPage, osPageSize]);

  const handleOsTypeChange = (newType: string) => {
    setOsForm((prev) => ({ ...prev, type: newType }));
    const fields = CONFIG_FIELDS[newType] || [];
    setOsConfig(getDefaultConfig(fields));
  };

  const handleAddOs = async () => {
    if (!osForm.name.trim()) {
      toast.error(t('dataSources.pleaseEnterName'));
      return;
    }
    if (!osForm.tag.trim()) {
      toast.error(t('dataSources.pleaseEnterTag'));
      return;
    }

    setIsAddingOs(true);
    try {
      const fields = CONFIG_FIELDS[osForm.type] || [];
      const config = buildConfigPayload(fields, osConfig);

      await apiClient.post(API_ENDPOINTS.DATA_SOURCES, {
        name: osForm.name,
        type: osForm.type,
        tag: osForm.tag,
        config,
        enabled: osForm.enabled,
      });
      toast.success(t('dataSources.dataSourceCreated'));
      setShowAddOsModal(false);
      resetOsForm();
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToCreate')));
    } finally {
      setIsAddingOs(false);
    }
  };

  const resetOsForm = () => {
    setOsForm({ name: '', type: OPERATION_SOURCE_TYPE, tag: '', enabled: true });
    setOsConfig({});
  };

  const openDeleteOsModal = async (ds: DataSourceItem) => {
    setDeleteOsItem(ds);
    setShowDeleteOsModal(true);
    setIsLoadingPreview(true);
    setDeletePreviewData(null);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.DATA_SOURCE_DELETE_PREVIEW}${ds.id}/delete-preview`);
      setDeletePreviewData(response.data);
    } catch (error: unknown) {
      setDeletePreviewData(null);
      toast.error(getErrorMessage(error, t('deletePreview.failedToAnalyze')));
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleDeleteOs = async () => {
    if (!deleteOsItem) return;
    setIsDeletingOs(true);
    try {
      await apiClient.delete(`${API_ENDPOINTS.DATA_SOURCES}${deleteOsItem.id}`);
      toast.success(t('dataSources.dataSourceDeleted', { name: deleteOsItem.name }));
      setShowDeleteOsModal(false);
      setDeleteOsItem(null);
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToDelete')));
    } finally {
      setIsDeletingOs(false);
    }
  };

  const handleTestConnection = async (ds: DataSourceItem) => {
    setTestingId(ds.id);
    setTestResult(null);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.DATA_SOURCES}${ds.id}/test`);
      const data = response.data;
      if (data.success) {
        setTestResult({ id: ds.id, success: true, message: data.message || t('dataSources.connectionSuccess') });
        toast.success(t('dataSources.connectionSuccess'));
        dsRefetch();
      } else {
        toast.error(`${t('dataSources.connectionFailed')}: ${data.message || data.detail || t('common.error')}`);
      }
    } catch (error: unknown) {
      const msg = getErrorMessage(error, t('dataSources.connectionFailed'));
      setTestResult({ id: ds.id, success: false, message: msg });
      toast.error(`${t('dataSources.connectionFailed')}: ${msg}`);
    } finally {
      setTestingId(null);
    }
  };

  const openEditOsModal = (ds: DataSourceItem) => {
    setEditOsForm({
      id: ds.id,
      name: ds.name,
      type: ds.type,
      tag: ds.tag,
      enabled: ds.enabled,
    });
    const fields = CONFIG_FIELDS[ds.type] || [];
    const rawConfig = ds.config || {};
    setEditOsConfig(populateConfigFromItem(fields, rawConfig));
    setShowEditOsModal(true);
  };

  const handleEditOs = async () => {
    if (!editOsForm.name.trim()) {
      toast.error(t('dataSources.pleaseEnterName'));
      return;
    }
    if (!editOsForm.tag.trim()) {
      toast.error(t('dataSources.pleaseEnterTag'));
      return;
    }

    const currentDs = dataSources?.find((d: DataSourceItem) => d.id === editOsForm.id);

    if (!editOsForm.enabled && currentDs && currentDs.enabled) {
      try {
        const previewResp = await apiClient.post(`${API_ENDPOINTS.DATA_SOURCES}${editOsForm.id}/disable-preview`);
        const preview = previewResp.data;
        if (preview.warnings?.length > 0 || preview.affected_terminals > 0) {
          setDisablePreviewData(preview);
          setShowDisableWarning(true);
          return;
        }
      } catch {
      }
    }

    await doUpdateOperationSource();
  };

  const doUpdateOperationSource = async () => {
    setIsEditingOs(true);
    try {
      const fields = CONFIG_FIELDS[editOsForm.type] || [];
      const config = buildConfigPayload(fields, editOsConfig);

      await apiClient.put(`${API_ENDPOINTS.DATA_SOURCES}${editOsForm.id}`, {
        name: editOsForm.name,
        type: editOsForm.type,
        tag: editOsForm.tag,
        config,
        enabled: editOsForm.enabled,
      });
      toast.success(t('dataSources.dataSourceUpdated'));
      setShowEditOsModal(false);
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToUpdate')));
    } finally {
      setIsEditingOs(false);
    }
  };

  const confirmDisable = async () => {
    setShowDisableWarning(false);
    await doUpdateOperationSource();
  };

  const getStatusBadge = (ds: DataSourceItem) => {
    if (!ds.enabled) return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">{t('common.disabled')}</span>;
    return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">{t('common.enabled')}</span>;
  };

  const getTypeBadge = (ds: DataSourceItem) => {
    const badge = TYPE_BADGE[ds.type];
    if (!badge) return null;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badge.className}`}>{badge.label}</span>;
  };

  return (
    <div>
      {dsLoading ? (
        <LoadingState message={t('dataSources.loading')} />
      ) : osList.length === 0 ? (
        <EmptyState
          icon={Server}
          title={t('dataSources.noSources')}
          description={t('dataSources.addFirstSource')}
          action={{ label: t('dataSources.addOperationSource'), onClick: onAddClick }}
        />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full divide-y divide-border">
              <thead className="bg-card">
                <tr>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('dataSources.name')}</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('dataSources.type')}</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('dataSources.tag')}</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('dataSources.status')}</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('dataSources.lastTest')}</th>
                  <th className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paginatedOs.map((ds: DataSourceItem) => (
                  <tr key={ds.id}>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 mr-2 text-muted-foreground" />
                        <span className="font-medium text-foreground">{ds.name}</span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">{getTypeBadge(ds)}</td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-foreground">{ds.tag}</td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">{getStatusBadge(ds)}</td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      {ds.last_sync_at ? formatDate(ds.last_sync_at) : t('common.never')}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={Pencil}
                          onClick={() => openEditOsModal(ds)}
                          title={t('common.edit')}
                          variant="primary"
                          size="md"
                        />
                        <IconButton
                          icon={testingId === ds.id ? Clock : testResult?.id === ds.id && testResult.success ? CheckCircle : testResult?.id === ds.id ? XCircle : Plug}
                          onClick={() => handleTestConnection(ds)}
                          title={t('dataSources.testConnection')}
                          loading={testingId === ds.id}
                          variant="primary"
                          size="md"
                        />
                        <IconButton
                          icon={Trash2}
                          onClick={() => openDeleteOsModal(ds)}
                          title={t('common.delete')}
                          variant="danger"
                          size="md"
                        />
                      </ButtonGroup>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex justify-end">
            <Pagination
              currentPage={osPage}
              totalPages={osTotalPages}
              onPageChange={setOsPage}
              pageSize={osPageSize}
              onPageSizeChange={setOsPageSize}
              pageSizeOptions={[10, 25, 50]}
            />
          </div>
        </>
      )}

      <Modal
        title={t('dataSources.addOperationSource')}
        isOpen={showAddOsModal}
        onClose={() => setShowAddOsModal(false)}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t('dataSources.name')}</label>
            <input
              type="text"
              value={osForm.name}
              onChange={(e) => setOsForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder={t('dataSources.enterName')}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t('dataSources.tag')}</label>
            <input
              type="text"
              value={osForm.tag}
              onChange={(e) => setOsForm((prev) => ({ ...prev, tag: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder={t('dataSources.enterTag')}
            />
          </div>
          <div className="space-y-3">
            <label className="block text-sm font-medium text-foreground">{t('dataSources.config')}</label>
            {(CONFIG_FIELDS[OPERATION_SOURCE_TYPE] || []).map((field) => (
              <div key={field.key}>
                <label className="block text-xs text-muted-foreground mb-1">{field.label}</label>
                {field.type === 'select' ? (
                  <select
                    value={osConfig[field.key] || ''}
                    onChange={(e) => setOsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  >
                    {field.options?.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                ) : field.type === 'password' ? (
                  <input
                    type="password"
                    value={osConfig[field.key] || ''}
                    onChange={(e) => setOsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    placeholder={field.placeholder || ''}
                  />
                ) : (
                  <input
                    type={field.type}
                    value={osConfig[field.key] || ''}
                    onChange={(e) => setOsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    placeholder={field.placeholder || ''}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center">
            <input
              type="checkbox"
              checked={osForm.enabled}
              onChange={(e) => setOsForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              className="rounded border-border bg-background text-blue-600 focus:ring-blue-500"
            />
            <label className="ml-2 text-sm text-foreground">{t('common.enabled')}</label>
          </div>
        </div>
        <div className="mt-6 flex justify-end space-x-3">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => setShowAddOsModal(false)}
          />
          <PrimaryButton
            label={t('common.create')}
            variant="success"
            onClick={handleAddOs}
            loading={isAddingOs}
          />
        </div>
      </Modal>

      <Modal
        title={t('dataSources.editSource')}
        isOpen={showEditOsModal}
        onClose={() => setShowEditOsModal(false)}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t('dataSources.name')}</label>
            <input
              type="text"
              value={editOsForm.name}
              onChange={(e) => setEditOsForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder={t('dataSources.enterName')}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t('dataSources.tag')}</label>
            <input
              type="text"
              value={editOsForm.tag}
              onChange={(e) => setEditOsForm((prev) => ({ ...prev, tag: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder={t('dataSources.enterTag')}
            />
          </div>
          <div className="space-y-3">
            <label className="block text-sm font-medium text-foreground">{t('dataSources.config')}</label>
            {(CONFIG_FIELDS[editOsForm.type] || []).map((field) => (
              <div key={field.key}>
                <label className="block text-xs text-muted-foreground mb-1">{field.label}</label>
                {field.type === 'select' ? (
                  <select
                    value={editOsConfig[field.key] || ''}
                    onChange={(e) => setEditOsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  >
                    {field.options?.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                ) : field.type === 'password' ? (
                  <input
                    type="password"
                    value={editOsConfig[field.key] || ''}
                    onChange={(e) => setEditOsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    placeholder={field.placeholder || ''}
                  />
                ) : (
                  <input
                    type={field.type}
                    value={editOsConfig[field.key] || ''}
                    onChange={(e) => setEditOsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    placeholder={field.placeholder || ''}
                  />
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center">
            <input
              type="checkbox"
              checked={editOsForm.enabled}
              onChange={(e) => setEditOsForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              className="rounded border-border bg-background text-blue-600 focus:ring-blue-500"
            />
            <label className="ml-2 text-sm text-foreground">{t('common.enabled')}</label>
          </div>
        </div>
        <div className="mt-6 flex justify-end space-x-3">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => setShowEditOsModal(false)}
          />
          <PrimaryButton
            label={t('common.save')}
            variant="success"
            onClick={handleEditOs}
            loading={isEditingOs}
          />
        </div>
      </Modal>

      <DeletePreviewModal
        isOpen={showDeleteOsModal}
        onClose={() => setShowDeleteOsModal(false)}
        onConfirm={handleDeleteOs}
        title={t('dataSources.deleteDataSourceTitle')}
        itemName={deleteOsItem?.name || ''}
        itemTag={deleteOsItem?.tag}
        previewData={deletePreviewData}
        isLoadingPreview={isLoadingPreview}
        isDeleting={isDeletingOs}
      />

      <Modal
        title={t('dataSources.disableWarning')}
        isOpen={showDisableWarning}
        onClose={() => setShowDisableWarning(false)}
      >
        {disablePreviewData && (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
              <AlertTriangle className="h-6 w-6 text-amber-600 mb-2" />
              <p className="text-sm text-amber-800">{t('dataSources.disableImpactWarning')}</p>
            </div>
            {disablePreviewData.warnings?.length > 0 && (
              <ul className="list-disc list-inside text-sm text-muted-foreground">
                {disablePreviewData.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
            {disablePreviewData.affected_terminals > 0 && (
              <p className="text-sm text-foreground">
                {t('dataSources.affectedTerminals', { count: disablePreviewData.affected_terminals })}
              </p>
            )}
          </div>
        )}
        <div className="mt-6 flex justify-end space-x-3">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => setShowDisableWarning(false)}
          />
          <PrimaryButton
            label={t('common.confirm')}
            variant="danger"
            onClick={confirmDisable}
          />
        </div>
      </Modal>
    </div>
  );
});

export default OperationSourceTab;
