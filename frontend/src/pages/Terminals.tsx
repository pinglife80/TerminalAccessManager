import React, { useState, useMemo } from 'react';
import { useTerminals, useBlacklistCheck, useStats, useDataSources, Terminal } from '@/hooks/useTerminalData';
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

const REFRESH_OPTIONS: { labelKey: string; label?: string; value: number }[] = [
  { labelKey: 'common.off', value: 0 },
  { labelKey: '', label: '30s', value: 30000 },
  { labelKey: '', label: '1m', value: 60000 },
  { labelKey: '', label: '5m', value: 300000 },
  { labelKey: '', label: '10m', value: 600000 },
];

import { formatDate, useDebounce, getErrorMessage } from '@/lib/utils';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';
import { DateRangeFilter } from '@/components/DateRangeFilter';

/**
 * Determine action buttons for a terminal based on status matrix:
 * - compliant + unblocked: view only (no actions)
 * - compliant: view only (system auto-manages)
 * - bypass: view only (whitelist removal in Whitelist Management page)
 * - non_compliant + blocked: add to whitelist only (for exemption)
 * - non_compliant + unblocked: add to whitelist only
 * - unknown: add to whitelist only (for temporary exemption)
 *
 * Note: All manual block/unblock actions are intentionally disabled to preserve 
 * compliance auto-detection business loop. Whitelist removal is centralized in 
 * Whitelist Management page.
 */
function getTerminalActions(terminal: Terminal): {
  canBlock: boolean;
  canUnblock: boolean;
  canAddWhitelist: boolean;
  canRemoveWhitelist: boolean;
  canRemoveBlacklist: boolean;
} {
  const cs = terminal.compliance_status || 'unknown';
  const st = terminal.status;

  // compliant: view only (system auto-manages block/unblock)
  if (cs === 'compliant') {
    return { canBlock: false, canUnblock: false, canAddWhitelist: false, canRemoveWhitelist: false, canRemoveBlacklist: false };
  }
  // bypass: view only (whitelist removal in Whitelist Management page)
  if (cs === 'bypass') {
    return { canBlock: false, canUnblock: false, canAddWhitelist: false, canRemoveWhitelist: false, canRemoveBlacklist: false };
  }
  // non_compliant + blocked: add to whitelist only (for exemption)
  if (cs === 'non_compliant' && st === 'blocked') {
    return { canBlock: false, canUnblock: false, canAddWhitelist: true, canRemoveWhitelist: false, canRemoveBlacklist: false };
  }
  // non_compliant + unblocked: add to whitelist only
  if (cs === 'non_compliant' && st !== 'blocked') {
    return { canBlock: false, canUnblock: false, canAddWhitelist: true, canRemoveWhitelist: false, canRemoveBlacklist: false };
  }
  // unknown: add to whitelist only (for temporary exemption)
  if (cs === 'unknown') {
    return { canBlock: false, canUnblock: false, canAddWhitelist: true, canRemoveWhitelist: false, canRemoveBlacklist: false };
  }
  // fallback: view only
  return { canBlock: false, canUnblock: false, canAddWhitelist: false, canRemoveWhitelist: false, canRemoveBlacklist: false };
}

