import React, { useState, useMemo } from 'react';
import { useTerminals, useBlacklist, Terminal } from '@/hooks/useTerminalData';
import { useTranslation } from 'react-i18next';
import { Search, Filter, RefreshCw, Clock, Server, Shield, ShieldOff, Plus, Download, Eye, Info, ChevronDown, Trash2 } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { STATUS_CONFIG, API_ENDPOINTS } from '@/lib/constants';

const COMPLIANCE_CONFIG: Record<string, { labelKey: string; className: string }> = {
  compliant: { labelKey: 'terminal.complianceStatusValues.compliant', className: 'bg-green-100 text-green-800' },
  bypass: { labelKey: 'terminal.complianceStatusValues.bypass', className: 'bg-blue-100 text-blue-800' },
  non_compliant: { labelKey: 'terminal.complianceStatusValues.non_compliant', className: 'bg-red-100 text-red-800' },
  unknown: { labelKey: 'terminal.complianceStatusValues.unknown', className: 'bg-yellow-100 text-yellow-800' },
};

const REFRESH_OPTIONS = [
  { labelKey: 'common.off', value: 0 },
  { labelKey: '', label: '30s', value: 30000 },
  { labelKey: '', label: '1m', value: 60000 },
  { labelKey: '', label: '5m', value: 300000 },
  { labelKey: '', label: '10m', value: 600000 },
];

import { downloadCSV, formatDate, useDebounce, getErrorMessage } from '@/lib/utils';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';
import { DateRangeFilter } from '@/components/DateRangeFilter';

