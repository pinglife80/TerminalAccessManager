import React, { useState } from 'react';
import { useWhitelist, WhitelistEntry } from '@/hooks/useTerminalData';
import { useTranslation } from 'react-i18next';
import { Search, Plus, Trash2, User, Server, Globe, RefreshCw, Download, Clock, ChevronDown, Eye, Upload, FileText, X, CheckCircle, AlertCircle } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { normalizeMacAddress, isValidMacAddress, isValidCidrOrRange, formatDate, useDebounce, getErrorMessage } from '@/lib/utils';
import { PrimaryButton, IconButton } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';
import { DateRangeFilter } from '@/components/DateRangeFilter';

interface ImportErrorRow {
  row: number;
  reason: string;
  data: Record<string, unknown>;
}

interface ImportResult {
  success_count: number;
  skipped_count: number;
  failed_count: number;
  errors: ImportErrorRow[];
  mode: string;
  total_processed: number;
}

const Whitelist: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [deleteIdentifier, setDeleteIdentifier] = useState<string>('');
  const [deleteIpPattern, setDeleteIpPattern] = useState('');
  const [selectedEntry, setSelectedEntry] = useState<WhitelistEntry | null>(null);
  const [macAddress, setMacAddress] = useState('');
  const [ipAddress, setIpAddress] = useState('');
  const [comments, setComments] = useState('');
  const [commentsError, setCommentsError] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [isAdding, setIsAdding] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<'skip' | 'overwrite'>('skip');
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importing, setImporting] = useState(false);
  const [isValidating, setIsValidating] = useState(false);

  // Debounce search term
  const debouncedSearch = useDebounce(searchTerm, 500);

  const { data: whitelistData, isLoading, refetch } = useWhitelist({
    search: debouncedSearch || undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: (currentPage - 1) * pageSize,
    limit: pageSize,
  });

  // Extract items and total from paginated response
  const filteredWhitelist = whitelistData?.items ?? [];
  const totalFromServer = whitelistData?.total ?? 0;

  const totalPages = Math.ceil(totalFromServer / pageSize);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleAddWhitelist = async () => {
    if (!macAddress.trim() && !ipAddress.trim()) {
      toast.error(t('whitelist.pleaseEnterMacOrIp'));
      return;
    }

    if (macAddress && !isValidMacAddress(macAddress)) {
      toast.error(t('whitelist.invalidMacFormat'));
      return;
    }

    if (ipAddress && !isValidCidrOrRange(ipAddress)) {
      toast.error(t('whitelist.invalidIpFormat'));
      return;
    }

    // Comments is required
    if (!comments.trim()) {
      setCommentsError(t('whitelist.commentsRequired'));
      return;
    }
    setCommentsError('');

    setIsAdding(true);
    try {
      const payload: Record<string, string> = {};

      if (macAddress) {
        payload['mac_address'] = normalizeMacAddress(macAddress);
      }
      if (ipAddress) {
        payload['ip_address'] = ipAddress;
      }
      payload['comments'] = comments;

      const response = await apiClient.post(API_ENDPOINTS.WHITELIST, payload);

      const result = response.data;
      if (result.success) {
        let successMsg = '';
        if (result.added > 0) {
          successMsg = t('whitelist.addedSuccessfully');
        }
        if (result.skipped > 0) {
          successMsg += ` (${t('whitelist.skipped')})`;
        }
        toast.success(successMsg);

        if (result.errors && result.errors.length > 0) {
          result.errors.forEach((error: string) => {
            toast.warning(error);
          });
        }
      }

      setMacAddress('');
      setIpAddress('');
      setComments('');
      setCommentsError('');
      setShowAddModal(false);
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('whitelist.failedToAdd')));
    } finally {
      setIsAdding(false);
    }
  };

  const handleReset = () => {
    refetch();
    setSearchTerm('');
    setStartDate('');
    setEndDate('');
    setCurrentPage(1);
  };

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (debouncedSearch) params['search'] = debouncedSearch;
      if (startDate) params['start_date'] = startDate;
      if (endDate) params['end_date'] = endDate;

      const response = await apiClient.get(API_ENDPOINTS.WHITELIST_EXPORT, {
        params,
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'whitelist.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('whitelist.failedToExport')));
    }
  };

  const handleImportFileSelect = (file: File | null) => {
    if (!file) {
      setImportFile(null);
      return;
    }
    const ext = file.name.toLowerCase().split('.').pop() || '';
    if (!['csv', 'zip', 'json'].includes(ext)) {
      toast.error(t('whitelist.invalidFileType'));
      setImportFile(null);
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error(t('whitelist.fileTooLarge'));
      setImportFile(null);
      return;
    }
    setImportFile(file);
    setImportResult(null);
  };

  const handleImport = async (validateOnly = false) => {
    if (!importFile) {
      toast.error(t('whitelist.noFileSelected'));
      return;
    }

    const formData = new FormData();
    formData.append('file', importFile);
    formData.append('mode', importMode);
    formData.append('validate_only', String(validateOnly));

    if (validateOnly) {
      setIsValidating(true);
    } else {
      setImporting(true);
    }

    try {
      const response = await apiClient.post(API_ENDPOINTS.WHITELIST_IMPORT, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const result = response.data as ImportResult;
      setImportResult(result);

      if (validateOnly) {
        if (result.failed_count === 0) {
          toast.success(t('whitelist.csvValidationPassed', { count: result.success_count }));
        } else {
          toast.error(t('whitelist.csvValidationFailed', { count: result.failed_count }));
        }
      } else {
        if (result.success_count > 0) {
          toast.success(t('whitelist.importSuccess'));
          refetch();
        } else {
          toast.error(t('whitelist.importFailed'));
        }
      }
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, validateOnly ? t('whitelist.validationRequestFailed') : t('whitelist.importFailed')));
    } finally {
      setIsValidating(false);
      setImporting(false);
    }
  };

  const resetImportModal = () => {
    setShowImportModal(false);
    setImportFile(null);
    setImportResult(null);
    setImportMode('skip');
    setImporting(false);
    setIsValidating(false);
  };

  const downloadTemplate = () => {
    const header = 'ID,MAC Address,IP Pattern,Pattern Type,Comments,Added By,Created At\n';
    const sample = '1,AA:BB:CC:DD:EE:FF,,mac_only,Office Printer,admin,2025-01-01T00:00:00\n';
    const sample2 = '2,,192.168.1.0/24,cidr,Office Subnet,admin,2025-01-01T00:00:00\n';
    const blob = new Blob(['\uFEFF' + header + sample + sample2], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'whitelist_template.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleRemoveWhitelist = (identifier: string | null, ipPattern?: string | null) => {
    setDeleteIdentifier(identifier || '');
    setDeleteIpPattern(ipPattern || '');
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    const identifier = deleteIdentifier || deleteIpPattern;

    setIsDeleting(true);
    try {
      await apiClient.delete(`${API_ENDPOINTS.WHITELIST}?identifier=${encodeURIComponent(identifier)}`);
      toast.success(t('whitelist.removedSuccessfully'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('whitelist.failedToRemove')));
    } finally {
      setIsDeleting(false);
      setShowDeleteModal(false);
      setDeleteIdentifier('');
      setDeleteIpPattern('');
    }
  };

  const handleViewDetails = (entry: WhitelistEntry) => {
    setSelectedEntry(entry);
    setShowDetailsModal(true);
  };

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {isLoading && !whitelistData ? (
        <PageSkeleton />
      ) : (
      <>
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('whitelist.whitelistTerminals')}</h1>
          <p className="text-muted-foreground mt-1">{t('whitelist.manageTrusted')}</p>
        </div>
        <div className="flex gap-2">
          <PrimaryButton
            icon={Download}
            label={t('common.export')}
            variant="success"
            onClick={handleExport}
          />
          <PrimaryButton
            icon={Upload}
            label={t('whitelist.import')}
            variant="secondary"
            onClick={() => { setShowImportModal(true); setImportResult(null); }}
          />
          <PrimaryButton
            icon={Plus}
            label={t('whitelist.addTerminal')}
            variant="success"
            onClick={() => setShowAddModal(true)}
          />
        </div>
      </div>

      {/* Search and Filter */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden mb-6">
        {/* Section Header - Clickable */}
        <button
          onClick={() => setFilterCollapsed(!filterCollapsed)}
          className={`w-full px-5 py-4 flex items-center justify-between hover:bg-background/50 transition-colors ${!filterCollapsed ? 'border-b border-border' : ''}`}
        >
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-base font-semibold text-foreground">{t('terminal.searchAndFilter')}</h2>
          </div>
          <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${filterCollapsed ? '' : 'rotate-180'}`} />
        </button>
        {!filterCollapsed && (
        <>
        <div className="p-4 sm:p-5">
          <div className="flex flex-col xl:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <input
                type="text"
                placeholder={t('whitelist.searchByMacIpDescription')}
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full pl-10 pr-4 py-2.5 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all"
              />
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Date Range */}
              <DateRangeFilter
                startDate={startDate}
                endDate={endDate}
                onChange={({ startDate, endDate }) => {
                  setStartDate(startDate);
                  setEndDate(endDate);
                  setCurrentPage(1);
                }}
              />

              {/* Reset Button */}
              <PrimaryButton
                icon={RefreshCw}
                label={t('common.reset')}
                variant="secondary"
                size="sm"
                onClick={handleReset}
              />
            </div>
          </div>
        </div>

        {/* Top Pagination - Info Row */}
        {totalPages > 1 && (
          <div className="px-4 sm:px-5 py-3 bg-background border-t border-border">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={handlePageChange}
              pageSize={pageSize}
              onPageSizeChange={handlePageSizeChange}
              totalItems={totalFromServer}
              variant="top"
              showPageSizeSelector={false}
            />
          </div>
        )}
        </>
        )}
      </div>

      {/* Stats */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden p-5 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-shrink-0 w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
            <Globe className="h-6 w-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">{t('whitelist.totalEntries')}</p>
            <p className="text-2xl sm:text-3xl font-bold text-foreground">{totalFromServer}</p>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-card">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('whitelist.macAddress')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('whitelist.ipAddress')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('whitelist.type')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('whitelist.addedBy')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('whitelist.addedDate')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('terminal.comments')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {filteredWhitelist?.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={Server}
                      title={t('whitelist.noWhitelistEntries')}
                      description={t('whitelist.addTrustedDescription')}
                      action={{
                        label: t('whitelist.addTerminal'),
                        onClick: () => setShowAddModal(true)
                      }}
                    />
                  </td>
                </tr>
              ) : (
                (filteredWhitelist || []).map((item) => (
                  <tr key={item.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm font-medium text-foreground">
                      {item.mac_address || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-muted-foreground">
                      {item.ip_pattern || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {item.pattern_type === 'single_ip' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">{t('whitelist.singleIp')}</span>
                      )}
                      {item.pattern_type === 'cidr' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">{t('whitelist.cidr')}</span>
                      )}
                      {item.pattern_type === 'ip_range' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">{t('whitelist.ipRange')}</span>
                      )}
                      {item.pattern_type === 'mac_only' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground">{t('whitelist.macOnly')}</span>
                      )}
                      {item.pattern_type === 'both' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">{t('whitelist.both')}</span>
                      )}
                      {!item.pattern_type && (
                        <span className="text-sm text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-muted-foreground">
                        <User className="h-4 w-4 mr-1.5 text-muted-foreground" />
                        {item.added_by}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Clock className="h-4 w-4 mr-1.5 text-muted-foreground" />
                        {formatDate(item.created_at)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <p className="text-sm text-muted-foreground max-w-xs truncate">{item.comments}</p>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <IconButton
                          icon={Eye}
                          variant="primary"
                          size="md"
                          title={t('terminal.viewDetails')}
                          onClick={() => handleViewDetails(item)}
                        />
                        <IconButton
                          icon={Trash2}
                          variant="danger"
                          size="md"
                          title={t('terminal.removeFromWhitelist')}
                          onClick={() => handleRemoveWhitelist(item.mac_address, item.ip_pattern)}
                        />
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Bottom Pagination - Full Features */}
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={handlePageChange}
          pageSize={pageSize}
          onPageSizeChange={handlePageSizeChange}
          totalItems={totalFromServer}
          variant="bottom"
        />
      </div>

      {/* Add Modal */}
      <Modal isOpen={showAddModal} onClose={() => { setShowAddModal(false); setMacAddress(''); setIpAddress(''); setComments(''); setCommentsError(''); }} title={t('whitelist.addAllowedTerminal')} size="lg">
        <p className="text-sm text-muted-foreground mb-6">{t('whitelist.enterMacIpOrBoth')}</p>

        {/* Format Help - Always visible */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <p className="text-sm font-medium text-blue-800 mb-2">{t('whitelist.formatTips')}</p>
          <div className="grid grid-cols-2 gap-2 text-xs text-blue-700">
            <div>
              <p className="font-medium">{t('whitelist.macAddressLabel')}</p>
              <ul className="space-y-0.5 ml-2">
                <li>• <code className="bg-blue-100 px-1 rounded">AA:BB:CC:DD:EE:FF</code></li>
                <li>• <code className="bg-blue-100 px-1 rounded">AA-BB-CC-DD-EE-FF</code></li>
                <li>• <code className="bg-blue-100 px-1 rounded">AABBCCDDEEFF</code></li>
              </ul>
            </div>
            <div>
              <p className="font-medium">{t('whitelist.ipAddressRange')}</p>
              <ul className="space-y-0.5 ml-2">
                <li>• <code className="bg-blue-100 px-1 rounded">192.168.1.100</code></li>
                <li>• <code className="bg-blue-100 px-1 rounded">192.168.1.0/24</code></li>
                <li>• <code className="bg-blue-100 px-1 rounded">192.168.1.1-100</code></li>
              </ul>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {/* MAC Address Field */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
              <Server className="h-4 w-4 text-muted-foreground" />
              {t('whitelist.macAddressLabel')} <span className="text-muted-foreground font-normal">({t('common.optional')})</span>
            </label>
            <input
              type="text"
              placeholder="00:11:22:33:44:55"
              value={macAddress}
              onChange={(e) => setMacAddress(e.target.value)}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
            />
            {macAddress && isValidMacAddress(macAddress) && (
              <p className="mt-2 text-sm text-green-600 flex items-center gap-1">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                {t('whitelist.normalized')}: {normalizeMacAddress(macAddress)}
              </p>
            )}
          </div>

          {/* IP Address Field */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
              <Globe className="h-4 w-4 text-muted-foreground" />
              {t('whitelist.ipAddressRange')} <span className="text-muted-foreground font-normal">({t('common.optional')})</span>
            </label>
            <input
              type="text"
              placeholder="192.168.1.1, 192.168.1.0/24, 10.0.1.1-100"
              value={ipAddress}
              onChange={(e) => setIpAddress(e.target.value)}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
            />
            <p className="mt-1.5 text-xs text-muted-foreground">
              {t('whitelist.supportsSingleIpCidrRange')}
            </p>
          </div>

          {/* Comments - Required */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              {t('terminal.comments')} <span className="text-red-500">*</span>
            </label>
            <textarea
              placeholder={t('whitelist.describeEntry')}
              value={comments}
              onChange={(e) => {
                setComments(e.target.value);
                if (e.target.value.trim()) {
                  setCommentsError('');
                }
              }}
              rows={2}
              className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm ${
                commentsError ? 'border-red-500' : 'border-border'
              }`}
            />
            {commentsError && <p className="text-red-600 text-xs mt-1">{commentsError}</p>}
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-4">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => {
                setShowAddModal(false);
                setMacAddress('');
                setIpAddress('');
                setComments('');
                setCommentsError('');
              }}
              className="flex-1"
            />
            <PrimaryButton
              icon={Plus}
              label={t('common.add')}
              variant="success"
              onClick={handleAddWhitelist}
              loading={isAdding}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal isOpen={showDeleteModal} onClose={() => { setShowDeleteModal(false); setDeleteIdentifier(''); setDeleteIpPattern(''); }} title={t('whitelist.removeFromWhitelistTitle')} size="sm">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
            <Trash2 className="h-6 w-6 text-red-600" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('common.cannotBeUndone')}</p>
          </div>
        </div>

        <p className="text-muted-foreground mb-6">
          {t('whitelist.areYouSureRemoveWhitelist')} <span className="font-mono font-medium">{deleteIdentifier || deleteIpPattern}</span>
        </p>

        <div className="flex gap-3">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => {
              setShowDeleteModal(false);
              setDeleteIdentifier('');
              setDeleteIpPattern('');
            }}
            className="flex-1"
          />
          <PrimaryButton
            icon={Trash2}
            label={t('common.remove')}
            variant="danger"
            onClick={confirmDelete}
            loading={isDeleting}
            className="flex-1"
          />
        </div>
      </Modal>

      {/* Details Modal */}
      <Modal isOpen={showDetailsModal && !!selectedEntry} onClose={() => { setShowDetailsModal(false); setSelectedEntry(null); }} title={t('whitelist.whitelistEntryDetails')} size="md">
        {selectedEntry && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
              <Globe className="h-6 w-6 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">ID: {selectedEntry.id}</p>
            </div>
          </div>

          <div className="bg-background rounded-lg p-4">
            <div className="space-y-3">
              {selectedEntry.mac_address && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('whitelist.macAddress')}</span>
                  <span className="font-mono text-foreground">{selectedEntry.mac_address}</span>
                </div>
              )}

              {selectedEntry.ip_pattern && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('whitelist.ipAddress')}</span>
                  <span className="font-mono text-foreground">{selectedEntry.ip_pattern}</span>
                </div>
              )}
              <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('whitelist.patternType')}</span>
                  <span className="text-foreground capitalize">
                    {selectedEntry.pattern_type === 'single_ip' && t('whitelist.singleIp')}
                    {selectedEntry.pattern_type === 'cidr' && t('whitelist.cidr')}
                    {selectedEntry.pattern_type === 'ip_range' && t('whitelist.ipRange')}
                    {selectedEntry.pattern_type === 'mac_only' && t('whitelist.macOnly')}
                    {selectedEntry.pattern_type === 'both' && t('whitelist.both')}
                    {!selectedEntry.pattern_type && '-'}
                  </span>
                </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('whitelist.addedBy')}</span>
                <span className="text-foreground">{selectedEntry.added_by}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('whitelist.addedDate')}</span>
                <span className="text-foreground">{formatDate(selectedEntry.created_at)}</span>
              </div>
            </div>
          </div>

          <div>
            <span className="text-muted-foreground block mb-2">{t('terminal.comments')}</span>
            <p className="text-foreground bg-background rounded-lg p-4">
              {selectedEntry.comments || t('common.noComments')}
            </p>
          </div>

          <PrimaryButton
            icon={Trash2}
            label={t('terminal.removeFromWhitelist')}
            variant="danger"
            onClick={() => {
              handleRemoveWhitelist(selectedEntry.mac_address, selectedEntry.ip_pattern);
              setShowDetailsModal(false);
              setSelectedEntry(null);
            }}
            className="w-full"
          />
        </div>
        )}
      </Modal>

      {/* Import Modal */}
      <Modal isOpen={showImportModal} onClose={resetImportModal} title={t('whitelist.importWhitelist')} size="lg">
        <div className="space-y-5">
          {/* Description */}
          <p className="text-sm text-muted-foreground">{t('whitelist.importDescription')}</p>

          {/* CSV Format Hint */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-blue-800">{t('whitelist.csvFormatHint')}</p>
              <button
                onClick={downloadTemplate}
                className="text-xs text-blue-600 hover:text-blue-800 underline font-medium"
              >
                {t('whitelist.downloadTemplate')}
              </button>
            </div>
            <p className="text-xs text-blue-700">{t('whitelist.csvFormatDescription')}</p>
            <p className="text-xs text-blue-700 mt-1">{t('whitelist.backupFormatDescription')}</p>
          </div>

          {/* File Upload Area */}
          <div
            className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors ${
              importFile ? 'border-green-400 bg-green-50' : 'border-border hover:border-blue-400'
            }`}
            onClick={() => {
              const input = document.getElementById('import-file-input') as HTMLInputElement;
              input?.click();
            }}
          >
            <input
              id="import-file-input"
              type="file"
              accept=".csv,.zip,.json"
              className="hidden"
              onChange={(e) => handleImportFileSelect(e.target.files?.[0] || null)}
            />
            {importFile ? (
              <div className="flex flex-col items-center gap-2">
                <FileText className="h-10 w-10 text-green-500" />
                <p className="text-sm font-medium text-foreground">{importFile.name}</p>
                <p className="text-xs text-muted-foreground">
                  {t('whitelist.fileSize')}: {(importFile.size / 1024).toFixed(1)} KB
                </p>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleImportFileSelect(null);
                  }}
                  className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1 mt-1"
                >
                  <X className="h-3 w-3" />
                  {t('common.cancel')}
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Upload className="h-10 w-10 text-muted-foreground" />
                <p className="text-sm font-medium text-foreground">{t('whitelist.dragToUpload')}</p>
                <p className="text-xs text-muted-foreground">{t('whitelist.fileFormatHint')}</p>
                <p className="text-xs text-muted-foreground">{t('whitelist.fileOrBackupFormatHint')}</p>
              </div>
            )}
          </div>

          {/* Conflict Mode Selection */}
          <div className="space-y-2">
            <p className="text-sm font-medium text-foreground">{t('whitelist.conflictMode')}</p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => { setImportMode('skip'); setImportResult(null); }}
                className={`p-3 rounded-lg border-2 text-left transition-all ${
                  importMode === 'skip'
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-border hover:border-blue-300'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  {importMode === 'skip' ? (
                    <CheckCircle className="h-4 w-4 text-blue-500" />
                  ) : (
                    <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                  )}
                  <span className="text-sm font-medium text-foreground">{t('whitelist.skipMode')}</span>
                </div>
                <p className="text-xs text-muted-foreground ml-6">{t('whitelist.skipModeDesc')}</p>
              </button>

              <button
                onClick={() => { setImportMode('overwrite'); setImportResult(null); }}
                className={`p-3 rounded-lg border-2 text-left transition-all ${
                  importMode === 'overwrite'
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-border hover:border-blue-300'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  {importMode === 'overwrite' ? (
                    <CheckCircle className="h-4 w-4 text-blue-500" />
                  ) : (
                    <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                  )}
                  <span className="text-sm font-medium text-foreground">{t('whitelist.overwriteMode')}</span>
                </div>
                <p className="text-xs text-muted-foreground ml-6">{t('whitelist.overwriteModeDesc')}</p>
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3">
            <PrimaryButton
              label={t('whitelist.validateButton')}
              variant="secondary"
              onClick={() => handleImport(true)}
              loading={isValidating}
              disabled={!importFile}
              className="flex-1"
            />
            <PrimaryButton
              icon={Upload}
              label={t('whitelist.importButton')}
              variant="success"
              onClick={() => handleImport(false)}
              loading={importing}
              disabled={!importFile}
              className="flex-1"
            />
          </div>

          {/* Import Result */}
          {importResult && (
            <div className="bg-background rounded-lg border border-border p-4 space-y-4">
              <div className="flex items-center gap-2">
                {importResult.failed_count > 0 ? (
                  <AlertCircle className="h-5 w-5 text-red-500" />
                ) : (
                  <CheckCircle className="h-5 w-5 text-green-500" />
                )}
                <p className="text-sm font-semibold text-foreground">{t('whitelist.importResult')}</p>
              </div>

              <div className="grid grid-cols-4 gap-3">
                <div className="text-center p-2 bg-green-50 rounded-lg">
                  <p className="text-lg font-bold text-green-600">{importResult.success_count}</p>
                  <p className="text-xs text-green-700">{t('whitelist.successCount')}</p>
                </div>
                <div className="text-center p-2 bg-yellow-50 rounded-lg">
                  <p className="text-lg font-bold text-yellow-600">{importResult.skipped_count}</p>
                  <p className="text-xs text-yellow-700">{t('whitelist.skippedCount')}</p>
                </div>
                <div className="text-center p-2 bg-red-50 rounded-lg">
                  <p className="text-lg font-bold text-red-600">{importResult.failed_count}</p>
                  <p className="text-xs text-red-700">{t('whitelist.failedCount')}</p>
                </div>
                <div className="text-center p-2 bg-blue-50 rounded-lg">
                  <p className="text-lg font-bold text-blue-600">{importResult.total_processed}</p>
                  <p className="text-xs text-blue-700">{t('whitelist.totalProcessed')}</p>
                </div>
              </div>

              {importResult.errors.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-foreground mb-2">{t('whitelist.errors')}</p>
                  <div className="max-h-48 overflow-y-auto border border-border rounded-lg">
                    <table className="w-full text-xs">
                      <thead className="bg-muted sticky top-0">
                        <tr>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">{t('whitelist.rowNumber')}</th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground">{t('whitelist.errorReason')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {importResult.errors.slice(0, 50).map((err, idx) => (
                          <tr key={idx} className="border-t border-border">
                            <td className="px-3 py-2 font-mono text-red-600">{err.row}</td>
                            <td className="px-3 py-2 text-muted-foreground">{err.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {importResult.errors.length > 50 && (
                      <p className="text-xs text-muted-foreground p-2 text-center border-t border-border">
                        ... {importResult.errors.length - 50} more errors not shown
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Close Button */}
          <div className="flex justify-end pt-2">
            <PrimaryButton
              label={t('common.close')}
              variant="secondary"
              onClick={resetImportModal}
            />
          </div>
        </div>
      </Modal>
      </>
      )}
    </div>
  );
};

export default Whitelist;
