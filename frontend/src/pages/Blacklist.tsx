import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Trash2, AlertTriangle, Clock, Server, Download, Eye, Shield, RefreshCw, ChevronDown } from 'lucide-react';
import { useBlacklist, BlacklistEntry, useDataSources } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';
import { DateRangeFilter } from '@/components/DateRangeFilter';
import { downloadCSV, formatDate, normalizeMacAddress, isValidMacAddress, isValidCidrOrRange, useDebounce, getErrorMessage } from '@/lib/utils';

const REFRESH_OPTIONS = [
  { labelKey: 'common.off', label: 'Off', value: 0 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 },
];

const Blacklist: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [deleteEntry, setDeleteEntry] = useState<BlacklistEntry | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<BlacklistEntry | null>(null);
  const [newEntry, setNewEntry] = useState({
    mac_address: '',
    ip_address: '',
    reason: '',
    block_time: '30d',
    firewall_tag: '',
  });
  const [macError, setMacError] = useState('');
  const [ipError, setIpError] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [isAdding, setIsAdding] = useState(false);
  const [isUnblocking, setIsUnblocking] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [autoRefresh, setAutoRefresh] = useState<number>(0);

  // Debounce search term
  const debouncedSearch = useDebounce(searchTerm, 500);

  const { data: blacklistData, isLoading, refetch } = useBlacklist({
    search: debouncedSearch || undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: (currentPage - 1) * pageSize,
    limit: pageSize,
    refetchInterval: autoRefresh || undefined,
  });

  const { data: dataSources } = useDataSources();

  const firewallOptions = useMemo(
    () => (dataSources || []).filter((ds) => ds.type === 'sangfor' && ds.enabled),
    [dataSources],
  );

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

  const handleAddBlacklist = async () => {
    if (!newEntry.mac_address && !newEntry.ip_address) {
      toast.error(t('blacklist.pleaseEnterMacOrIp'));
      return;
    }
    if (!newEntry.reason) {
      toast.error(t('blacklist.pleaseSelectReason'));
      return;
    }

    // Validate MAC address format
    if (newEntry.mac_address && !isValidMacAddress(newEntry.mac_address)) {
      setMacError(t('blacklist.invalidMacFormat'));
      return;
    }
    setMacError('');

    // Validate IP address format
    if (newEntry.ip_address && !isValidCidrOrRange(newEntry.ip_address)) {
      setIpError(t('blacklist.invalidIpFormat'));
      return;
    }
    setIpError('');

    setIsAdding(true);
    try {
      const payload: Record<string, string> = {
        reason: newEntry.reason,
        block_time: newEntry.block_time,
      };
      if (newEntry.mac_address) payload['mac_address'] = normalizeMacAddress(newEntry.mac_address);
      if (newEntry.ip_address) payload['ip_address'] = newEntry.ip_address;
      if (newEntry.firewall_tag) payload['firewall_tag'] = newEntry.firewall_tag;

      await apiClient.post(API_ENDPOINTS.BLACKLIST, payload);
      toast.success(t('blacklist.terminalBlockedSuccessfully'));
      setNewEntry({ mac_address: '', ip_address: '', reason: '', block_time: '30d', firewall_tag: '' });
      setShowAddModal(false);
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('blacklist.failedToBlock')));
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemoveBlacklist = (entry: BlacklistEntry) => {
    setDeleteEntry(entry);
    setShowDeleteModal(true);
  };

  const confirmUnblock = async () => {
    if (!deleteEntry) return;

    setIsUnblocking(true);
    try {
      const identifier = deleteEntry.mac_address || deleteEntry.ip_address;
      await apiClient.delete(`${API_ENDPOINTS.BLACKLIST}${identifier}`);
      toast.success(t('blacklist.unblockedSuccessfully'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('blacklist.failedToUnblock')));
    } finally {
      setIsUnblocking(false);
      setShowDeleteModal(false);
      setDeleteEntry(null);
    }
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

  const handleExport = () => {
    const headers = [t('terminal.mac'), t('blacklist.ip'), t('blacklist.reason'), t('blacklist.blockedBy'), t('blacklist.firewall'), t('whitelist.type'), t('blacklist.autoUnblocked'), t('blacklist.blockedAt'), t('blacklist.expiresAt')];
    const rows = filteredBlacklist?.map((item) => [
      item.mac_address || '',
      item.ip_address || '',
      item.reason,
      item.blocked_by,
      item.firewall_tag || '',
      item.is_auto_blocked ? t('blacklist.auto') : t('blacklist.manual'),
      item.auto_unblocked ? t('common.yes') : t('common.no'),
      formatDate(item.blocked_at),
      formatDate(item.expires_at)
    ]) || [];

    downloadCSV(headers, rows, 'blocked-terminals');
  };

  const isExpired = (expiresAt: string | null) => expiresAt ? new Date(expiresAt) < new Date() : false;

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
        <ButtonGroup>
          <PrimaryButton
            icon={Download}
            label={t('common.export')}
            variant="success"
            onClick={handleExport}
          />
          <PrimaryButton
            icon={Shield}
            label={t('blacklist.blockTerminal')}
            variant="danger"
            onClick={() => setShowAddModal(true)}
          />
        </ButtonGroup>
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
                onClick={() => refetch()}
              />

              {/* Auto Refresh Selector */}
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <Clock className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={autoRefresh}
                  onChange={(e) => setAutoRefresh(Number(e.target.value))}
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

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-red-600">{totalFromServer}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('blacklist.blockedDevices')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-red-400 to-red-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-orange-600">
              {filteredBlacklist?.filter((b) => b.is_auto_blocked).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('blacklist.autoBlocked')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-orange-400 to-orange-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-blue-600">
              {filteredBlacklist?.filter((b) => !b.is_auto_blocked).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('blacklist.manualBlocked')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-amber-600">
              {filteredBlacklist?.filter((b) => isExpired(b.expires_at)).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('blacklist.expiredBlocks')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-amber-400 to-amber-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-muted-foreground">
              {filteredBlacklist?.filter((b) => !isExpired(b.expires_at)).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('blacklist.activeBlocks')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-400 to-gray-600" />
        </div>
      </div>

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
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
                  {t('whitelist.type')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.blockedBy')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.firewall')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.blockedAt')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('blacklist.expiresAt')}
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
                    className={`hover:bg-blue-50/30 transition-colors ${
                      isExpired(item.expires_at) ? 'opacity-50' : ''
                    } ${item.is_auto_blocked ? 'bg-orange-50/30' : ''}`}
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
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {item.is_auto_blocked ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                          {t('blacklist.auto')}
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {t('blacklist.manual')}
                        </span>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      {item.blocked_by}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      {item.firewall_tag || '-'}
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
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={Eye}
                          variant="primary"
                          size="md"
                          title={t('terminal.viewDetails')}
                          onClick={() => handleViewDetails(item)}
                        />
                        <IconButton
                          icon={Trash2}
                          variant="success"
                          size="md"
                          title={t('terminal.unblockTerminal')}
                          onClick={() => handleRemoveBlacklist(item)}
                        />
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

      {/* Add Modal */}
      <Modal isOpen={showAddModal} onClose={() => { setShowAddModal(false); setNewEntry({ mac_address: '', ip_address: '', reason: '', block_time: '30d', firewall_tag: '' }); setMacError(''); setIpError(''); }} title={t('blacklist.blockTerminal')} size="md">
        <p className="text-sm text-muted-foreground mb-6">{t('blacklist.enterMacIpOrBoth')}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              {t('terminal.mac')} <span className="text-muted-foreground font-normal">({t('common.optional')})</span>
            </label>
            <input
              type="text"
              placeholder="00:11:22:33:44:55"
              value={newEntry.mac_address}
              onChange={(e) => {
                setNewEntry({ ...newEntry, mac_address: e.target.value });
                setMacError('');
              }}
              className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm ${
                macError ? 'border-red-500' : 'border-border'
              }`}
            />
            {macError && <p className="text-red-600 text-xs mt-1">{macError}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              {t('blacklist.ip')} <span className="text-muted-foreground font-normal">({t('common.optional')})</span>
            </label>
            <input
              type="text"
              placeholder="192.168.1.100 or 192.168.1.0/24"
              value={newEntry.ip_address}
              onChange={(e) => {
                setNewEntry({ ...newEntry, ip_address: e.target.value });
                setIpError('');
              }}
              className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm ${
                ipError ? 'border-red-500' : 'border-border'
              }`}
            />
            {ipError && <p className="text-red-600 text-xs mt-1">{ipError}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              {t('blacklist.reason')}
            </label>
            <select
              value={newEntry.reason}
              onChange={(e) => setNewEntry({ ...newEntry, reason: e.target.value })}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="">{t('blacklist.selectReason')}</option>
              <option value="Unauthorized access attempt">{t('blacklist.unauthorizedAccess')}</option>
              <option value="Security violation">{t('blacklist.securityViolation')}</option>
              <option value="Malware detected">{t('blacklist.malwareDetected')}</option>
              <option value="Policy violation">{t('blacklist.policyViolation')}</option>
              <option value="Suspicious activity">{t('blacklist.suspiciousActivity')}</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              {t('blacklist.blockDuration')}
            </label>
            <select
              value={newEntry.block_time}
              onChange={(e) => setNewEntry({ ...newEntry, block_time: e.target.value })}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="30m">{t('blacklist.minutes30')}</option>
              <option value="1h">{t('blacklist.hour1')}</option>
              <option value="7d">{t('blacklist.days7')}</option>
              <option value="15d">{t('blacklist.days15')}</option>
              <option value="30d">{t('blacklist.days30')}</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              {t('blacklist.firewall')} <span className="text-muted-foreground font-normal">({t('common.optional')})</span>
            </label>
            <select
              value={newEntry.firewall_tag}
              onChange={(e) => setNewEntry({ ...newEntry, firewall_tag: e.target.value })}
              className="w-full px-4 py-2.5 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="">{t('blacklist.defaultFirewall')}</option>
              {firewallOptions.map((ds) => (
                <option key={ds.id} value={ds.tag}>
                  {ds.tag} ({ds.name})
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => {
                setShowAddModal(false);
                setNewEntry({ mac_address: '', ip_address: '', reason: '', block_time: '30d', firewall_tag: '' });
                setMacError('');
                setIpError('');
              }}
              className="flex-1"
            />
            <PrimaryButton
              icon={Shield}
              label={t('common.block')}
              variant="danger"
              onClick={handleAddBlacklist}
              loading={isAdding}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal isOpen={showDeleteModal && !!deleteEntry} onClose={() => { setShowDeleteModal(false); setDeleteEntry(null); }} title={t('blacklist.confirmUnblock')} size="sm">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
            <Trash2 className="h-6 w-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('blacklist.areYouSureUnblock')}</p>
          </div>
        </div>

        <div className="bg-background rounded-lg p-4 mb-6">
          <div className="space-y-2 text-sm">
            {deleteEntry?.mac_address && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.mac')}:</span>
                <span className="font-mono text-foreground">{deleteEntry.mac_address}</span>
              </div>
            )}
            {deleteEntry?.ip_address && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('blacklist.ip')}:</span>
                <span className="font-mono text-foreground">{deleteEntry.ip_address}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('blacklist.reason')}:</span>
              <span className="text-foreground">{deleteEntry?.reason}</span>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <PrimaryButton
            label="Cancel"
            variant="secondary"
            onClick={() => {
              setShowDeleteModal(false);
              setDeleteEntry(null);
            }}
            className="flex-1"
          />
          <PrimaryButton
            icon={Trash2}
            label={t('common.unblock')}
            variant="success"
            onClick={confirmUnblock}
            loading={isUnblocking}
            className="flex-1"
          />
        </div>
      </Modal>

      {/* Details Modal */}
      <Modal isOpen={showDetailsModal && !!selectedEntry} onClose={() => { setShowDetailsModal(false); setSelectedEntry(null); }} title={t('blacklist.blockedTerminalDetails')} size="md">
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
              <AlertTriangle className="h-6 w-6 text-red-600" />
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
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${selectedEntry?.auto_unblocked ? 'bg-green-100 text-green-800' : 'bg-muted text-foreground'}`}>
                  {selectedEntry?.auto_unblocked ? t('common.yes') : t('common.no')}
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
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${isExpired(selectedEntry?.expires_at || null) ? 'bg-muted text-foreground' : 'bg-red-100 text-red-800'}`}>
                  {isExpired(selectedEntry?.expires_at || null) ? t('common.expired') : t('common.active')}
                </span>
              </div>
            </div>
          </div>

          <PrimaryButton
            icon={Trash2}
            label={t('terminal.unblockTerminal')}
            variant="success"
            onClick={() => {
              if (selectedEntry) handleRemoveBlacklist(selectedEntry);
              setShowDetailsModal(false);
              setSelectedEntry(null);
            }}
            className="w-full"
          />
        </div>
      </Modal>
      </>
      )}
    </div>
  );
};

export default Blacklist;