const Terminals: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterCompliance, setFilterCompliance] = useState<string>('all');
  const [selectedTerminal, setSelectedTerminal] = useState<Terminal | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [autoRefresh, setAutoRefresh] = useState<number>(0);

  // Debounce search term
  const debouncedSearch = useDebounce(searchTerm, 500);

  // Loading states for operations
  const [blockingId, setBlockingId] = useState<number | null>(null);
  const [whitelistId, setWhitelistId] = useState<number | null>(null);
  const [removingWlId, setRemovingWlId] = useState<number | null>(null);
  const [removingBlId, setRemovingBlId] = useState<number | null>(null);

  const { data: terminalsData, isLoading, refetch } = useTerminals({
    ip: debouncedSearch || undefined,
    mac: debouncedSearch || undefined,
    status: filterStatus !== 'all' ? filterStatus : undefined,
    compliance_status: filterCompliance !== 'all' ? filterCompliance : undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: (currentPage - 1) * pageSize,
    limit: pageSize,
    refetchInterval: autoRefresh || undefined,
  });
  const { data: blackListData, refetch: refetchBlacklist } = useBlacklist({
    skip: 0,
    limit: 9999,
  });

  // Extract items and total from paginated response
  const macAddresses = terminalsData?.items ?? [];
  const totalFromServer = terminalsData?.total ?? 0;
  const blackListItems = blackListData?.items ?? [];

  // Build blacklist lookup sets for MAC and IP matching
  const { blackMacSet, blackIpSet, blackEntryMap } = useMemo(() => {
    const macSet = new Set<string>();
    const ipSet = new Set<string>();
    const entryMap = new Map<string, { firewall_tag: string | null; match_type: string }>();

    (blackListItems || []).forEach((item) => {
      if (item.mac_address) {
        macSet.add(item.mac_address.toLowerCase());
        entryMap.set(item.mac_address.toLowerCase(), {
          firewall_tag: item.firewall_tag,
          match_type: 'mac',
        });
      }
      if (item.ip_address) {
        ipSet.add(item.ip_address);
        const existing = entryMap.get(item.ip_address);
        if (existing) {
          existing.match_type = 'both';
        } else {
          entryMap.set(item.ip_address, {
            firewall_tag: item.firewall_tag,
            match_type: 'ip',
          });
        }
      }
    });

    return { blackMacSet: macSet, blackIpSet: ipSet, blackEntryMap: entryMap };
  }, [blackListItems]);

  // Merge ARP data with blacklist data (no whitelist-only entries)
  const allTerminals = useMemo(() => {
    return macAddresses.map((mac) => {
      const macInBlacklist = blackMacSet.has(mac.mac_address?.toLowerCase());
      const ipInBlacklist = blackIpSet.has(mac.ip_address);

      // Determine blacklist info
      let blackMatchType: string | null = null;
      let firewallTag: string | null = null;

      if (macInBlacklist && ipInBlacklist) {
        blackMatchType = 'both';
        const info = blackEntryMap.get(mac.mac_address?.toLowerCase()) || blackEntryMap.get(mac.ip_address);
        firewallTag = info?.firewall_tag || null;
      } else if (macInBlacklist) {
        blackMatchType = 'mac';
        const info = blackEntryMap.get(mac.mac_address?.toLowerCase());
        firewallTag = info?.firewall_tag || null;
      } else if (ipInBlacklist) {
        blackMatchType = 'ip';
        const info = blackEntryMap.get(mac.ip_address);
        firewallTag = info?.firewall_tag || null;
      }

      // Use backend compliance_status, but override with blacklist if needed
      let complianceStatus = mac.compliance_status || 'unknown';
      // If in blacklist and not already marked non_compliant by backend, mark as non_compliant
      if (blackMatchType && complianceStatus !== 'non_compliant') {
        complianceStatus = 'non_compliant';
      }

      return {
        ...mac,
        compliance_status: complianceStatus,
        wl_match_type: mac.wl_match_type || null,
        firewall_tag: firewallTag || mac.firewall_tag || null,
        black_match_type: blackMatchType,
      };
    });
  }, [macAddresses, blackMacSet, blackIpSet, blackEntryMap]);

  const totalPages = Math.ceil(totalFromServer / pageSize);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleBlock = async (mac: Terminal) => {
    setBlockingId(mac.id);
    try {
      await apiClient.post(`${API_ENDPOINTS.TERMINALS_BLOCK}${mac.ip_address}`, null, {
        params: { mac_address: mac.mac_address, block_time: '30d' }
      });
      toast.success(t('terminal.blocked'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToBlock')));
    } finally {
      setBlockingId(null);
    }
  };

  const handleUnblock = async (mac: Terminal) => {
    setBlockingId(mac.id);
    try {
      await apiClient.post(`${API_ENDPOINTS.TERMINALS_UNBLOCK}${mac.ip_address}`);
      toast.success(t('terminal.unblocked'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToUnblock')));
    } finally {
      setBlockingId(null);
    }
  };

  const handleAddToWhitelist = async (mac: Terminal) => {
    setWhitelistId(mac.id);
    try {
      const payload: Record<string, string> = {};
      if (mac.mac_address) payload['mac_address'] = mac.mac_address;
      if (mac.ip_address) payload['ip_address'] = mac.ip_address;
      await apiClient.post(API_ENDPOINTS.WHITELIST, payload);
      toast.success(t('terminal.addedToWhitelist'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToAddToWhitelist')));
    } finally {
      setWhitelistId(null);
    }
  };

  const handleRemoveFromWhitelist = async (mac: Terminal) => {
    const identifier = mac.wl_match_type === 'ip' ? mac.ip_address : mac.mac_address;
    setRemovingWlId(mac.id);
    try {
      await apiClient.delete(`${API_ENDPOINTS.WHITELIST}${identifier}`);
      toast.success(t('terminal.removedFromWhitelist'));
      refetch();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToRemoveFromWhitelist')));
    } finally {
      setRemovingWlId(null);
    }
  };

  const handleRemoveFromBlacklist = async (mac: Terminal) => {
    const identifier = mac.black_match_type === 'ip' ? mac.ip_address : mac.mac_address;
    setRemovingBlId(mac.id);
    try {
      await apiClient.delete(`${API_ENDPOINTS.BLACKLIST}${identifier}`);
      toast.success(t('terminal.removedFromBlacklist'));
      refetch();
      refetchBlacklist();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToRemoveFromBlacklist')));
    } finally {
      setRemovingBlId(null);
    }
  };

  const handleExport = () => {
    const headers = [t('terminal.mac'), t('terminal.ip'), t('common.status'), t('terminal.source'), t('terminal.sourceTag'), t('terminal.complianceStatus'), t('terminal.whitelistMatch'), t('terminal.firewallTag'), t('terminal.added'), t('terminal.comments')];
    const rows = allTerminals?.map((mac) => [
      mac.mac_address,
      mac.ip_address,
      STATUS_CONFIG[mac.status]?.label || mac.status,
      mac.source,
      mac.source_tag || '',
      COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.labelKey ? t(COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.labelKey) : 'Unknown',
      mac.wl_match_type || '',
      mac.firewall_tag || '',
      formatDate(mac.timestamp),
      mac.comments || ''
    ]) || [];

    downloadCSV(headers, rows, 'terminals');
  };

  const handleViewDetails = (mac: Terminal) => {
    setSelectedTerminal(mac);
    setShowModal(true);
  };

  const handleReset = () => {
    refetch();
    setSearchTerm('');
    setFilterStatus('all');
    setFilterCompliance('all');
    setStartDate('');
    setEndDate('');
    setCurrentPage(1);
  };

  const handleManualRefresh = () => {
    refetch();
    refetchBlacklist();
  };

  // Stats - use server total and current page data for compliance counts
  const totalTerminals = totalFromServer;
  const normalCount = allTerminals.filter((m) => (m.compliance_status || 'unknown') === 'compliant').length;
  const bypassCount = allTerminals.filter((m) => m.compliance_status === 'bypass').length;
  const blockedCount = allTerminals.filter((m) => m.compliance_status === 'non_compliant').length;
  const pendingCount = allTerminals.filter((m) => (m.compliance_status || 'unknown') === 'unknown').length;

  // Helper to get status label via i18n
  const getStatusLabel = (status: string): string => {
    const keyMap: Record<string, string> = {
      active: 'terminal.status.active',
      inactive: 'terminal.status.inactive',
      frozen: 'terminal.status.frozen',
      pending: 'terminal.status.pending',
      unfrozen: 'terminal.status.unfrozen',
      bypass: 'terminal.status.bypass',
    };
    return keyMap[status] ? t(keyMap[status]) : (STATUS_CONFIG[status]?.label || status);
  };

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {isLoading && !terminalsData ? (
        <PageSkeleton />
      ) : (
      <>
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('terminal.networkTerminals')}</h1>
          <p className="text-muted-foreground mt-1">{t('terminal.manageAndMonitor')}</p>
        </div>
        <PrimaryButton
          icon={Download}
          label={t('terminal.exportCSV')}
          variant="success"
          onClick={handleExport}
        />
      </div>

      {/* Search and Filter Section - Enhanced */}
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
        {/* Filter Bar */}
        {!filterCollapsed && (
        <>
        <div className="p-4 sm:p-5">
          <div className="flex flex-col xl:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <input
                type="text"
                placeholder={t('terminal.searchByMacOrIp')}
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
              {/* Status Filter */}
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <Filter className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={filterStatus}
                  onChange={(e) => {
                    setFilterStatus(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1.5 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[6rem]"
                >
                  <option value="all">{t('terminal.allStatus')}</option>
                  <option value="active">{t('terminal.status.active')}</option>
                  <option value="inactive">{t('terminal.status.inactive')}</option>
                  <option value="frozen">{t('terminal.status.frozen')}</option>
                  <option value="pending">{t('terminal.status.pending')}</option>
                  <option value="unfrozen">{t('terminal.status.unfrozen')}</option>
                  <option value="bypass">{t('terminal.status.bypass')}</option>
                </select>
              </div>

              {/* Compliance Filter */}
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <Shield className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={filterCompliance}
                  onChange={(e) => {
                    setFilterCompliance(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1.5 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[7rem]"
                >
                  <option value="all">{t('terminal.allCompliance')}</option>
                  <option value="compliant">{t('terminal.complianceStatusValues.compliant')}</option>
                  <option value="bypass">{t('terminal.complianceStatusValues.bypass')}</option>
                  <option value="non_compliant">{t('terminal.complianceStatusValues.non_compliant')}</option>
                  <option value="unknown">{t('terminal.complianceStatusValues.unknown')}</option>
                </select>
              </div>

              {/* Date Range Filter */}
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
                onClick={handleManualRefresh}
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

      {/* Stats - 4 compliance statuses + Total */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 mb-6">
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title={t('terminal.totalArpEntries')}>
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-muted-foreground transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-foreground">{totalTerminals}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('common.total')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-300 to-gray-500" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title={t('terminal.terminalCompliesPolicy')}>
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-muted-foreground transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-green-600">{normalCount}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('terminal.complianceStatusValues.compliant')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-green-400 to-green-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title={t('terminal.inWhitelistBypass')}>
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-muted-foreground transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-blue-600">{bypassCount}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('terminal.complianceStatusValues.bypass')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title={t('terminal.terminalBlockedByBlacklist')}>
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-muted-foreground transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-red-600">{blockedCount}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('terminal.complianceStatusValues.non_compliant')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-red-400 to-red-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title={t('terminal.complianceNotDetermined')}>
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-muted-foreground transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-yellow-600">{pendingCount}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('terminal.complianceStatusValues.unknown')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-yellow-400 to-yellow-600" />
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
                  {t('terminal.ip')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.status')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('terminal.source')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('terminal.compliance')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('terminal.firewallTag')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('terminal.added')}
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
              {allTerminals?.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <EmptyState
                      icon={Server}
                      title={t('terminal.noTerminalsFound')}
                      description={t('terminal.noTerminalsDescription')}
                    />
                  </td>
                </tr>
              ) : (
                (allTerminals || []).map((mac) => (
                  <tr key={mac.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 text-muted-foreground mr-2 flex-shrink-0" />
                        <span className="font-medium text-foreground font-mono text-sm">
                          {mac.mac_address}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-muted-foreground">
                      {mac.ip_address}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${STATUS_CONFIG[mac.status]?.className || 'bg-muted text-foreground'}`}
                      >
                        {getStatusLabel(mac.status)}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="text-sm text-muted-foreground capitalize">
                        {mac.source}{mac.source_tag ? <span className="text-muted-foreground"> ({mac.source_tag})</span> : ''}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.className || 'bg-muted text-foreground'}`}
                      >
                        {COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.labelKey ? t(COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.labelKey) : 'Unknown'}
                        {mac.compliance_status === 'bypass' && mac.wl_match_type && (
                          <span className="ml-1 text-xs opacity-75">({mac.wl_match_type.toUpperCase()})</span>
                        )}
                        {mac.compliance_status === 'non_compliant' && mac.black_match_type && (
                          <span className="ml-1 text-xs opacity-75">({mac.black_match_type.toUpperCase()})</span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      {mac.firewall_tag || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Clock className="h-4 w-4 mr-1.5 text-muted-foreground" />
                        {formatDate(mac.timestamp)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <p className="text-sm text-muted-foreground max-w-xs truncate">{mac.comments}</p>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={Eye}
                          variant="primary"
                          size="md"
                          title={t('terminal.viewDetails')}
                          onClick={() => handleViewDetails(mac)}
                        />
                        {mac.compliance_status === 'bypass' ? (
                          <IconButton
                            icon={Trash2}
                            variant="danger"
                            size="md"
                            title={t('terminal.removeFromWhitelist')}
                            loading={removingWlId === mac.id}
                            onClick={() => handleRemoveFromWhitelist(mac)}
                          />
                        ) : mac.compliance_status === 'non_compliant' && mac.black_match_type ? (
                          <IconButton
                            icon={Trash2}
                            variant="danger"
                            size="md"
                            title={t('terminal.removeFromBlacklist')}
                            loading={removingBlId === mac.id}
                            onClick={() => handleRemoveFromBlacklist(mac)}
                          />
                        ) : mac.compliance_status !== 'bypass' && mac.compliance_status !== 'non_compliant' ? (
                          <>
                            <IconButton
                              icon={Plus}
                              variant="success"
                              size="md"
                              title={t('terminal.addToWhitelist')}
                              loading={whitelistId === mac.id}
                              onClick={() => handleAddToWhitelist(mac)}
                            />
                            {mac.status !== 'frozen' ? (
                              <IconButton
                                icon={Shield}
                                variant="danger"
                                size="md"
                                title={t('terminal.blockTerminal')}
                                loading={blockingId === mac.id}
                                onClick={() => handleBlock(mac)}
                              />
                            ) : (
                              <IconButton
                                icon={ShieldOff}
                                variant="secondary"
                                size="md"
                                title={t('terminal.unblockTerminal')}
                                loading={blockingId === mac.id}
                                onClick={() => handleUnblock(mac)}
                              />
                            )}
                          </>
                        ) : null}
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
          totalItems={totalFromServer}
          variant="bottom"
        />
      </div>

      {/* Details Modal */}
      <Modal isOpen={showModal && !!selectedTerminal} onClose={() => setShowModal(false)} title={t('terminal.terminalDetails')} size="md">
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
              <Server className="h-6 w-6 text-blue-600" />
            </div>
            <p className="text-sm text-muted-foreground">ID: {selectedTerminal?.id}</p>
          </div>

          <div className="bg-background rounded-lg p-4">
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.mac')}</span>
                <span className="font-mono text-foreground">{selectedTerminal?.mac_address}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.ip')}</span>
                <span className="font-mono text-foreground">{selectedTerminal?.ip_address}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('common.status')}</span>
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${STATUS_CONFIG[selectedTerminal?.status || '']?.className || 'bg-muted text-foreground'}`}>
                  {getStatusLabel(selectedTerminal?.status || '')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.source')}</span>
                <span className="capitalize text-foreground">{selectedTerminal?.source}</span>
              </div>
              {selectedTerminal?.source_tag && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.sourceTag')}</span>
                <span className="text-foreground">{selectedTerminal.source_tag}</span>
              </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.complianceStatus')}</span>
                <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${COMPLIANCE_CONFIG[selectedTerminal?.compliance_status || 'unknown']?.className || 'bg-muted text-foreground'}`}>
                  {COMPLIANCE_CONFIG[selectedTerminal?.compliance_status || 'unknown']?.labelKey ? t(COMPLIANCE_CONFIG[selectedTerminal?.compliance_status || 'unknown']?.labelKey) : 'Unknown'}
                </span>
              </div>
              {selectedTerminal?.compliance_status === 'bypass' && selectedTerminal?.wl_match_type && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.whitelistMatch')}</span>
                <span className="text-foreground">{selectedTerminal.wl_match_type.toUpperCase()}</span>
              </div>
              )}
              {selectedTerminal?.compliance_status === 'non_compliant' && selectedTerminal?.black_match_type && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.blacklistMatch')}</span>
                <span className="text-foreground">{selectedTerminal.black_match_type.toUpperCase()}</span>
              </div>
              )}
              {selectedTerminal?.firewall_tag && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.firewallTag')}</span>
                <span className="text-foreground">{selectedTerminal.firewall_tag}</span>
              </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('terminal.addedDate')}</span>
                <span className="text-foreground">{formatDate(selectedTerminal?.timestamp)}</span>
              </div>
            </div>
          </div>

          <div>
            <span className="text-muted-foreground block mb-2">{t('terminal.comments')}</span>
            <p className="text-foreground bg-background rounded-lg p-4">
              {selectedTerminal?.comments || t('common.noComments')}
            </p>
          </div>

          <div className="flex gap-3">
            {selectedTerminal?.compliance_status === 'bypass' ? (
              <PrimaryButton
                icon={Trash2}
                label={t('terminal.removeFromWhitelist')}
                variant="danger"
                onClick={() => {
                  if (selectedTerminal) handleRemoveFromWhitelist(selectedTerminal);
                  setShowModal(false);
                }}
                className="flex-1"
              />
            ) : selectedTerminal?.compliance_status === 'non_compliant' && selectedTerminal?.black_match_type ? (
              <PrimaryButton
                icon={Trash2}
                label={t('terminal.removeFromBlacklist')}
                variant="danger"
                onClick={() => {
                  if (selectedTerminal) handleRemoveFromBlacklist(selectedTerminal);
                  setShowModal(false);
                }}
                className="flex-1"
              />
            ) : (
              <>
                <PrimaryButton
                  icon={Plus}
                  label={t('terminal.addToWhitelist')}
                  variant="success"
                  onClick={() => { if (selectedTerminal) handleAddToWhitelist(selectedTerminal); }}
                  className="flex-1"
                />
                {selectedTerminal?.status !== 'frozen' ? (
                  <PrimaryButton
                    icon={Shield}
                    label={t('terminal.blockTerminal')}
                    variant="danger"
                    onClick={() => { if (selectedTerminal) handleBlock(selectedTerminal); }}
                    className="flex-1"
                  />
                ) : (
                  <PrimaryButton
                    icon={ShieldOff}
                    label={t('terminal.unblockTerminal')}
                    variant="secondary"
                    onClick={() => { if (selectedTerminal) handleUnblock(selectedTerminal); }}
                    className="flex-1"
                  />
                )}
              </>
            )}
          </div>
        </div>
      </Modal>
      </>
      )}
    </div>
  );
};

export default Terminals;