const Terminals: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterCompliance, setFilterCompliance] = useState<string>('all');
  const [filterSource, setFilterSource] = useState<string>('all');
  const [filterFirewallTag, setFilterFirewallTag] = useState<string>('all');
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
  const [whitelistId, setWhitelistId] = useState<number | null>(null);
  const [removingWlId, setRemovingWlId] = useState<number | null>(null);
  const [removingBlId, setRemovingBlId] = useState<number | null>(null);
  const [unblockingId, setUnblockingId] = useState<number | null>(null);

  // Confirmation dialogs - Whitelist Add
  const [showWlAddDialog, setShowWlAddDialog] = useState(false);
  const [wlAddTarget, setWlAddTarget] = useState<Terminal | null>(null);
  const [wlAddComment, setWlAddComment] = useState('');

  // Confirmation dialogs - Remove from Whitelist
  const [showWlRemoveConfirm, setShowWlRemoveConfirm] = useState(false);
  const [wlRemoveTarget, setWlRemoveTarget] = useState<Terminal | null>(null);

  // Whitelist add type selector
  const [wlAddType, setWlAddType] = useState<'mac_only' | 'single_ip' | 'both'>('both');

  // Confirmation dialogs - Unblock
  const [showUnblockConfirm, setShowUnblockConfirm] = useState(false);
  const [unblockTarget, setUnblockTarget] = useState<Terminal | null>(null);
  const [unblockComment, setUnblockComment] = useState('');

  // Confirmation dialogs - Remove from Blacklist
  const [showBlRemoveConfirm, setShowBlRemoveConfirm] = useState(false);
  const [blRemoveTarget, setBlRemoveTarget] = useState<Terminal | null>(null);
  const [blRemoveComment, setBlRemoveComment] = useState('');

  const { data: terminalsData, isLoading, refetch } = useTerminals({
    ip: debouncedSearch || undefined,
    mac: debouncedSearch || undefined,
    status: filterStatus !== 'all' ? filterStatus : undefined,
    compliance_status: filterCompliance !== 'all' ? filterCompliance : undefined,
    source_tag: filterSource !== 'all' ? filterSource : undefined,
    firewall_tag: filterFirewallTag !== 'all' ? filterFirewallTag : undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: (currentPage - 1) * pageSize,
    limit: pageSize,
    refetchInterval: autoRefresh || undefined,
  });
  // Extract items and total from paginated response
  const macAddresses = terminalsData?.items ?? [];
  const totalFromServer = terminalsData?.total ?? 0;

  // Batch-check blacklist status for current page terminals
  const checkMacAddresses = useMemo(
    () => macAddresses.map(t => t.mac_address).filter(Boolean),
    [macAddresses]
  );
  const checkIpAddresses = useMemo(
    () => macAddresses.map(t => t.ip_address).filter(Boolean),
    [macAddresses]
  );
  const { data: blackListCheckData, refetch: refetchBlacklist } = useBlacklistCheck({
    mac_addresses: checkMacAddresses,
    ip_addresses: checkIpAddresses,
  });

  const { data: stats } = useStats();
  const { data: dataSources } = useDataSources();

  const blackListItems = blackListCheckData ?? [];

  // Build blacklist lookup sets for MAC and IP matching
  const { blackMacSet, blackIpSet, blackEntryMap } = useMemo(() => {
    const macSet = new Set<string>();
    const ipSet = new Set<string>();
    const entryMap = new Map<string, string | null>();  // key -> firewall_tag

    (blackListItems || []).forEach((item) => {
      if (item.mac_address) {
        const key = item.mac_address.toLowerCase();
        macSet.add(key);
        entryMap.set(key, item.firewall_tag);
      }
      if (item.ip_address) {
        ipSet.add(item.ip_address);
        // MAC 优先：如果 IP 对应的 key 已存在（同一个条目同时有 MAC 和 IP），
        // 不覆盖；否则用 IP 作为 key
        if (!entryMap.has(item.ip_address)) {
          entryMap.set(item.ip_address, item.firewall_tag);
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

      if (macInBlacklist && ipInBlacklist) {
        blackMatchType = 'both';
      } else if (macInBlacklist) {
        blackMatchType = 'mac';
      } else if (ipInBlacklist) {
        blackMatchType = 'ip';
      }

      // 后端 compliance_status 是合规判定的唯一数据源，前端不再做二次覆盖。
      // 桥接虚拟机场景下同 MAC 不同 IP 的终端不应共享封堵状态，
      // 防火墙封堵基于 IP 而非 MAC，前端黑名单 MAC 匹配会导致宿主机被误判。
      const complianceStatus = mac.compliance_status || 'unknown';

      return {
        ...mac,
        compliance_status: complianceStatus,
        wl_match_type: mac.wl_match_type || null,
        firewall_tag: mac.firewall_tag || null,
        black_match_type: blackMatchType,
      };
    });
  }, [macAddresses, blackMacSet, blackIpSet, blackEntryMap]);

  // Extract unique source_tags from ARP data sources only
  const sourceTagOptions = useMemo(() => {
    const tags = new Set<string>();
    dataSources?.forEach((ds) => {
      if (ds.tag && (ds.type === 'arp_ssh' || ds.type === 'arp_api')) {
        tags.add(ds.tag);
      }
    });
    return Array.from(tags).sort();
  }, [dataSources]);

  const firewallTagOptions = useMemo(() => {
    const tags = new Set<string>();
    allTerminals.forEach((m) => { if (m.firewall_tag) tags.add(m.firewall_tag); });
    return Array.from(tags).sort();
  }, [allTerminals]);

  const totalPages = Math.ceil(totalFromServer / pageSize);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  // --- Action handlers with confirmation dialogs ---

  const handleUnblock = (mac: Terminal) => {
    setUnblockTarget(mac);
    setUnblockComment('');
    setShowUnblockConfirm(true);
  };

  const confirmUnblock = async () => {
    if (!unblockTarget) return;
    setUnblockingId(unblockTarget.id);
    try {
      const params: Record<string, string> = {};
      if (unblockComment.trim()) params['comments'] = unblockComment.trim();
      await apiClient.post(`${API_ENDPOINTS.TERMINALS_UNBLOCK}${unblockTarget.ip_address}`, null, {
        params
      });
      toast.success(t('terminal.unblocked'));
      refetch();
      refetchBlacklist();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToUnblock')));
    } finally {
      setUnblockingId(null);
      setShowUnblockConfirm(false);
      setUnblockTarget(null);
    }
  };

  const handleAddToWhitelist = (mac: Terminal) => {
    setWlAddTarget(mac);
    setWlAddComment('');
    setShowWlAddDialog(true);
  };

  const confirmAddToWhitelist = async () => {
    if (!wlAddTarget) return;
    if (!wlAddComment.trim()) {
      toast.error(t('terminal.whitelistCommentRequired'));
      return;
    }
    setWhitelistId(wlAddTarget.id);
    try {
      const payload: Record<string, string> = {};
      if (wlAddType !== 'single_ip' && wlAddTarget.mac_address) {
        payload['mac_address'] = wlAddTarget.mac_address;
      }
      if (wlAddType !== 'mac_only' && wlAddTarget.ip_address) {
        payload['ip_address'] = wlAddTarget.ip_address;
      }
      payload['comments'] = wlAddComment.trim();
      await apiClient.post(API_ENDPOINTS.WHITELIST, payload);
      toast.success(t('terminal.addedToWhitelist'));
      refetch();
      refetchBlacklist();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToAddToWhitelist')));
    } finally {
      setWhitelistId(null);
      setShowWlAddDialog(false);
      setWlAddTarget(null);
      setWlAddType('both');
    }
  };

  const handleRemoveFromWhitelist = (mac: Terminal) => {
    setWlRemoveTarget(mac);
    setShowWlRemoveConfirm(true);
  };

  const confirmRemoveFromWhitelist = async () => {
    if (!wlRemoveTarget) return;
    const identifier = wlRemoveTarget.wl_match_type === 'ip' ? wlRemoveTarget.ip_address : wlRemoveTarget.mac_address;
    setRemovingWlId(wlRemoveTarget.id);
    try {
      await apiClient.delete(`${API_ENDPOINTS.WHITELIST}${identifier}`);
      toast.success(t('terminal.removedFromWhitelist'));
      refetch();
      refetchBlacklist();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToRemoveFromWhitelist')));
    } finally {
      setRemovingWlId(null);
      setShowWlRemoveConfirm(false);
      setWlRemoveTarget(null);
    }
  };

  const handleRemoveFromBlacklist = (mac: Terminal) => {
    setBlRemoveTarget(mac);
    setBlRemoveComment('');
    setShowBlRemoveConfirm(true);
  };

  const confirmRemoveFromBlacklist = async () => {
    if (!blRemoveTarget) return;
    const identifier = blRemoveTarget.black_match_type === 'ip' ? blRemoveTarget.ip_address : blRemoveTarget.mac_address;
    setRemovingBlId(blRemoveTarget.id);
    try {
      await apiClient.delete(`${API_ENDPOINTS.BLACKLIST}${identifier}`);
      toast.success(t('terminal.removedFromBlacklist'));
      refetch();
      refetchBlacklist();
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToRemoveFromBlacklist')));
    } finally {
      setRemovingBlId(null);
      setShowBlRemoveConfirm(false);
      setBlRemoveTarget(null);
    }
  };

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (debouncedSearch) {
        params['ip'] = debouncedSearch;
        params['mac'] = debouncedSearch;
      }
      if (filterStatus !== 'all') params['status'] = filterStatus;
      if (filterCompliance !== 'all') params['compliance_status'] = filterCompliance;
      if (filterSource !== 'all') params['source_tag'] = filterSource;
      if (filterFirewallTag !== 'all') params['firewall_tag'] = filterFirewallTag;
      if (startDate) params['start_date'] = startDate;
      if (endDate) params['end_date'] = endDate;

      const response = await apiClient.get(API_ENDPOINTS.TERMINALS_EXPORT, {
        params,
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'terminals.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('terminal.failedToExport')));
    }
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
    setFilterSource('all');
    setFilterFirewallTag('all');
    setStartDate('');
    setEndDate('');
    setCurrentPage(1);
  };

  const handleManualRefresh = async () => {
    await refetch();
    refetchBlacklist();
    toast.success(t('terminal.dataRefreshed'));
  };

  // Stats - use server-side aggregation for compliance counts
  const totalTerminals = stats?.total ?? totalFromServer;
  const normalCount = stats?.compliant ?? allTerminals.filter((m) => (m.compliance_status || 'unknown') === 'compliant').length;
  const bypassCount = stats?.bypass ?? allTerminals.filter((m) => m.compliance_status === 'bypass').length;
  const blockedCount = stats?.non_compliant ?? allTerminals.filter((m) => m.compliance_status === 'non_compliant').length;
  const pendingCount = stats?.unknown ?? allTerminals.filter((m) => (m.compliance_status || 'unknown') === 'unknown').length;

  // Helper to get status label via i18n
  const getStatusLabel = (status: string): string => {
    const keyMap: Record<string, string> = {
      blocked: 'terminal.status.blocked',
      unblocked: 'terminal.status.unblocked',
      // Legacy values mapping
      frozen: 'terminal.status.blocked',
      unfrozen: 'terminal.status.unblocked',
      active: 'terminal.status.unblocked',
      inactive: 'terminal.status.unblocked',
      pending: 'terminal.status.unblocked',
      bypass: 'terminal.status.unblocked',
    };
    return keyMap[status] ? t(keyMap[status]) : (STATUS_CONFIG[status]?.label || status);
  };

  // Helper to render terminal info in confirmation dialogs
  const renderTerminalInfo = (terminal: Terminal | null) => {
    if (!terminal) return null;
    return (
      <div className="bg-background rounded-lg p-4 mb-4">
        <div className="space-y-2 text-sm">
          {terminal.mac_address && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('terminal.mac')}:</span>
              <span className="font-mono text-foreground">{terminal.mac_address}</span>
            </div>
          )}
          {terminal.ip_address && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('terminal.ip')}:</span>
              <span className="font-mono text-foreground">{terminal.ip_address}</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Helper to render comment input in confirmation dialogs
  const renderCommentInput = (value: string, onChange: (val: string) => void) => (
    <div>
      <label className="text-sm text-muted-foreground block mb-1">{t('terminal.actionCommentPlaceholder')}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('terminal.actionCommentPlaceholder')}
        className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
      />
    </div>
  );

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
                  <option value="blocked">{t('terminal.status.blocked')}</option>
                  <option value="unblocked">{t('terminal.status.unblocked')}</option>
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

              {/* Source Tag Filter */}
              {sourceTagOptions.length > 0 && (
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <Server className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={filterSource}
                  onChange={(e) => {
                    setFilterSource(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1.5 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[6rem]"
                >
                  <option value="all">{t('terminal.allSource')}</option>
                  {sourceTagOptions.map((tag) => (
                    <option key={tag} value={tag}>{tag}</option>
                  ))}
                </select>
              </div>
              )}

              {/* Firewall Tag Filter */}
              {firewallTagOptions.length > 0 && (
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <ShieldOff className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={filterFirewallTag}
                  onChange={(e) => {
                    setFilterFirewallTag(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1.5 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[6rem]"
                >
                  <option value="all">{t('terminal.allFirewallTag')}</option>
                  {firewallTagOptions.map((tag) => (
                    <option key={tag} value={tag}>{tag}</option>
                  ))}
                </select>
              </div>
              )}

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
                (allTerminals || []).map((mac) => {
                  const actions = getTerminalActions(mac);
                  return (
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
                        {mac.status === 'blocked' ? (mac.firewall_tag || '-') : '-'}
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center text-sm text-muted-foreground">
                          <Clock className="h-4 w-4 mr-1.5 text-muted-foreground" />
                          {formatDate(mac.timestamp)}
                        </div>
                      </td>
                      <td className="px-4 sm:px-6 py-4">
                        <p className="text-sm text-muted-foreground max-w-xs truncate" title={mac.comments || undefined}>{mac.comments}</p>
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
                          {actions.canAddWhitelist && (
                            <IconButton
                              icon={Plus}
                              variant="success"
                              size="md"
                              title={t('terminal.addToWhitelist')}
                              loading={whitelistId === mac.id}
                              onClick={() => handleAddToWhitelist(mac)}
                            />
                          )}
                          {actions.canRemoveWhitelist && (
                            <IconButton
                              icon={Trash2}
                              variant="danger"
                              size="md"
                              title={t('terminal.removeFromWhitelist')}
                              loading={removingWlId === mac.id}
                              onClick={() => handleRemoveFromWhitelist(mac)}
                            />
                          )}
                          {actions.canUnblock && (
                            <IconButton
                              icon={ShieldOff}
                              variant="secondary"
                              size="md"
                              title={t('terminal.unblockTerminal')}
                              loading={unblockingId === mac.id}
                              onClick={() => handleUnblock(mac)}
                            />
                          )}
                          {actions.canRemoveBlacklist && (
                            <IconButton
                              icon={Trash2}
                              variant="danger"
                              size="md"
                              title={t('terminal.removeFromBlacklist')}
                              loading={removingBlId === mac.id}
                              onClick={() => handleRemoveFromBlacklist(mac)}
                            />
                          )}
                        </ButtonGroup>
                      </td>
                    </tr>
                  );
                })
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
              {selectedTerminal?.status === 'blocked' && selectedTerminal?.firewall_tag && (
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

          {/* Action buttons in detail modal - same logic as table */}
          {(() => {
            if (!selectedTerminal) return null;
            const actions = getTerminalActions(selectedTerminal);
            const hasAnyAction = actions.canBlock || actions.canUnblock || actions.canAddWhitelist || actions.canRemoveWhitelist || actions.canRemoveBlacklist;
            if (!hasAnyAction) return null;
            return (
              <div className="flex gap-3">
                {actions.canAddWhitelist && (
                  <PrimaryButton
                    icon={Plus}
                    label={t('terminal.addToWhitelist')}
                    variant="success"
                    onClick={() => { if (selectedTerminal) handleAddToWhitelist(selectedTerminal); }}
                    className="flex-1"
                  />
                )}
                {actions.canRemoveWhitelist && (
                  <PrimaryButton
                    icon={Trash2}
                    label={t('terminal.removeFromWhitelist')}
                    variant="danger"
                    onClick={() => { if (selectedTerminal) handleRemoveFromWhitelist(selectedTerminal); }}
                    className="flex-1"
                  />
                )}
                {actions.canUnblock && (
                  <PrimaryButton
                    icon={ShieldOff}
                    label={t('terminal.unblockTerminal')}
                    variant="secondary"
                    onClick={() => { if (selectedTerminal) handleUnblock(selectedTerminal); }}
                    className="flex-1"
                  />
                )}
                {actions.canRemoveBlacklist && (
                  <PrimaryButton
                    icon={Trash2}
                    label={t('terminal.removeFromBlacklist')}
                    variant="danger"
                    onClick={() => { if (selectedTerminal) handleRemoveFromBlacklist(selectedTerminal); setShowModal(false); }}
                    className="flex-1"
                  />
                )}
              </div>
            );
          })()}
        </div>
      </Modal>

      {/* Add to Whitelist Dialog */}
      <Modal isOpen={showWlAddDialog && !!wlAddTarget} onClose={() => { setShowWlAddDialog(false); setWlAddTarget(null); }} title={t('terminal.addToWhitelistWithComment')} size="sm">
        <div className="space-y-4">
          {renderTerminalInfo(wlAddTarget)}
          <div>
            <label className="text-sm text-muted-foreground block mb-1">{t('whitelist.matchTypeSelector')}</label>
            <select
              value={wlAddType}
              onChange={(e) => setWlAddType(e.target.value as 'mac_only' | 'single_ip' | 'both')}
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="mac_only">{t('whitelist.matchTypeMacOnly')}</option>
              <option value="single_ip">{t('whitelist.matchTypeSingleIp')}</option>
              <option value="both">{t('whitelist.matchTypeBoth')}</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-muted-foreground block mb-1">{t('terminal.whitelistCommentPlaceholder')}</label>
            <input
              type="text"
              value={wlAddComment}
              onChange={(e) => setWlAddComment(e.target.value)}
              placeholder={t('terminal.whitelistCommentPlaceholder')}
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div className="flex gap-3">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => { setShowWlAddDialog(false); setWlAddTarget(null); }}
              className="flex-1"
            />
            <PrimaryButton
              icon={Plus}
              label={t('common.add')}
              variant="success"
              onClick={confirmAddToWhitelist}
              loading={whitelistId === wlAddTarget?.id}
              className="flex-1"
            />
          </div>
        </div>
      </Modal>

      {/* Remove from Whitelist Confirmation */}
      <Modal isOpen={showWlRemoveConfirm && !!wlRemoveTarget} onClose={() => { setShowWlRemoveConfirm(false); setWlRemoveTarget(null); }} title={t('terminal.confirmRemoveFromWhitelist')} size="sm">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center">
            <Trash2 className="h-6 w-6 text-yellow-600" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('terminal.confirmRemoveFromWhitelistMsg')}</p>
          </div>
        </div>
        {renderTerminalInfo(wlRemoveTarget)}
        <div className="flex gap-3">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => { setShowWlRemoveConfirm(false); setWlRemoveTarget(null); }}
            className="flex-1"
          />
          <PrimaryButton
            icon={Trash2}
            label={t('common.delete')}
            variant="danger"
            onClick={confirmRemoveFromWhitelist}
            loading={removingWlId === wlRemoveTarget?.id}
            className="flex-1"
          />
        </div>
      </Modal>

      {/* Unblock Confirmation Dialog */}
      <Modal isOpen={showUnblockConfirm && !!unblockTarget} onClose={() => { setShowUnblockConfirm(false); setUnblockTarget(null); }} title={t('terminal.confirmUnblock')} size="sm">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
            <ShieldOff className="h-6 w-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('terminal.confirmUnblockMsg')}</p>
          </div>
        </div>
        {renderTerminalInfo(unblockTarget)}
        {renderCommentInput(unblockComment, setUnblockComment)}
        <div className="flex gap-3 mt-4">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => { setShowUnblockConfirm(false); setUnblockTarget(null); }}
            className="flex-1"
          />
          <PrimaryButton
            icon={ShieldOff}
            label={t('terminal.unblockTerminal')}
            variant="secondary"
            onClick={confirmUnblock}
            loading={unblockingId === unblockTarget?.id}
            className="flex-1"
          />
        </div>
      </Modal>

      {/* Remove from Blacklist Confirmation Dialog */}
      <Modal isOpen={showBlRemoveConfirm && !!blRemoveTarget} onClose={() => { setShowBlRemoveConfirm(false); setBlRemoveTarget(null); }} title={t('terminal.confirmRemoveFromBlacklist')} size="sm">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center">
            <Trash2 className="h-6 w-6 text-yellow-600" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t('terminal.confirmRemoveFromBlacklistMsg')}</p>
          </div>
        </div>
        {renderTerminalInfo(blRemoveTarget)}
        {renderCommentInput(blRemoveComment, setBlRemoveComment)}
        <div className="flex gap-3 mt-4">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={() => { setShowBlRemoveConfirm(false); setBlRemoveTarget(null); }}
            className="flex-1"
          />
          <PrimaryButton
            icon={Trash2}
            label={t('terminal.removeFromBlacklist')}
            variant="danger"
            onClick={confirmRemoveFromBlacklist}
            loading={removingBlId === blRemoveTarget?.id}
            className="flex-1"
          />
        </div>
      </Modal>
      </>
      )}
    </div>
  );
};

export default Terminals;
