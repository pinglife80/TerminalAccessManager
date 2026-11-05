import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2, Edit2, Eye, Ban, CheckCircle, XCircle, Search } from 'lucide-react';
import { toast } from 'sonner';
import {
  useTerminalExclusions,
  useCreateTerminalExclusion,
  useUpdateTerminalExclusion,
  useDeleteTerminalExclusion,
  useToggleTerminalExclusion,
  usePreviewTerminalExclusion,
  TerminalExclusion,
  ExclusionImpact,
  ExclusionUnblockResult,
  IpPatternType,
  MacPatternType,
  TerminalExclusionCondition,
} from '@/api/terminalExclusions';
import { formatDate, getErrorMessage } from '@/lib/utils';
import { PrimaryButton, IconButton } from '@/components/Button';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';

const TerminalExclusions: React.FC = () => {
  const { t } = useTranslation();
  const { data, isLoading } = useTerminalExclusions();
  const createMutation = useCreateTerminalExclusion();
  const updateMutation = useUpdateTerminalExclusion();
  const deleteMutation = useDeleteTerminalExclusion();
  const toggleMutation = useToggleTerminalExclusion();
  const previewMutation = usePreviewTerminalExclusion();

  const [showFormModal, setShowFormModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showUnblockConfirm, setShowUnblockConfirm] = useState(false);
  const [enableRule, setEnableRule] = useState<TerminalExclusion | null>(null);
  const [enableUnblockBlocked, setEnableUnblockBlocked] = useState(false);
  const [selectedRule, setSelectedRule] = useState<TerminalExclusion | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  const [ipEnabled, setIpEnabled] = useState(false);
  const [ipType, setIpType] = useState<IpPatternType>('single_ip');
  const [ipValue, setIpValue] = useState('');
  const [macEnabled, setMacEnabled] = useState(false);
  const [macType, setMacType] = useState<MacPatternType>('mac_prefix');
  const [macValue, setMacValue] = useState('');
  const [comments, setComments] = useState('');
  const [unblockBlocked, setUnblockBlocked] = useState(false);
  const [formError, setFormError] = useState('');
  const [preview, setPreview] = useState<ExclusionImpact | null>(null);

  const rules = data?.items || [];

  useEffect(() => {
    setPreview(null);
  }, [ipEnabled, ipType, ipValue, macEnabled, macType, macValue]);

  const resetForm = () => {
    setIpEnabled(false);
    setIpType('single_ip');
    setIpValue('');
    setMacEnabled(false);
    setMacType('mac_prefix');
    setMacValue('');
    setComments('');
    setUnblockBlocked(false);
    setFormError('');
    setPreview(null);
  };

  const getIpTypeLabel = (type: IpPatternType) => {
    switch (type) {
      case 'single_ip': return t('terminalExclusions.ipTypeSingle');
      case 'cidr': return t('terminalExclusions.ipTypeCidr');
      case 'ip_range': return t('terminalExclusions.ipTypeRange');
      default: return type;
    }
  };

  const getMacTypeLabel = (type: MacPatternType) => {
    switch (type) {
      case 'mac': return t('terminalExclusions.macTypeFull');
      case 'mac_prefix': return t('terminalExclusions.macTypePrefix');
      default: return type;
    }
  };

  const getIpPlaceholder = (type: IpPatternType) => {
    switch (type) {
      case 'single_ip': return t('terminalExclusions.ipPlaceholderSingle');
      case 'cidr': return t('terminalExclusions.ipPlaceholderCidr');
      case 'ip_range': return t('terminalExclusions.ipPlaceholderRange');
      default: return '';
    }
  };

  const getMacPlaceholder = (type: MacPatternType) => {
    return type === 'mac'
      ? t('terminalExclusions.macPlaceholderFull')
      : t('terminalExclusions.macPlaceholderPrefix');
  };

  const getReasonLabel = (reason: string) => {
    switch (reason) {
      case 'blocked': return t('terminalExclusions.retainedBlocked');
      case 'active_blacklist': return t('terminalExclusions.retainedBlacklist');
      default: return t('terminalExclusions.willPurge');
    }
  };

  const buildConditionPayload = (): TerminalExclusionCondition | null => {
    if (!ipEnabled && !macEnabled) {
      setFormError(t('terminalExclusions.conditionRequired'));
      return null;
    }
    if (ipEnabled && !ipValue.trim()) {
      setFormError(t('terminalExclusions.ipValueRequired'));
      return null;
    }
    if (macEnabled && !macValue.trim()) {
      setFormError(t('terminalExclusions.macValueRequired'));
      return null;
    }
    return {
      ip_type: ipEnabled ? ipType : null,
      ip_value: ipEnabled ? ipValue.trim() : null,
      mac_type: macEnabled ? macType : null,
      mac_value: macEnabled ? macValue.trim() : null,
    };
  };

  const validateForm = (): boolean => {
    const condition = buildConditionPayload();
    if (!condition) return false;
    if (!comments.trim()) {
      setFormError(t('terminalExclusions.commentsRequired'));
      return false;
    }
    setFormError('');
    return true;
  };

  const handlePreview = async () => {
    const condition = buildConditionPayload();
    if (!condition) return;
    setFormError('');
    try {
      const impact = await previewMutation.mutateAsync(condition);
      setPreview(impact);
      if (impact.blocked === 0) {
        setUnblockBlocked(false);
      }
    } catch (err: unknown) {
      setFormError(getErrorMessage(err));
    }
  };

  const showImpactToast = (
    impact: ExclusionImpact,
    unblock?: ExclusionUnblockResult | null
  ) => {
    toast.success(
      t('terminalExclusions.impactToast', {
        purged: impact.purgeable,
        retained: impact.retained,
      })
    );
    if (!unblock || !unblock.requested) return;
    const summary = t('terminalExclusions.unblockResult', {
      unblocked: unblock.unblocked,
      failed: unblock.failed,
      skipped: unblock.skipped,
    });
    if (unblock.failed > 0 || unblock.skipped > 0) {
      toast.warning(summary, {
        description: unblock.errors.slice(0, 3).join('\n'),
      });
    } else {
      toast.success(summary);
    }
  };

  const submitCreate = async (withUnblock: boolean) => {
    const condition = buildConditionPayload();
    if (!condition) return;
    try {
      const result = await createMutation.mutateAsync({
        ...condition,
        comments: comments.trim(),
        unblock_blocked: withUnblock,
      });
      showImpactToast(result.impact, result.unblock);
      setShowFormModal(false);
      setShowUnblockConfirm(false);
      resetForm();
    } catch (err: unknown) {
      setFormError(getErrorMessage(err));
      setShowUnblockConfirm(false);
    }
  };

  const handleCreate = async () => {
    if (!validateForm()) return;
    if (unblockBlocked && (preview?.blocked || 0) > 0) {
      setShowUnblockConfirm(true);
      return;
    }
    await submitCreate(false);
  };

  const handleUpdate = async () => {
    if (!selectedRule || !validateForm()) return;
    const condition = buildConditionPayload();
    if (!condition) return;
    try {
      const result = await updateMutation.mutateAsync({
        id: selectedRule.id,
        data: { ...condition, comments: comments.trim() },
      });
      showImpactToast(result.impact, result.unblock);
      setShowFormModal(false);
      resetForm();
    } catch (err: unknown) {
      setFormError(getErrorMessage(err));
    }
  };

  const handleDelete = async () => {
    if (!selectedRule) return;
    try {
      await deleteMutation.mutateAsync(selectedRule.id);
      toast.success(t('common.deleteSuccess'));
      setShowDeleteModal(false);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err));
    }
  };

  const performToggle = async (rule: TerminalExclusion, withUnblock: boolean) => {
    try {
      const result = await toggleMutation.mutateAsync({
        id: rule.id,
        unblock_blocked: withUnblock,
      });
      if (rule.is_active) {
        toast.success(t('terminalExclusions.disabled'));
      } else {
        showImpactToast(result.impact, result.unblock);
      }
    } catch (err: unknown) {
      toast.error(getErrorMessage(err));
    }
  };

  const handleToggle = (rule: TerminalExclusion) => {
    if (rule.is_active) {
      void performToggle(rule, false);
      return;
    }
    setEnableRule(rule);
    setEnableUnblockBlocked(false);
  };

  const confirmEnable = async () => {
    if (!enableRule) return;
    const rule = enableRule;
    setEnableRule(null);
    await performToggle(rule, enableUnblockBlocked);
  };

  const openAddModal = () => {
    setIsEditing(false);
    setSelectedRule(null);
    resetForm();
    setShowFormModal(true);
  };

  const openEditModal = (rule: TerminalExclusion) => {
    setIsEditing(true);
    setSelectedRule(rule);
    setIpEnabled(!!rule.ip_value);
    setIpType(rule.ip_type || 'single_ip');
    setIpValue(rule.ip_value || '');
    setMacEnabled(!!rule.mac_value);
    setMacType(rule.mac_type || 'mac_prefix');
    setMacValue(rule.mac_value || '');
    setComments(rule.comments || '');
    setFormError('');
    setPreview(null);
    setShowFormModal(true);
  };

  const openDeleteModal = (rule: TerminalExclusion) => {
    setSelectedRule(rule);
    setShowDeleteModal(true);
  };

  const openDetailsModal = (rule: TerminalExclusion) => {
    setSelectedRule(rule);
    setShowDetailsModal(true);
  };

  if (isLoading) {
    return <PageSkeleton />;
  }

  const renderConditionFields = () => (
    <>
      <div className="rounded-md border border-border p-3 space-y-3">
        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
          <input
            type="checkbox"
            checked={ipEnabled}
            onChange={(e) => setIpEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          {t('terminalExclusions.ipSection')}
        </label>
        {ipEnabled && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <select
              value={ipType}
              onChange={(e) => { setIpType(e.target.value as IpPatternType); setIpValue(''); }}
              className="block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="single_ip">{t('terminalExclusions.ipTypeSingle')}</option>
              <option value="cidr">{t('terminalExclusions.ipTypeCidr')}</option>
              <option value="ip_range">{t('terminalExclusions.ipTypeRange')}</option>
            </select>
            <input
              type="text"
              value={ipValue}
              onChange={(e) => setIpValue(e.target.value)}
              placeholder={getIpPlaceholder(ipType)}
              className="block w-full rounded-md border border-border px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 sm:col-span-2"
            />
          </div>
        )}
      </div>

      <div className="rounded-md border border-border p-3 space-y-3">
        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
          <input
            type="checkbox"
            checked={macEnabled}
            onChange={(e) => setMacEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          {t('terminalExclusions.macSection')}
        </label>
        {macEnabled && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <select
              value={macType}
              onChange={(e) => { setMacType(e.target.value as MacPatternType); setMacValue(''); }}
              className="block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="mac">{t('terminalExclusions.macTypeFull')}</option>
              <option value="mac_prefix">{t('terminalExclusions.macTypePrefix')}</option>
            </select>
            <input
              type="text"
              value={macValue}
              onChange={(e) => setMacValue(e.target.value)}
              placeholder={getMacPlaceholder(macType)}
              className="block w-full rounded-md border border-border px-3 py-2 font-mono text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 sm:col-span-2"
            />
          </div>
        )}
      </div>

      {ipEnabled && macEnabled && (
        <p className="text-xs text-muted-foreground">{t('terminalExclusions.andHint')}</p>
      )}
    </>
  );

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('terminalExclusions.title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('terminalExclusions.description')}</p>
        </div>
        <PrimaryButton
          icon={Plus}
          label={t('terminalExclusions.create')}
          onClick={openAddModal}
        />
      </div>

      {rules.length === 0 ? (
        <EmptyState
          title={t('terminalExclusions.title')}
          description={t('terminalExclusions.emptyState')}
          icon={Ban}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg bg-card border border-border shadow-sm">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-card">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.ipSection')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.macSection')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.logicLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.commentsLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.activeLabel')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.createdBy')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.createdAt')}
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {t('terminalExclusions.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-card">
              {rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-muted/50">
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-foreground">
                    {rule.ip_value ? (
                      <div>
                        <span className="block text-xs text-muted-foreground">
                          {rule.ip_type ? getIpTypeLabel(rule.ip_type) : '-'}
                        </span>
                        <span className="font-mono">{rule.ip_value}</span>
                      </div>
                    ) : '-'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-foreground">
                    {rule.mac_value ? (
                      <div>
                        <span className="block text-xs text-muted-foreground">
                          {rule.mac_type ? getMacTypeLabel(rule.mac_type) : '-'}
                        </span>
                        <span className="font-mono">{rule.mac_value}</span>
                      </div>
                    ) : '-'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-muted-foreground">
                    {rule.ip_value && rule.mac_value
                      ? t('terminalExclusions.logicAnd')
                      : t('terminalExclusions.logicSingle')}
                  </td>
                  <td className="max-w-xs px-6 py-4 text-sm text-muted-foreground">
                    {rule.comments || '-'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <button
                      onClick={() => handleToggle(rule)}
                      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        rule.is_active
                          ? 'bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-500/15 dark:text-green-400 dark:hover:bg-green-500/25'
                          : 'bg-gray-100 text-muted-foreground hover:bg-gray-200 dark:bg-muted dark:hover:bg-muted/80'
                      }`}
                    >
                      {rule.is_active ? t('terminalExclusions.enabled') : t('terminalExclusions.disabled')}
                    </button>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-muted-foreground">
                    {rule.created_by}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-muted-foreground">
                    {formatDate(rule.created_at)}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-right text-sm">
                    <div className="inline-flex items-center gap-2">
                      <IconButton
                        icon={Eye}
                        onClick={() => openDetailsModal(rule)}
                        title={t('terminalExclusions.details')}
                      />
                      <IconButton
                        icon={Edit2}
                        onClick={() => openEditModal(rule)}
                        title={t('common.edit')}
                      />
                      <IconButton
                        icon={Trash2}
                        onClick={() => openDeleteModal(rule)}
                        title={t('common.delete')}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add / Edit Modal */}
      <Modal
        isOpen={showFormModal}
        onClose={() => { setShowFormModal(false); resetForm(); }}
        title={isEditing ? t('terminalExclusions.edit') : t('terminalExclusions.create')}
      >
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">{t('terminalExclusions.formHint')}</p>

          {renderConditionFields()}

          <div>
            <label className="block text-sm font-medium text-foreground">
              {t('terminalExclusions.commentsLabel')}
            </label>
            <textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder={t('terminalExclusions.commentsPlaceholder')}
              rows={2}
              className="mt-1 block w-full rounded-md border border-border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {formError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-600 dark:bg-red-500/10 dark:text-red-400">
              {formError}
            </div>
          )}

          {preview && (
            <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div>
                  <div className="text-xs text-muted-foreground">{t('terminalExclusions.matched')}</div>
                  <div className="font-semibold text-foreground">{preview.matched}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">{t('terminalExclusions.purgeable')}</div>
                  <div className="font-semibold text-red-600 dark:text-red-400">{preview.purgeable}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">{t('terminalExclusions.blocked')}</div>
                  <div className="font-semibold text-orange-600 dark:text-orange-400">{preview.blocked}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">{t('terminalExclusions.retained')}</div>
                  <div className="font-semibold text-yellow-600 dark:text-yellow-400">{preview.retained}</div>
                </div>
              </div>

              {!isEditing && preview.blocked > 0 && (
                <label className="mt-3 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-500/40 dark:bg-amber-500/10">
                  <input
                    type="checkbox"
                    checked={unblockBlocked}
                    onChange={(e) => setUnblockBlocked(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-border"
                  />
                  <span>
                    <span className="font-medium text-foreground">
                      {t('terminalExclusions.unblockBlocked', { count: preview.blocked })}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {t('terminalExclusions.unblockBlockedHint')}
                    </span>
                  </span>
                </label>
              )}
              {preview.samples.length > 0 && (
                <div className="mt-3 max-h-40 overflow-auto rounded border border-border bg-card">
                  <table className="min-w-full text-xs">
                    <thead className="bg-muted/60">
                      <tr>
                        <th className="px-2 py-1 text-left">{t('terminalExclusions.sampleIp')}</th>
                        <th className="px-2 py-1 text-left">{t('terminalExclusions.sampleMac')}</th>
                        <th className="px-2 py-1 text-left">{t('terminalExclusions.sampleStatus')}</th>
                        <th className="px-2 py-1 text-left">{t('terminalExclusions.sampleAction')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.samples.map((sample, index) => (
                        <tr key={`${sample.ip_address}-${sample.mac_address}-${index}`} className="border-t border-border">
                          <td className="px-2 py-1 font-mono">{sample.ip_address}</td>
                          <td className="px-2 py-1 font-mono">{sample.mac_address}</td>
                          <td className="px-2 py-1">{sample.status}</td>
                          <td className="px-2 py-1">{getReasonLabel(sample.reason)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between gap-3">
            <PrimaryButton
              icon={Search}
              label={previewMutation.isPending ? t('terminalExclusions.previewing') : t('terminalExclusions.preview')}
              variant="secondary"
              onClick={handlePreview}
              disabled={previewMutation.isPending}
            />
            <div className="flex gap-3">
              <PrimaryButton
                label={t('common.cancel')}
                variant="secondary"
                onClick={() => { setShowFormModal(false); resetForm(); }}
              />
              <PrimaryButton
                label={
                  (isEditing ? updateMutation.isPending : createMutation.isPending)
                    ? t('common.saving')
                    : isEditing ? t('common.save') : t('common.create')
                }
                onClick={isEditing ? handleUpdate : handleCreate}
                disabled={isEditing ? updateMutation.isPending : createMutation.isPending}
              />
            </div>
          </div>
        </div>
      </Modal>

      {/* Unblock confirmation for create */}
      <Modal
        isOpen={showUnblockConfirm}
        onClose={() => setShowUnblockConfirm(false)}
        title={t('terminalExclusions.unblockConfirmTitle')}
      >
        <div className="space-y-4">
          <p className="text-sm text-foreground">
            {t('terminalExclusions.unblockConfirmMessage', {
              count: preview?.blocked || 0,
            })}
          </p>
          <div className="flex justify-end gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => setShowUnblockConfirm(false)}
            />
            <PrimaryButton
              label={createMutation.isPending ? t('common.saving') : t('common.confirm')}
              variant="danger"
              onClick={() => submitCreate(true)}
              disabled={createMutation.isPending}
            />
          </div>
        </div>
      </Modal>

      {/* Enable rule confirmation */}
      <Modal
        isOpen={enableRule !== null}
        onClose={() => setEnableRule(null)}
        title={t('terminalExclusions.enableConfirmTitle')}
      >
        <div className="space-y-4">
          <p className="text-sm text-foreground">
            {t('terminalExclusions.enableConfirmMessage')}
          </p>
          <label className="flex items-start gap-2 rounded-md border border-border p-3 text-sm">
            <input
              type="checkbox"
              checked={enableUnblockBlocked}
              onChange={(e) => setEnableUnblockBlocked(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-border"
            />
            <span>
              <span className="font-medium text-foreground">
                {t('terminalExclusions.unblockBlockedGeneric')}
              </span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {t('terminalExclusions.unblockBlockedHint')}
              </span>
            </span>
          </label>
          <div className="flex justify-end gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => setEnableRule(null)}
            />
            <PrimaryButton
              label={toggleMutation.isPending ? t('common.saving') : t('common.confirm')}
              onClick={confirmEnable}
              disabled={toggleMutation.isPending}
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
          <p className="text-sm text-foreground">{t('terminalExclusions.confirmDelete')}</p>
          <div className="rounded-md bg-muted p-3 text-sm">
            <p>
              <span className="font-medium">{t('terminalExclusions.ipSection')}:</span>{' '}
              <span className="font-mono">{selectedRule?.ip_value || '-'}</span>
            </p>
            <p>
              <span className="font-medium">{t('terminalExclusions.macSection')}:</span>{' '}
              <span className="font-mono">{selectedRule?.mac_value || '-'}</span>
            </p>
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
        title={t('terminalExclusions.details')}
      >
        {selectedRule && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.activeLabel')}</dt>
                <dd className="mt-1 text-sm">
                  {selectedRule.is_active ? (
                    <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-500/15 dark:text-green-400">
                      <CheckCircle className="mr-1 h-3 w-3" /> {t('terminalExclusions.enabled')}
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted-foreground dark:bg-muted">
                      <XCircle className="mr-1 h-3 w-3" /> {t('terminalExclusions.disabled')}
                    </span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.logicLabel')}</dt>
                <dd className="mt-1 text-sm text-foreground">
                  {selectedRule.ip_value && selectedRule.mac_value
                    ? t('terminalExclusions.logicAnd')
                    : t('terminalExclusions.logicSingle')}
                </dd>
              </div>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.ipSection')}</dt>
              <dd className="mt-1 font-mono text-sm text-foreground">
                {selectedRule.ip_value
                  ? `${getIpTypeLabel(selectedRule.ip_type || 'single_ip')} · ${selectedRule.ip_value}`
                  : '-'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.macSection')}</dt>
              <dd className="mt-1 font-mono text-sm text-foreground">
                {selectedRule.mac_value
                  ? `${getMacTypeLabel(selectedRule.mac_type || 'mac_prefix')} · ${selectedRule.mac_value}`
                  : '-'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.commentsLabel')}</dt>
              <dd className="mt-1 text-sm text-foreground">{selectedRule.comments || '-'}</dd>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.createdBy')}</dt>
                <dd className="mt-1 text-sm text-foreground">{selectedRule.created_by}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-muted-foreground">{t('terminalExclusions.createdAt')}</dt>
                <dd className="mt-1 text-sm text-foreground">{formatDate(selectedRule.created_at)}</dd>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{t('terminalExclusions.disableHint')}</p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default TerminalExclusions;
