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
  Database,
} from 'lucide-react';
import { useDataSources, DataSourceItem } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, formatDate } from '@/lib/utils';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
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

interface DataSourcesTabProps {
  onAddClick: () => void;
}

const DataSourcesTab = forwardRef<{ openAddModal: () => void }, DataSourcesTabProps>(({ onAddClick }, ref) => {
  const { t } = useTranslation();
  const { data: dataSources, isLoading: dsLoading, refetch: dsRefetch } = useDataSources();

  // Expose openAddModal to parent via ref
  useImperativeHandle(ref, () => ({
    openAddModal: () => {
      resetDsForm();
      handleDsTypeChange('arp_ssh');
      setShowAddDsModal(true);
    },
  }));

  // Pagination
  const [dsPage, setDsPage] = useState(1);
  const [dsPageSize, setDsPageSize] = useState(10);

  // Add Data Source modal
  const [showAddDsModal, setShowAddDsModal] = useState(false);
  const [dsForm, setDsForm] = useState({
    name: '',
    type: 'arp_ssh',
    tag: '',
    enabled: true,
  });
  const [dsConfig, setDsConfig] = useState<Record<string, string>>({});
  const [isAddingDs, setIsAddingDs] = useState(false);

  // Delete Data Source modal
  const [showDeleteDsModal, setShowDeleteDsModal] = useState(false);
  const [deleteDsItem, setDeleteDsItem] = useState<DataSourceItem | null>(null);
  const [isDeletingDs, setIsDeletingDs] = useState(false);

  // Test connection
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);

  // Edit Data Source modal
  const [showEditDsModal, setShowEditDsModal] = useState(false);
  const [editDsForm, setEditDsForm] = useState({
    id: 0,
    name: '',
    type: 'arp_ssh',
    tag: '',
    enabled: true,
  });
  const [editDsConfig, setEditDsConfig] = useState<Record<string, string>>({});
  const [isEditingDs, setIsEditingDs] = useState(false);

  // Sync Data Source
  const [syncingId, setSyncingId] = useState<number | null>(null);

  // Derived data
  const dsList = dataSources || [];
  const dsTotalPages = Math.max(1, Math.ceil(dsList.length / dsPageSize));
  const paginatedDs = useMemo(() => {
    const start = (dsPage - 1) * dsPageSize;
    return dsList.slice(start, start + dsPageSize);
  }, [dsList, dsPage, dsPageSize]);

  // Handlers - Data Sources
  const handleDsTypeChange = (newType: string) => {
    setDsForm((prev) => ({ ...prev, type: newType }));
    const fields = CONFIG_FIELDS[newType] || [];
    setDsConfig(getDefaultConfig(fields));
  };

  const handleAddDs = async () => {
    if (!dsForm.name.trim()) {
      toast.error(t('dataSources.pleaseEnterName'));
      return;
    }
    if (!dsForm.tag.trim()) {
      toast.error(t('dataSources.pleaseEnterTag'));
      return;
    }

    setIsAddingDs(true);
    try {
      const fields = CONFIG_FIELDS[dsForm.type] || [];
      const config = buildConfigPayload(fields, dsConfig);

      await apiClient.post(API_ENDPOINTS.DATA_SOURCES, {
        name: dsForm.name,
        type: dsForm.type,
        tag: dsForm.tag,
        config,
        enabled: dsForm.enabled,
      });
      toast.success(t('dataSources.dataSourceCreated'));
      setShowAddDsModal(false);
      resetDsForm();
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToCreate')));
    } finally {
      setIsAddingDs(false);
    }
  };

  const resetDsForm = () => {
    setDsForm({ name: '', type: 'arp_ssh', tag: '', enabled: true });
    setDsConfig({});
  };

  const handleDeleteDs = async () => {
    if (!deleteDsItem) return;
    setIsDeletingDs(true);
    try {
      await apiClient.delete(`${API_ENDPOINTS.DATA_SOURCES}${deleteDsItem.id}`);
      toast.success(t('dataSources.dataSourceDeleted', { name: deleteDsItem.name }));
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToDelete')));
    } finally {
      setIsDeletingDs(false);
      setShowDeleteDsModal(false);
      setDeleteDsItem(null);
    }
  };

  const handleTestConnection = async (ds: DataSourceItem) => {
    setTestingId(ds.id);
    setTestResult(null);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.DATA_SOURCES}${ds.id}/test`);
      const data = response.data;
      setTestResult({ id: ds.id, success: data.success ?? true, message: data.message || data.detail || t('dataSources.connectionSuccessful') });
      if (data.success ?? true) {
        toast.success(t('dataSources.connectionSuccessful'));
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

  const openEditDsModal = (ds: DataSourceItem) => {
    setEditDsForm({
      id: ds.id,
      name: ds.name,
      type: ds.type,
      tag: ds.tag,
      enabled: ds.enabled,
    });
    const fields = CONFIG_FIELDS[ds.type] || [];
    const rawConfig = ds.config || {};
    setEditDsConfig(populateConfigFromItem(fields, rawConfig));
    setShowEditDsModal(true);
  };

  const handleEditDsTypeChange = (newType: string) => {
    setEditDsForm((prev) => ({ ...prev, type: newType }));
    const fields = CONFIG_FIELDS[newType] || [];
    const defaults: Record<string, string> = {};
    fields.forEach((f) => {
      defaults[f.key] = editDsConfig[f.key] ?? f.defaultValue ?? '';
    });
    setEditDsConfig(defaults);
  };

  const handleEditDs = async () => {
    if (!editDsForm.name.trim()) {
      toast.error(t('dataSources.pleaseEnterName'));
      return;
    }
    if (!editDsForm.tag.trim()) {
      toast.error(t('dataSources.pleaseEnterTag'));
      return;
    }

    setIsEditingDs(true);
    try {
      const fields = CONFIG_FIELDS[editDsForm.type] || [];
      const config = buildConfigPayload(fields, editDsConfig);

      await apiClient.put(`${API_ENDPOINTS.DATA_SOURCES}${editDsForm.id}`, {
        name: editDsForm.name,
        type: editDsForm.type,
        tag: editDsForm.tag,
        config,
        enabled: editDsForm.enabled,
      });
      toast.success(t('dataSources.dataSourceUpdated'));
      setShowEditDsModal(false);
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToUpdate')));
    } finally {
      setIsEditingDs(false);
    }
  };

  const handleSyncDs = async (ds: DataSourceItem) => {
    setSyncingId(ds.id);
    try {
      await apiClient.post(`${API_ENDPOINTS.DATA_SOURCES}${ds.id}/sync`);
      toast.success(t('dataSources.syncedSuccessfully'));
      dsRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('dataSources.failedToSync')));
    } finally {
      setSyncingId(null);
    }
  };

  // Render helpers
  const renderTypeBadge = (type: string) => {
    const badge = TYPE_BADGE[type];
    if (!badge) return <span className="text-sm text-muted-foreground">{type}</span>;
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>
        {badge.label}
      </span>
    );
  };

  const renderEnabledBadge = (enabled: boolean) => (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${enabled ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
      {enabled ? t('common.enabled') : t('common.disabled')}
    </span>
  );

  const renderLastSync = (ds: DataSourceItem) => {
    if (!ds.last_sync_at) {
      return <span className="text-sm text-muted-foreground">{t('common.never')}</span>;
    }
    const statusColor = ds.last_sync_status === 'success'
      ? 'text-green-600'
      : ds.last_sync_status === 'failed'
        ? 'text-red-600'
        : 'text-muted-foreground';
    return (
      <div>
        <span className={`text-sm font-medium ${statusColor}`}>
          {ds.last_sync_status === 'success' ? t('dataSources.lastSyncStatus.success') : ds.last_sync_status === 'failed' ? t('dataSources.lastSyncStatus.failed') : ds.last_sync_status}
        </span>
        <div className="flex items-center text-xs text-muted-foreground mt-0.5">
          <Clock className="h-3 w-3 mr-1" />
          {formatDate(ds.last_sync_at)}
        </div>
        {ds.last_sync_error && (
          <p className="text-xs text-red-500 mt-0.5 max-w-xs truncate" title={ds.last_sync_error}>
            {ds.last_sync_error}
          </p>
        )}
      </div>
    );
  };

  // Config form for add modal
  const renderConfigFields = () => {
    const fields = CONFIG_FIELDS[dsForm.type] || [];
    return fields.map((field) => (
      <div key={field.key}>
        <label className="block text-sm font-medium text-muted-foreground mb-1">{field.label}</label>
        {field.type === 'select' ? (
          <select
            value={dsConfig[field.key] ?? field.defaultValue ?? ''}
            onChange={(e) => setDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
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
            value={dsConfig[field.key] ?? field.defaultValue ?? ''}
            onChange={(e) => setDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
            className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
        )}
      </div>
    ));
  };

  return (
    <>
      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('dataSources.name')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('dataSources.type')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('dataSources.tag')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('dataSources.enabled')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('dataSources.lastSync')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {dsLoading ? (
                <tr>
                  <td colSpan={6}>
                    <LoadingState message={t('dataSources.loadingDataSources')} />
                  </td>
                </tr>
              ) : dsList.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={Database}
                      title={t('dataSources.noDataSources')}
                      description={t('dataSources.addDataSourceDescription')}
                      action={{ label: t('dataSources.addSource'), onClick: onAddClick }}
                    />
                  </td>
                </tr>
              ) : (
                paginatedDs.map((ds) => (
                  <tr key={ds.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 text-muted-foreground mr-2 flex-shrink-0" />
                        <span className="text-sm font-medium text-foreground">{ds.name}</span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {renderTypeBadge(ds.type)}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground">
                        {ds.tag}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {renderEnabledBadge(ds.enabled)}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {renderLastSync(ds)}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={testingId === ds.id ? RefreshCw : Plug}
                          variant="primary"
                          size="md"
                          title={t('dataSources.testConnection')}
                          onClick={() => handleTestConnection(ds)}
                          loading={testingId === ds.id}
                        />
                        <IconButton
                          icon={Pencil}
                          variant="primary"
                          size="md"
                          title={t('dataSources.editDataSource')}
                          onClick={() => openEditDsModal(ds)}
                        />
                        <IconButton
                          icon={RefreshCw}
                          variant="secondary"
                          size="md"
                          title={t('dataSources.syncDataSource')}
                          onClick={() => handleSyncDs(ds)}
                          loading={syncingId === ds.id}
                        />
                        <IconButton
                          icon={Trash2}
                          variant="danger"
                          size="md"
                          title={t('dataSources.deleteDataSource')}
                          onClick={() => { setDeleteDsItem(ds); setShowDeleteDsModal(true); }}
                        />
                      </ButtonGroup>
                      {/* Test result inline */}
                      {testResult && testResult.id === ds.id && (
                        <div className={`mt-1 text-xs flex items-center gap-1 ${testResult.success ? 'text-green-600' : 'text-red-600'}`}>
                          {testResult.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                          <span className="max-w-[200px] truncate" title={testResult.message}>{testResult.message}</span>
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
          currentPage={dsPage}
          totalPages={dsTotalPages}
          onPageChange={setDsPage}
          pageSize={dsPageSize}
          onPageSizeChange={(s) => { setDsPageSize(s); setDsPage(1); }}
          totalItems={dsList.length}
          variant="bottom"
        />
      </div>

      {/* Add Data Source Modal */}
      <Modal isOpen={showAddDsModal} onClose={() => { setShowAddDsModal(false); resetDsForm(); }} title={t('dataSources.addSource')} size="lg">
        <p className="text-sm text-muted-foreground mb-6">{t('dataSources.configureNewConnection')}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('dataSources.name')}</label>
            <input
              type="text"
              placeholder="My Data Source"
              value={dsForm.name}
              onChange={(e) => setDsForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('dataSources.type')}</label>
            <select
              value={dsForm.type}
              onChange={(e) => handleDsTypeChange(e.target.value)}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="arp_ssh">ARP SSH</option>
              <option value="arp_api">ARP API</option>
              <option value="sangfor">Sangfor</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('dataSources.tag')}</label>
            <input
              type="text"
              placeholder="unique-tag"
              value={dsForm.tag}
              onChange={(e) => setDsForm((prev) => ({ ...prev, tag: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          {renderConfigFields()}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="ds-enabled"
              checked={dsForm.enabled}
              onChange={(e) => setDsForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              className="h-4 w-4 text-blue-600 border-border rounded focus:ring-blue-500"
            />
            <label htmlFor="ds-enabled" className="text-sm font-medium text-muted-foreground">{t('dataSources.enabled')}</label>
          </div>
          <div className="flex gap-3 pt-4">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => { setShowAddDsModal(false); resetDsForm(); }}
              className="flex-1"
            />
            <PrimaryButton
              icon={Plus}
              label={t('common.create')}
              variant="success"
              onClick={handleAddDs}
              loading={isAddingDs}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Delete Data Source Modal */}
      <Modal isOpen={showDeleteDsModal} onClose={() => { setShowDeleteDsModal(false); setDeleteDsItem(null); }} title={t('dataSources.deleteDataSourceTitle')} size="sm">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
            <Trash2 className="h-6 w-6 text-red-600" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('common.cannotBeUndone')}</p>
          </div>
        </div>
        <p className="text-muted-foreground mb-6">
          {t('dataSources.areYouSureDeleteDs')} <span className="font-medium">{deleteDsItem?.name}</span> (tag: <span className="font-mono">{deleteDsItem?.tag}</span>)?
        </p>
        <div className="flex gap-3">
          <PrimaryButton
            label="Cancel"
            variant="secondary"
            onClick={() => { setShowDeleteDsModal(false); setDeleteDsItem(null); }}
            className="flex-1"
          />
          <PrimaryButton
            icon={Trash2}
            label={t('common.delete')}
            variant="danger"
            onClick={handleDeleteDs}
            loading={isDeletingDs}
            className="flex-1"
          />
        </div>
      </Modal>

      {/* Edit Data Source Modal */}
      <Modal isOpen={showEditDsModal} onClose={() => setShowEditDsModal(false)} title={t('dataSources.editDataSourceTitle')} size="lg">
        <p className="text-sm text-muted-foreground mb-6">{t('dataSources.updateConnectionSettings')}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('dataSources.name')}</label>
            <input
              type="text"
              placeholder="My Data Source"
              value={editDsForm.name}
              onChange={(e) => setEditDsForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('dataSources.type')}</label>
            <select
              value={editDsForm.type}
              onChange={(e) => handleEditDsTypeChange(e.target.value)}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="arp_ssh">ARP SSH</option>
              <option value="arp_api">ARP API</option>
              <option value="sangfor">Sangfor</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('dataSources.tag')}</label>
            <input
              type="text"
              placeholder="unique-tag"
              value={editDsForm.tag}
              onChange={(e) => setEditDsForm((prev) => ({ ...prev, tag: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          {(CONFIG_FIELDS[editDsForm.type] || []).map((field) => (
            <div key={field.key}>
              <label className="block text-sm font-medium text-muted-foreground mb-1">{field.label}</label>
              {field.type === 'select' ? (
                <select
                  value={editDsConfig[field.key] ?? field.defaultValue ?? ''}
                  onChange={(e) => setEditDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
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
                  value={editDsConfig[field.key] ?? field.defaultValue ?? ''}
                  onChange={(e) => setEditDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              )}
            </div>
          ))}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="edit-ds-enabled"
              checked={editDsForm.enabled}
              onChange={(e) => setEditDsForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              className="h-4 w-4 text-blue-600 border-border rounded focus:ring-blue-500"
            />
            <label htmlFor="edit-ds-enabled" className="text-sm font-medium text-muted-foreground">{t('dataSources.enabled')}</label>
          </div>
          <div className="flex gap-3 pt-4">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => setShowEditDsModal(false)}
              className="flex-1"
            />
            <PrimaryButton
              icon={Pencil}
              label={t('common.update')}
              variant="primary"
              onClick={handleEditDs}
              loading={isEditingDs}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>
    </>
  );
});

DataSourcesTab.displayName = 'DataSourcesTab';

export default DataSourcesTab;
