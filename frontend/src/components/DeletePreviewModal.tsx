import { useTranslation } from 'react-i18next';
import { Trash2, AlertTriangle, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { PrimaryButton } from '@/components/Button';
import { Modal } from '@/components/Modal';

export interface DeletePreviewData {
  can_delete: boolean;
  warnings: string[];
  actions: string[];
  affected: {
    terminals: number;
    blocked_terminals: number;
    blacklist_entries: number;
    bindings: number;
    compliant_terminals: number;
  };
  reason?: string | null;
}

interface DeletePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  title: string;
  itemName: string;
  itemTag?: string;
  previewData: DeletePreviewData | null;
  isLoadingPreview: boolean;
  isDeleting: boolean;
}

export function DeletePreviewModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  itemName,
  itemTag,
  previewData,
  isLoadingPreview,
  isDeleting,
}: DeletePreviewModalProps) {
  const { t } = useTranslation();

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="md">
      {isLoadingPreview ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-primary-600 mr-3" />
          <span className="text-muted-foreground">{t('deletePreview.analyzingImpact')}</span>
        </div>
      ) : previewData ? (
        <>
          {/* Cannot delete warning */}
          {!previewData.can_delete && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
              <XCircle className="h-5 w-5 text-red-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-red-800">{t('deletePreview.cannotDelete')}</p>
                {previewData.reason && (
                  <p className="text-sm text-red-700 mt-1">{previewData.reason}</p>
                )}
              </div>
            </div>
          )}

          {/* Item info */}
          <div className="mb-4 flex items-center gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${previewData.can_delete ? 'bg-red-100' : 'bg-gray-100'}`}>
              <Trash2 className={`h-5 w-5 ${previewData.can_delete ? 'text-red-600' : 'text-gray-400'}`} />
            </div>
            <div>
              <p className="font-medium">{itemName}</p>
              {itemTag && <p className="text-sm text-muted-foreground font-mono">{itemTag}</p>}
            </div>
          </div>

          {/* Warnings */}
          {previewData.warnings.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-amber-800 mb-2 flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4" />
                {t('deletePreview.impactScope')}
              </h4>
              <ul className="space-y-1">
                {previewData.warnings.map((warning, index) => (
                  <li key={index} className="text-sm text-amber-700 pl-6 relative before:content-['\2022'] before:absolute before:left-2 before:text-amber-500">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Actions to be performed */}
          {previewData.actions.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                <CheckCircle className="h-4 w-4" />
                {t('deletePreview.actionsToPerform')}
              </h4>
              <div className="bg-muted/50 rounded-lg p-3 space-y-1.5">
                {previewData.actions.map((action, index) => (
                  <div key={index} className="flex items-start gap-2 text-sm">
                    <span className="text-muted-foreground shrink-0">{index + 1}.</span>
                    <span>{action}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Affected counts */}
          {(previewData.affected.terminals > 0 || previewData.affected.blocked_terminals > 0 ||
            previewData.affected.blacklist_entries > 0 || previewData.affected.bindings > 0 ||
            previewData.affected.compliant_terminals > 0) && (
            <div className="mb-4 grid grid-cols-2 sm:grid-cols-3 gap-2">
              {previewData.affected.terminals > 0 && (
                <div className="bg-blue-50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-blue-700">{previewData.affected.terminals}</p>
                  <p className="text-xs text-blue-600">{t('deletePreview.terminals')}</p>
                </div>
              )}
              {previewData.affected.blocked_terminals > 0 && (
                <div className="bg-red-50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-red-700">{previewData.affected.blocked_terminals}</p>
                  <p className="text-xs text-red-600">{t('deletePreview.blockedTerminals')}</p>
                </div>
              )}
              {previewData.affected.blacklist_entries > 0 && (
                <div className="bg-orange-50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-orange-700">{previewData.affected.blacklist_entries}</p>
                  <p className="text-xs text-orange-600">{t('deletePreview.blacklistEntries')}</p>
                </div>
              )}
              {previewData.affected.bindings > 0 && (
                <div className="bg-purple-50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-purple-700">{previewData.affected.bindings}</p>
                  <p className="text-xs text-purple-600">{t('deletePreview.bindings')}</p>
                </div>
              )}
              {previewData.affected.compliant_terminals > 0 && (
                <div className="bg-green-50 rounded-lg p-2 text-center">
                  <p className="text-lg font-semibold text-green-700">{previewData.affected.compliant_terminals}</p>
                  <p className="text-xs text-green-600">{t('deletePreview.compliantTerminals')}</p>
                </div>
              )}
            </div>
          )}

          {/* Cannot be undone notice */}
          {previewData.can_delete && (
            <p className="text-xs text-muted-foreground mb-4">{t('deletePreview.cannotBeUndone')}</p>
          )}

          {/* Action buttons */}
          <div className="flex gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={onClose}
              className="flex-1"
            />
            {previewData.can_delete && (
              <PrimaryButton
                icon={Trash2}
                label={t('common.delete')}
                variant="danger"
                onClick={onConfirm}
                loading={isDeleting}
                className="flex-1"
              />
            )}
          </div>
        </>
      ) : (
        <div className="py-4 text-center text-muted-foreground">
          {t('deletePreview.failedToAnalyze')}
        </div>
      )}
    </Modal>
  );
}
