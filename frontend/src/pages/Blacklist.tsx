import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Search, AlertTriangle, Clock, Server, Download, Eye, Shield, RefreshCw, ChevronDown, Unlock, ShieldCheck, ShieldAlert, AlertCircle } from 'lucide-react';
import { useBlacklist, useBlacklistStats, useRetryBlacklistEntry, BlacklistEntry } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';
import { DateRangeFilter } from '@/components/DateRangeFilter';
import { formatDate, useDebounce, getErrorMessage } from '@/lib/utils';

const REFRESH_OPTIONS: { labelKey?: string; label: string; value: number }[] = [
  { labelKey: 'common.off', label: 'Off', value: 0 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 },
];



const Blacklist: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [showFirewallErrorsModal, setShowFirewallErrorsModal] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<BlacklistEntry | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [autoRefresh, setAutoRefresh] = useState<number>(0);
  const [category, setCategory] = useState<string | undefined>(undefined);

  // Debounce search term
  const debouncedSearch = useDebounce(searchTerm, 500);

  // Always show active (blocked) records only when no category filter applied
  const statusParam = 'active';

  const { data: blacklistData, isLoading, refetch } = useBlacklist({
    search: debouncedSearch || undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    status: category ? undefined : statusParam,
    category,
    skip: (currentPage - 1) * pageSize,
    limit: pageSize,
    refetchInterval: autoRefresh || undefined,
  });

  const { data: stats } = useBlacklistStats();
  const retryMutation = useRetryBlacklistEntry();





  // Extract items and total from paginated response
  const filteredBlacklist = blacklistData?.items ?? [];
  const totalFromServer = blacklistData?.total ?? 0;

  const totalPages = Math.ceil(totalFromServer / pageSize);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleViewDetails = (entry: BlacklistEntry) => {
    setSelectedEntry(entry);
    setShowDetailsModal(true);
  };

  const handleReset = () => {
    refetch();
    setSearchTerm('');
    setStartDate('');
    setEndDate('');
    setCurrentPage(1);
  };

  const handleCategorySelect = (cat: string) => {
    setCategory((prev) => (prev === cat ? undefined : cat));
    setCurrentPage(1);
  };

  const handlePendingRetryBlock = () => {
    navigate('/terminals?compliance_status=non_compliant&status=unblocked&arp_enabled_only=1');
  };

  const handleFirewallErrors = () => {
    setShowFirewallErrorsModal(true);
  };

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (debouncedSearch) params['search'] = debouncedSearch;
      if (startDate) params['start_date'] = startDate;
      if (endDate) params['end_date'] = endDate;
      params['status'] = statusParam;

      const response = await apiClient.get(API_ENDPOINTS.BLACKLIST_EXPORT, {
        params,
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'blacklist.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('blacklist.failedToExport')));
    }
  };

  const isExpired = (expiresAt: string | null) => expiresAt ? new Date(expiresAt) < new Date() : false;

  const handleRetryUnblock = async (entry: BlacklistEntry) => {
    try {
      await retryMutation.mutateAsync(entry.id);
      toast.success(t('blacklist.retryUnblockSuccess'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('blacklist.retryUnblockFailed')));
    }
  };

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {isLoading && !blacklistData ? (
        <PageSkeleton />
      ) : (
      <>
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('blacklist.blockedTerminals')}</h1>
          <p className="text-muted-foreground mt-1">{t('blacklist.manageBlocked')}</p>
        </div>
        <PrimaryButton
          icon={Download}
          label={t('common.export')}
          variant="success"
          onClick={handleExport}
        />
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4 mb-6">
        <button
          type="button"
          onClick={() => handleCategorySelect('success_blocked')}
          className={`bg-card rounded-2xl border p-5 shadow-sm text-left transition-colors ${
            category === 'success_blocked' ? 'border-blue-500 ring-2 ring-blue-200' : 'border-border hover:border-blue-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{t('blacklist.statsSuccessBlocked')}</p>
              <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-1">{stats?.success_blocked ?? 0}</p>
            </div>
            <ShieldCheck className="h-8 w-8 text-green-500" />
          </div>
        </button>

        <button
          type="button"
          onClick={handlePendingRetryBlock}
          title={t('blacklist.pendingRetryBlockHint')}
          className="bg-card rounded-2xl border border-border p-5 shadow-sm text-left transition-colors hover:border-yellow-300"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{t('blacklist.statsPendingRetryBlock')}</p>
              <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400 mt-1">{stats?.pending_retry_block ?? 0}</p>
            </div>
            <ShieldAlert className="h-8 w-8 text-yellow-500" />
          </div>
        </button>

        <button
          type="button"
          onClick={() => handleCategorySelect('success_unblocked')}
          className={`bg-card rounded-2xl border p-5 shadow-sm text-left transition-colors ${
            category === 'success_unblocked' ? 'border-blue-500 ring-2 ring-blue-200' : 'border-border hover:border-blue-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{t('blacklist.statsSuccessUnblocked')}</p>
              <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-1">{stats?.success_unblocked ?? 0}</p>
            </div>
            <ShieldCheck className="h-8 w-8 text-blue-500" />
          </div>
        </button>

        <button
          type="button"
          onClick={() => handleCategorySelect('pending_retry_unblock')}
          className={`bg-card rounded-2xl border p-5 shadow-sm text-left transition-colors ${
            category === 'pending_retry_unblock' ? 'border-blue-500 ring-2 ring-blue-200' : 'border-border hover:border-orange-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{t('blacklist.statsPendingRetryUnblock')}</p>
              <p className="text-3xl font-bold text-orange-600 mt-1">{stats?.pending_retry_unblock ?? 0}</p>
            </div>
            <Clock className="h-8 w-8 text-orange-500" />
          </div>
        </button>

        <button
          type="button"
          onClick={handleFirewallErrors}
          className="bg-card rounded-2xl border border-border p-5 shadow-sm text-left transition-colors hover:border-red-300"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{t('blacklist.statsFirewallErrors')}</p>
              <p className={`text-3xl font-bold mt-1 ${stats?.firewall_errors?.length ? 'text-red-600' : 'text-muted-foreground'}`}>
                {stats?.firewall_errors?.length ?? 0}
              </p>
            </div>
            <AlertCircle className={`h-8 w-8 ${stats?.firewall_errors?.length ? 'text-red-500' : 'text-muted-foreground'}`} />
          </div>
        </button>
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
                placeholder={t('blacklist.searchByMacOrIp')}
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

              {/* Manual Refresh Button */}
              <IconButton
                icon={RefreshCw}
                variant="secondary"
                size="sm"
                title={t('common.refresh')}
                onClick={async () => { await refetch(); toast.success(t('terminal.dataRefreshed')); }}
              />

              {/* Auto Refresh Selector */}
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <Clock className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={autoRefresh}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setAutoRefresh(val);
                    if (val > 0) {
                      toast.success(t('terminal.autoRefreshEnabled', { seconds: val / 1000 }));
                    } else {
                      toast.info(t('terminal.autoRefreshDisabled'));
                    }
                  }}
                  className="bg-transparent py-1.5 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[4rem]"
                >
                  {REFRESH_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.labelKey ? t(opt.labelKey) : opt.label}</option>
                  ))}
                </select>
              </div>

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

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-card">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('terminal.mac')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.ip')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.reason')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.firewall')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.status')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.blockedAt')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.expiresAt')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.unblockEvent')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {filteredBlacklist?.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <EmptyState
                      icon={Shield}
                      title={t('blacklist.noBlockedTerminals')}
                      description={t('blacklist.noBlockedDescription')}
                    />
                  </td>
                </tr>
              ) : (
                (filteredBlacklist || []).map((item) => (
                  <tr
                    key={item.id}
                    className={`hover:bg-muted/40 transition-colors ${
                      (item.auto_unblocked || item.unblocked_at) ? 'opacity-60' : isExpired(item.expires_at) ? 'opacity-50' : ''
                    } ${!(item.auto_unblocked || item.unblocked_at) && item.is_auto_blocked ? 'bg-orange-500/10 dark:bg-orange-500/15' : ''}`}
                  >
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 text-muted-foreground mr-2 flex-shrink-0" />
                        <span className="font-mono text-sm font-medium text-foreground">
                          {item.mac_address}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-muted-foreground">
                      {item.ip_address}
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <div className="flex items-center">
                        <AlertTriangle className="h-4 w-4 text-red-400 mr-2 flex-shrink-0" />
                        <span className="text-sm text-muted-foreground">{item.reason}</span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      {item.firewall_tag || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        {item.last_operation_status === 'success' ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            {t('blacklist.opSuccess')}
                          </span>
                        ) : item.last_operation_status === 'failed' ? (
                          <span
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800"
                            title={item.last_operation_error || undefined}
                          >
                            {t('blacklist.opFailed')}
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground">
                            —
                          </span>
                        )}
                        {(item.retry_count ?? 0) > 0 && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                            {t('blacklist.retryCount', { count: item.retry_count })}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Clock className="h-4 w-4 mr-1.5 text-muted-foreground" />
                        {formatDate(item.blocked_at)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center text-sm ${
                          isExpired(item.expires_at) ? 'text-muted-foreground line-through' : 'text-muted-foreground'
                        }`}
                      >
                        {formatDate(item.expires_at)}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      {(item.auto_unblocked || item.unblocked_at) ? (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5">
                            <Unlock className="h-3.5 w-3.5 text-green-600 flex-shrink-0" />
                            <span className="text-sm text-foreground">{item.reason || '—'}</span>
                          </div>
                          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                            <Clock className="h-3.5 w-3.5 flex-shrink-0" />
                            {formatDate(item.unblocked_at)}
                          </div>
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={Eye}
                          size="md"
                          title={t('terminal.viewDetails')}
                          onClick={() => handleViewDetails(item)}
                        />
                        {!(item.auto_unblocked || item.unblocked_at) &&
                          (item.terminal_compliance_status === 'compliant' ||
                            item.terminal_compliance_status === 'bypass') && (
                          <IconButton
                            icon={Unlock}
                            size="md"
                            variant="success"
                            title={t('blacklist.retryUnblock')}
                            loading={retryMutation.isPending}
                            onClick={() => handleRetryUnblock(item)}
                          />
                        )}
                      </ButtonGroup>
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
          totalItems={filteredBlacklist.length}
          variant="bottom"
        />
      </div>

      {/* Details Modal */}
      <Modal isOpen={showDetailsModal && !!selectedEntry} onClose={() => { setShowDetailsModal(false); setSelectedEntry(null); }} title={t('blacklist.blockedTerminalDetails')} size="md">
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <div className={`w-12 h-12 rounded-full flex items-center justify-center ${(selectedEntry?.auto_unblocked || selectedEntry?.unblocked_at) ? 'bg-green-100' : 'bg-red-100'}`}>
              {(selectedEntry?.auto_unblocked || selectedEntry?.unblocked_at) ? (
                <Unlock className="h-6 w-6 text-green-600" />
              ) : (
                <AlertTriangle className="h-6 w-6 text-red-600" />
              )}
            </div>
            <p className="text-sm text-muted-foreground">ID: {selectedEntry?.id}</p>
          </div>

          <div className="bg-background rounded-lg p-4">
            <div className="space-y-3">
              {selectedEntry?.mac_address && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('terminal.mac')}</span>
                  <span className="font-mono text-foreground">{selectedEntry.mac_address}</span>
                </div>
              )}
              {selectedEntry?.ip_address && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('blacklist.ip')}</span>
                  <span className="font-mono text-foreground">{selectedEntry.ip_address}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.reason')}</span>
                <span className="text-foreground">{selectedEntry?.reason}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.blockedBy')}</span>
                <span className="text-foreground">{selectedEntry?.blocked_by}</span>
              </div>
              {selectedEntry?.source_tag && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('terminal.sourceTag')}</span>
                  <span className="text-foreground">{selectedEntry.source_tag}</span>
                </div>
              )}
              {selectedEntry?.firewall_tag && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('blacklist.firewall')}</span>
                  <span className="text-foreground">{selectedEntry.firewall_tag}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.blockType')}</span>
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${selectedEntry?.is_auto_blocked ? 'bg-orange-100 text-orange-800' : 'bg-blue-100 text-blue-800'}`}>
                  {selectedEntry?.is_auto_blocked ? t('blacklist.auto') : t('blacklist.manual')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.autoUnblocked')}</span>
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${(selectedEntry?.auto_unblocked || selectedEntry?.unblocked_at) ? 'bg-green-100 text-green-800' : 'bg-muted text-foreground'}`}>
                  {(selectedEntry?.auto_unblocked || selectedEntry?.unblocked_at) ? t('common.yes') : t('common.no')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.blockedAt')}</span>
                <span className="text-foreground">{formatDate(selectedEntry?.blocked_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.expires')}</span>
                <span className={`${isExpired(selectedEntry?.expires_at || null) ? 'text-muted-foreground line-through' : 'text-foreground'}`}>
                  {formatDate(selectedEntry?.expires_at)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('common.status')}</span>
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                  (selectedEntry?.auto_unblocked || selectedEntry?.unblocked_at)
                    ? 'bg-green-100 text-green-800'
                    : isExpired(selectedEntry?.expires_at || null)
                      ? 'bg-muted text-foreground'
                      : 'bg-red-100 text-red-800'
                }`}>
                  {(selectedEntry?.auto_unblocked || selectedEntry?.unblocked_at)
                    ? t('blacklist.unblockedLabel')
                    : isExpired(selectedEntry?.expires_at || null)
                      ? t('common.expired')
                      : t('common.active')}
                </span>
              </div>
            </div>
          </div>

          
        </div>
      </Modal>

      {/* Firewall Errors Modal */}
      <Modal
        isOpen={showFirewallErrorsModal}
        onClose={() => setShowFirewallErrorsModal(false)}
        title={t('blacklist.firewallErrorsTitle')}
        size="md"
      >
        <div className="space-y-3">
          {stats?.synced_at && (
            <p className="text-xs text-muted-foreground">
              {t('blacklist.firewallReconcileTime')}: {formatDate(stats.synced_at)}
            </p>
          )}
          {stats?.firewall_errors?.length ? (
            <ul className="space-y-3">
              {stats.firewall_errors.map((fw, idx) => (
                <li key={idx} className="rounded-lg border border-red-100 bg-red-50 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                    {fw.tag}
                  </div>
                  {fw.error && (
                    <p className="mt-1 pl-6 text-sm text-muted-foreground">{fw.error}</p>
                  )}
                </li>
              ))}
            </ul>
          ) : stats?.synced_at ? (
            <p className="text-sm text-muted-foreground">{t('blacklist.noFirewallErrors')}</p>
          ) : (
            <p className="text-sm text-muted-foreground">{t('blacklist.noReconcileData')}</p>
          )}
        </div>
      </Modal>
      </>
      )}
    </div>
  );
};

export default Blacklist;
