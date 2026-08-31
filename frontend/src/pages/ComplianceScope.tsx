import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2, Edit2, Filter, CheckCircle, XCircle, Eye } from 'lucide-react';
import { toast } from 'sonner';
import { useComplianceScopes, useCreateComplianceScope, useUpdateComplianceScope, useDeleteComplianceScope, useToggleComplianceScope, ComplianceScope as ComplianceScopeType, ScopeType } from '@/api/complianceScope';
import { formatDate, getErrorMessage } from '@/lib/utils';
import { PrimaryButton, IconButton } from '@/components/Button';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';

const ComplianceScope: React.FC = () => {
  const { t } = useTranslation();
  const { data, isLoading } = useComplianceScopes();
  const createMutation = useCreateComplianceScope();
  const updateMutation = useUpdateComplianceScope();
  const deleteMutation = useDeleteComplianceScope();
  const toggleMutation = useToggleComplianceScope();

  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedScope, setSelectedScope] = useState<ComplianceScopeType | null>(null);

  const [scopeType, setScopeType] = useState<ScopeType>('ip_cidr');
  const [scopeValue, setScopeValue] = useState('');
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState('');

  const scopes = data?.items || [];

  const resetForm = () => {
    setScopeType('ip_cidr');
    setScopeValue('');
    setDescription('');
    setFormError('');
  };

  const getScopeTypeLabel = (type: string) => {
    switch (type) {
      case 'ip_cidr': return t('complianceScope.typeIpCidr');
      case 'ip_range': return t('complianceScope.typeIpRange');
      case 'mac_prefix_arp': return t('complianceScope.typeMacPrefixArp');
      case 'mac_prefix_ipguard': return t('complianceScope.typeMacPrefixIpguard');
      default: return type;
    }
  };

  const getScopeTypeDesc = (type: string) => {
    switch (type) {
      case 'ip_cidr': return t('complianceScope.ipCidrDesc');
      case 'ip_range': return t('complianceScope.ipRangeDesc');
      case 'mac_prefix_arp': return t('complianceScope.macPrefixArpDesc');
      case 'mac_prefix_ipguard': return t('complianceScope.macPrefixIpguardDesc');
      default: return '';
    }
  };

  const getScopePlaceholder = (type: string) => {
    switch (type) {
      case 'ip_cidr': return t('complianceScope.valuePlaceholderCidr');
      case 'ip_range': return t('complianceScope.valuePlaceholderRange');
      case 'mac_prefix_arp':
      case 'mac_prefix_ipguard':
        return t('complianceScope.valuePlaceholderMac');
      default: return '';
    }
  };

  const validateForm = (): string => {
    if (!scopeValue.trim()) {
      return t('complianceScope.valueLabel') + '不能为空';
    }
    return '';
  };

  const handleCreate = async () => {
    const error = validateForm();
    if (error) {
      setFormError(error);
      return;
    }
    try {
      await createMutation.mutateAsync({
        scope_type: scopeType,
        scope_value: scopeValue.trim(),
        description: description.trim() || undefined,
      });
      toast.success(t('common.createSuccess'));
      setShowAddModal(false);
      resetForm();
    } catch (err: unknown) {
      const msg = getErrorMessage(err);
      setFormError(msg);
    }
  };

  const handleUpdate = async () => {
    if (!selectedScope) return;
    const error = validateForm();
    if (error) {
      setFormError(error);
      return;
    }
    try {
      await updateMutation.mutateAsync({
        id: selectedScope.id,
        data: {
          scope_type: scopeType,
          scope_value: scopeValue.trim(),
          description: description.trim() || undefined,
        },
      });
      toast.success(t('common.updateSuccess'));
      setShowEditModal(false);
      resetForm();
    } catch (err: unknown) {
      const msg = getErrorMessage(err);
      setFormError(msg);
    }
  };

  const handleDelete = async () => {
    if (!selectedScope) return;
    try {
      await deleteMutation.mutateAsync(selectedScope.id);
      toast.success(t('common.deleteSuccess'));
      setShowDeleteModal(false);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err));
    }
  };

  const handleToggle = async (scope: ComplianceScopeType) => {
    try {
      await toggleMutation.mutateAsync(scope.id);
      toast.success(scope.is_active ? t('complianceScope.disabled') : t('complianceScope.enabled'));
    } catch (err: unknown) {
      toast.error(getErrorMessage(err));
    }
  };

  const openAddModal = () => {
    resetForm();
    setShowAddModal(true);
  };

  const openEditModal = (scope: ComplianceScopeType) => {
    setSelectedScope(scope);
    setScopeType(scope.scope_type);
    setScopeValue(scope.scope_value);
    setDescription(scope.description || '');
    setFormError('');
    setShowEditModal(true);
  };

  const openDeleteModal = (scope: ComplianceScopeType) => {
    setSelectedScope(scope);
    setShowDeleteModal(true);
  };

  const openDetailsModal = (scope: ComplianceScopeType) => {
    setSelectedScope(scope);
    setShowDetailsModal(true);
  };

  if (isLoading) {
    return <PageSkeleton />;
  }

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('complianceScope.title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('complianceScope.description')}</p>
        </div>
        <PrimaryButton
          icon={Plus}
          label={t('complianceScope.create')}
          onClick={openAddModal}
        />
      </div>

      {scopes.length === 0 ? (
        <EmptyState
          title={t('complianceScope.title')}
          description={t('complianceScope.emptyState')}
          icon={Filter}
        />
      ) : (
        <div className="overflow-hidden rounded-lg bg-card border border-border shadow-sm">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-card">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('complianceScope.typeLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('complianceScope.valueLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('complianceScope.descriptionLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('complianceScope.activeLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('complianceScope.createdBy')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('complianceScope.createdAt')}
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-card">
              {scopes.map((scope) => (
                <tr key={scope.id} className="hover:bg-muted/50">
                  <td className="whitespace-nowrap px-6 py-4">
                    <span className="inline-flex rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-500/15 dark:text-blue-400">
                      {getScopeTypeLabel(scope.scope_type)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 font-mono text-sm text-foreground">
                    {scope.scope_value}
                  </td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    {scope.description || '-'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <button
                      onClick={() => handleToggle(scope)}
                      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        scope.is_active
                          ? 'bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-500/15 dark:text-green-400 dark:hover:bg-green-500/25'
                          : 'bg-gray-100 text-muted-foreground hover:bg-gray-200 dark:bg-muted dark:hover:bg-muted/80'
                      }`}
                    >
                      {scope.is_active ? t('complianceScope.enabled') : t('complianceScope.disabled')}
                    </button>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-muted-foreground">
                    {scope.created_by}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-muted-foreground">
                    {formatDate(scope.created_at)}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-right text-sm">
                    <div className="inline-flex items-center gap-2">
                      <IconButton
                        icon={Eye}
                        onClick={() => openDetailsModal(scope)}
                        title="Details"
                      />
                      <IconButton
                        icon={Edit2}
                        onClick={() => openEditModal(scope)}
                        title="Edit"
                      />
                      <IconButton
                        icon={Trash2}
                        onClick={() => openDeleteModal(scope)}
                        title="Delete"
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => { setShowAddModal(false); resetForm(); }}
        title={t('complianceScope.create')}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('complianceScope.typeLabel')}
            </label>
            <select
              value={scopeType}
              onChange={(e) => { setScopeType(e.target.value as ScopeType); setScopeValue(''); }}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="ip_cidr">{t('complianceScope.typeIpCidr')}</option>
              <option value="ip_range">{t('complianceScope.typeIpRange')}</option>
              <option value="mac_prefix_arp">{t('complianceScope.typeMacPrefixArp')}</option>
              <option value="mac_prefix_ipguard">{t('complianceScope.typeMacPrefixIpguard')}</option>
            </select>
            <p className="mt-1 text-xs text-muted-foreground">{getScopeTypeDesc(scopeType)}</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('complianceScope.valueLabel')}
            </label>
            <input
              type="text"
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              placeholder={getScopePlaceholder(scopeType)}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('complianceScope.descriptionLabel')}
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('complianceScope.descriptionPlaceholder')}
              rows={3}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {formError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-500/10 dark:text-red-400">
              {formError}
            </div>
          )}

          <div className="flex justify-end gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => { setShowAddModal(false); resetForm(); }}
            />
            <PrimaryButton
              label={createMutation.isPending ? t('common.saving') : t('common.create')}
              onClick={handleCreate}
              disabled={createMutation.isPending}
            />
          </div>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={() => { setShowEditModal(false); resetForm(); }}
        title={t('complianceScope.edit')}
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('complianceScope.typeLabel')}
            </label>
            <select
              value={scopeType}
              onChange={(e) => { setScopeType(e.target.value as ScopeType); setScopeValue(''); }}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="ip_cidr">{t('complianceScope.typeIpCidr')}</option>
              <option value="ip_range">{t('complianceScope.typeIpRange')}</option>
              <option value="mac_prefix_arp">{t('complianceScope.typeMacPrefixArp')}</option>
              <option value="mac_prefix_ipguard">{t('complianceScope.typeMacPrefixIpguard')}</option>
            </select>
            <p className="mt-1 text-xs text-muted-foreground">{getScopeTypeDesc(scopeType)}</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('complianceScope.valueLabel')}
            </label>
            <input
              type="text"
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              placeholder={getScopePlaceholder(scopeType)}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('complianceScope.descriptionLabel')}
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('complianceScope.descriptionPlaceholder')}
              rows={3}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {formError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-500/10 dark:text-red-400">
              {formError}
            </div>
          )}

          <div className="flex justify-end gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => { setShowEditModal(false); resetForm(); }}
            />
            <PrimaryButton
              label={updateMutation.isPending ? t('common.saving') : t('common.save')}
              onClick={handleUpdate}
              disabled={updateMutation.isPending}
            />
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title={t('common.confirmDelete')}
      >
        <div className="space-y-4">
          <p className="text-sm text-foreground">
            {t('complianceScope.confirmDelete')}
          </p>
          <div className="rounded-md bg-muted p-3 text-sm">
            <p><span className="font-medium">{t('complianceScope.typeLabel')}:</span> {selectedScope && getScopeTypeLabel(selectedScope.scope_type)}</p>
            <p><span className="font-medium">{t('complianceScope.valueLabel')}:</span> <span className="font-mono">{selectedScope?.scope_value}</span></p>
          </div>
          <div className="flex justify-end gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => setShowDeleteModal(false)}
            />
            <PrimaryButton
              label={deleteMutation.isPending ? '...' : t('common.delete')}
              variant="danger"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            />
          </div>
        </div>
      </Modal>

      {/* Details Modal */}
      <Modal
        isOpen={showDetailsModal}
        onClose={() => setShowDetailsModal(false)}
        title={t('complianceScope.edit')}
      >
        {selectedScope && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('complianceScope.typeLabel')}</dt>
                <dd className="mt-1 text-sm text-foreground">{getScopeTypeLabel(selectedScope.scope_type)}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('complianceScope.activeLabel')}</dt>
                <dd className="mt-1 text-sm">
                  {selectedScope.is_active ? (
                    <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-500/15 dark:text-green-400">
                      <CheckCircle className="mr-1 h-3 w-3" /> {t('complianceScope.enabled')}
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted-foreground dark:bg-muted">
                      <XCircle className="mr-1 h-3 w-3" /> {t('complianceScope.disabled')}
                    </span>
                  )}
                </dd>
              </div>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">{t('complianceScope.valueLabel')}</dt>
              <dd className="mt-1 font-mono text-sm text-foreground">{selectedScope.scope_value}</dd>
              <p className="mt-1 text-xs text-muted-foreground">{getScopeTypeDesc(selectedScope.scope_type)}</p>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">{t('complianceScope.descriptionLabel')}</dt>
              <dd className="mt-1 text-sm text-foreground">{selectedScope.description || '-'}</dd>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('complianceScope.createdBy')}</dt>
                <dd className="mt-1 text-sm text-foreground">{selectedScope.created_by}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('complianceScope.createdAt')}</dt>
                <dd className="mt-1 text-sm text-foreground">{formatDate(selectedScope.created_at)}</dd>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ComplianceScope;
