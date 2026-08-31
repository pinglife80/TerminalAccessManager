import { useState, useMemo, forwardRef, useImperativeHandle } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Trash2,
  Clock,
  Link2,
} from 'lucide-react';
import { useDataSourceBindings, useDataSources } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, formatDate } from '@/lib/utils';
import { PrimaryButton, IconButton } from '@/components/Button';
import { DeletePreviewModal, DeletePreviewData } from '@/components/DeletePreviewModal';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { Modal } from '@/components/Modal';
import { TYPE_BADGE } from './shared';

interface BindingsTabProps {
  onAddClick: () => void;
}

const BindingsTab = forwardRef<{ openAddModal: () => void }, BindingsTabProps>(({ onAddClick }, ref) => {
  const { t } = useTranslation();
  const { data: bindings, isLoading: bindLoading, refetch: bindRefetch } = useDataSourceBindings();
  const { data: dataSources } = useDataSources();

  // Expose openAddModal to parent via ref
  useImperativeHandle(ref, () => ({
    openAddModal: () => {
      setBindForm({ arp_source_tag: '', firewall_tag: '' });
      setShowAddBindModal(true);
    },
  }));

  // Pagination
  const [bindPage, setBindPage] = useState(1);
  const [bindPageSize, setBindPageSize] = useState(10);

  // Add Binding modal
  const [showAddBindModal, setShowAddBindModal] = useState(false);
  const [bindForm, setBindForm] = useState({ arp_source_tag: '', firewall_tag: '' });
  const [isAddingBind, setIsAddingBind] = useState(false);

  // Delete Binding modal
  const [showDeleteBindModal, setShowDeleteBindModal] = useState(false);
  const [deleteBindId, setDeleteBindId] = useState<number | null>(null);
  const [deleteBindInfo, setDeleteBindInfo] = useState<{ arpTag: string; fwTag: string } | null>(null);
  const [isDeletingBind, setIsDeletingBind] = useState(false);
  const [bindPreviewData, setBindPreviewData] = useState<DeletePreviewData | null>(null);
  const [isLoadingBindPreview, setIsLoadingBindPreview] = useState(false);

  // Derived data
  const bindList = bindings || [];
  const dsList = dataSources || [];

  const bindTotalPages = Math.max(1, Math.ceil(bindList.length / bindPageSize));
  const paginatedBind = useMemo(() => {
    const start = (bindPage - 1) * bindPageSize;
    return bindList.slice(start, start + bindPageSize);
  }, [bindList, bindPage, bindPageSize]);

  // ARP sources for binding dropdown (arp_ssh / arp_api)
  const arpSourceOptions = useMemo(
    () => dsList.filter((ds) => ds.type === 'arp_ssh' || ds.type === 'arp_api'),
    [dsList],
  );
  // Firewall sources for binding dropdown (sangfor)
  const firewallOptions = useMemo(
    () => dsList.filter((ds) => ds.type === 'sangfor'),
    [dsList],
  );

  // Handlers
  const handleAddBinding = async () => {
    if (!bindForm.arp_source_tag) {
      toast.error(t('bindings.pleaseSelectArpTag'));
      return;
    }
    if (!bindForm.firewall_tag) {
      toast.error(t('bindings.pleaseSelectFirewallTag'));
      return;
    }

    setIsAddingBind(true);
    try {
      await apiClient.post(API_ENDPOINTS.DATA_SOURCE_BINDINGS, {
        arp_source_tag: bindForm.arp_source_tag,
        firewall_tag: bindForm.firewall_tag,
      });
      toast.success(t('bindings.bindingCreated'));
      setShowAddBindModal(false);
      setBindForm({ arp_source_tag: '', firewall_tag: '' });
      bindRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('bindings.failedToCreateBinding')));
    } finally {
      setIsAddingBind(false);
    }
  };

  const openDeleteBindModal = async (bindingId: number, arpTag: string, fwTag: string) => {
    setDeleteBindId(bindingId);
    setDeleteBindInfo({ arpTag, fwTag });
    setShowDeleteBindModal(true);
    setIsLoadingBindPreview(true);
    setBindPreviewData(null);
    try {
      const response = await apiClient.post(`${API_ENDPOINTS.DATA_SOURCE_BINDING_DELETE_PREVIEW}${bindingId}/delete-preview`);
      setBindPreviewData(response.data);
    } catch (error: unknown) {
      setBindPreviewData(null);
      toast.error(getErrorMessage(error, t('deletePreview.failedToAnalyze')));
    } finally {
      setIsLoadingBindPreview(false);
    }
  };

  const handleDeleteBinding = async () => {
    if (!deleteBindId) return;
    setIsDeletingBind(true);
    try {
      await apiClient.delete(`${API_ENDPOINTS.DATA_SOURCE_BINDINGS}${deleteBindId}`);
      toast.success(t('bindings.bindingDeleted'));
      bindRefetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('bindings.failedToDeleteBinding')));
    } finally {
      setIsDeletingBind(false);
      setShowDeleteBindModal(false);
      setDeleteBindId(null);
      setDeleteBindInfo(null);
      setBindPreviewData(null);
    }
  };

  return (
    <>
      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-card">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('bindings.arpSourceTag')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('bindings.firewallTag')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('bindings.createdAt')}</th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {bindLoading ? (
                <tr>
                  <td colSpan={4}>
                    <LoadingState message={t('bindings.loadingBindings')} />
                  </td>
                </tr>
              ) : bindList.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <EmptyState
                      icon={Link2}
                      title={t('bindings.noBindings')}
                      description={t('bindings.createBindingDescription')}
                      action={{ label: t('bindings.addBindingTitle'), onClick: onAddClick }}
                    />
                  </td>
                </tr>
              ) : (
                paginatedBind.map((b) => (
                  <tr key={b.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {b.arp_source_tag}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                        {b.firewall_tag}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Clock className="h-4 w-4 mr-1.5 text-muted-foreground" />
                        {formatDate(b.created_at)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <IconButton
                        icon={Trash2}
                        variant="danger"
                        size="md"
                        title={t('bindings.deleteBindingTitle')}
                        onClick={() => openDeleteBindModal(b.id, b.arp_source_tag, b.firewall_tag)}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          currentPage={bindPage}
          totalPages={bindTotalPages}
          onPageChange={setBindPage}
          pageSize={bindPageSize}
          onPageSizeChange={(s) => { setBindPageSize(s); setBindPage(1); }}
          totalItems={bindList.length}
          variant="bottom"
        />
      </div>

      {/* Add Binding Modal */}
      <Modal isOpen={showAddBindModal} onClose={() => { setShowAddBindModal(false); setBindForm({ arp_source_tag: '', firewall_tag: '' }); }} title={t('bindings.addBindingTitle')} size="md">
        <p className="text-sm text-muted-foreground mb-6">{t('bindings.linkArpWithFirewall')}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('bindings.arpSourceTag')}</label>
            <select
              value={bindForm.arp_source_tag}
              onChange={(e) => setBindForm((prev) => ({ ...prev, arp_source_tag: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="">{t('bindings.selectArpSource')}</option>
              {arpSourceOptions.map((ds) => (
                <option key={ds.id} value={ds.tag} disabled={!ds.enabled}>
                  {ds.tag} ({ds.name} - {TYPE_BADGE[ds.type]?.label || ds.type}){!ds.enabled ? ` [${t('common.disabled')}]` : ''}
                </option>
              ))}
            </select>
            {arpSourceOptions.length > 0 && arpSourceOptions.every(ds => !ds.enabled) && (
              <p className="mt-1 text-xs text-amber-600">{t('bindings.allArpSourcesDisabled')}</p>
            )}
            {arpSourceOptions.length === 0 && (
              <p className="mt-1 text-xs text-amber-600">{t('bindings.noArpSourcesAvailable')}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('bindings.firewallTag')}</label>
            <select
              value={bindForm.firewall_tag}
              onChange={(e) => setBindForm((prev) => ({ ...prev, firewall_tag: e.target.value }))}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="">{t('bindings.selectFirewall')}</option>
              {firewallOptions.map((ds) => (
                <option key={ds.id} value={ds.tag} disabled={!ds.enabled}>
                  {ds.tag} ({ds.name}){!ds.enabled ? ` [${t('common.disabled')}]` : ''}
                </option>
              ))}
            </select>
            {firewallOptions.length > 0 && firewallOptions.every(ds => !ds.enabled) && (
              <p className="mt-1 text-xs text-amber-600">{t('bindings.allFirewallSourcesDisabled')}</p>
            )}
            {firewallOptions.length === 0 && (
              <p className="mt-1 text-xs text-amber-600">{t('bindings.noSangforSourcesAvailable')}</p>
            )}
          </div>
          <div className="flex gap-3 pt-4">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => { setShowAddBindModal(false); setBindForm({ arp_source_tag: '', firewall_tag: '' }); }}
              className="flex-1"
            />
            <PrimaryButton
              icon={Link2}
              label={t('bindings.createBinding')}
              variant="success"
              onClick={handleAddBinding}
              loading={isAddingBind}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Delete Binding Modal */}
      <DeletePreviewModal
        isOpen={showDeleteBindModal}
        onClose={() => { setShowDeleteBindModal(false); setDeleteBindId(null); setDeleteBindInfo(null); setBindPreviewData(null); }}
        onConfirm={handleDeleteBinding}
        title={t('bindings.deleteBindingTitle')}
        itemName={deleteBindInfo ? `${deleteBindInfo.arpTag} \u2192 ${deleteBindInfo.fwTag}` : ''}
        previewData={bindPreviewData}
        isLoadingPreview={isLoadingBindPreview}
        isDeleting={isDeletingBind}
      />
    </>
  );
});

BindingsTab.displayName = 'BindingsTab';

export default BindingsTab;
