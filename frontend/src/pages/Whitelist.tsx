import React, { useState } from 'react';
import { useWhitelist, WhitelistEntry } from '@/hooks/useTerminalData';
import { useTranslation } from 'react-i18next';
import { Search, Plus, Trash2, User, Server, Globe, RefreshCw, Download, Clock, ChevronDown, Eye } from 'lucide-react';
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
            <thead className="bg-background">
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
                <span className="text-foreground capitalize">{selectedEntry.pattern_type?.replace('_', ' ') || '-'}</span>
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
      </>
      )}
    </div>
  );
};

export default Whitelist;
