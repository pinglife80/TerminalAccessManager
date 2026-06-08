import React, { useState, useMemo } from 'react';
import { useTerminals, useBlacklist } from '@/hooks/useTerminalData';
import { Search, Filter, RefreshCw, Clock, Server, Shield, ShieldOff, Plus, Download, Eye, X, Info, ChevronDown, Trash2 } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { STATUS_CONFIG } from '@/lib/constants';

const COMPLIANCE_CONFIG: Record<string, { label: string; className: string }> = {
  compliant: { label: 'Normal', className: 'bg-green-100 text-green-800' },
  bypass: { label: 'Bypass', className: 'bg-blue-100 text-blue-800' },
  non_compliant: { label: 'Blocked', className: 'bg-red-100 text-red-800' },
  unknown: { label: 'Pending', className: 'bg-yellow-100 text-yellow-800' },
};

const REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 },
];

import { downloadCSV, formatDate } from '@/lib/utils';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { DateRangeFilter } from '@/components/DateRangeFilter';

const Terminals: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterCompliance, setFilterCompliance] = useState<string>('all');
  const [selectedTerminal, setSelectedTerminal] = useState<any>(null);
  const [showModal, setShowModal] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [autoRefresh, setAutoRefresh] = useState<number>(0);

  // Loading states for operations
  const [blockingId, setBlockingId] = useState<string | null>(null);
  const [whitelistId, setWhitelistId] = useState<string | null>(null);
  const [removingWlId, setRemovingWlId] = useState<string | null>(null);
  const [removingBlId, setRemovingBlId] = useState<string | null>(null);

  const { data: macAddresses, isLoading, refetch } = useTerminals({
    ip: searchTerm || undefined,
    mac: searchTerm || undefined,
    status: filterStatus !== 'all' ? filterStatus : undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    refetchInterval: autoRefresh || undefined,
  });
  const { data: blackListItems, refetch: refetchBlacklist } = useBlacklist();

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
    const macList = macAddresses || [];

    return macList.map((mac) => {
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

  const filteredAddresses = useMemo(() => {
    let result = allTerminals;
    if (filterStatus !== 'all') {
      result = result.filter((mac) => mac.status === filterStatus);
    }
    if (filterCompliance !== 'all') {
      result = result.filter((mac) => (mac.compliance_status || 'unknown') === filterCompliance);
    }
    return result;
  }, [allTerminals, filterStatus, filterCompliance]);

  const totalPages = Math.ceil(filteredAddresses.length / pageSize);
  const paginatedAddresses = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return filteredAddresses.slice(start, end);
  }, [filteredAddresses, currentPage, pageSize]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleBlock = async (mac: any) => {
    setBlockingId(mac.id);
    try {
      await apiClient.post(`/terminals/block/${mac.ip_address}`, null, {
        params: { mac_address: mac.mac_address, block_time: '30d' }
      });
      toast.success(`Blocked ${mac.ip_address}`);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to block');
    } finally {
      setBlockingId(null);
    }
  };

  const handleUnblock = async (mac: any) => {
    setBlockingId(mac.id);
    try {
      await apiClient.post(`/terminals/unblock/${mac.ip_address}`);
      toast.success(`Unblocked ${mac.ip_address}`);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to unblock');
    } finally {
      setBlockingId(null);
    }
  };

  const handleAddToWhitelist = async (mac: any) => {
    setWhitelistId(mac.id);
    try {
      const payload: Record<string, string> = {};
      if (mac.mac_address) payload['mac_address'] = mac.mac_address;
      if (mac.ip_address) payload['ip_address'] = mac.ip_address;
      await apiClient.post('/whitelist/', payload);
      toast.success(`Added ${mac.mac_address || mac.ip_address} to whitelist`);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to add to whitelist');
    } finally {
      setWhitelistId(null);
    }
  };

  const handleRemoveFromWhitelist = async (mac: any) => {
    const identifier = mac.wl_match_type === 'ip' ? mac.ip_address : mac.mac_address;
    setRemovingWlId(mac.id);
    try {
      await apiClient.delete(`/whitelist/${identifier}`);
      toast.success(`Removed ${identifier} from whitelist`);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to remove from whitelist');
    } finally {
      setRemovingWlId(null);
    }
  };

  const handleRemoveFromBlacklist = async (mac: any) => {
    const identifier = mac.black_match_type === 'ip' ? mac.ip_address : mac.mac_address;
    setRemovingBlId(mac.id);
    try {
      await apiClient.delete(`/blacklist/${identifier}`);
      toast.success(`Removed ${identifier} from blacklist`);
      refetch();
      refetchBlacklist();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to remove from blacklist');
    } finally {
      setRemovingBlId(null);
    }
  };

  const handleExport = () => {
    const headers = ['MAC Address', 'IP Address', 'Status', 'Source', 'Source Tag', 'Compliance Status', 'WL Match Type', 'Firewall Tag', 'Added', 'Comments'];
    const rows = filteredAddresses?.map((mac) => [
      mac.mac_address,
      mac.ip_address,
      STATUS_CONFIG[mac.status]?.label || mac.status,
      mac.source,
      mac.source_tag || '',
      COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.label || 'Unknown',
      mac.wl_match_type || '',
      mac.firewall_tag || '',
      formatDate(mac.timestamp),
      mac.comments || ''
    ]) || [];

    downloadCSV(headers, rows, 'terminals');
  };

  const handleViewDetails = (mac: any) => {
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

  // Stats
  const totalTerminals = filteredAddresses.length;
  const normalCount = filteredAddresses.filter((m) => (m.compliance_status || 'unknown') === 'compliant').length;
  const bypassCount = filteredAddresses.filter((m) => m.compliance_status === 'bypass').length;
  const blockedCount = filteredAddresses.filter((m) => m.compliance_status === 'non_compliant').length;
  const pendingCount = filteredAddresses.filter((m) => (m.compliance_status || 'unknown') === 'unknown').length;

  return (
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Network Terminals</h1>
          <p className="text-gray-600 mt-1">Manage and monitor all terminals on your network</p>
        </div>
        <PrimaryButton
          icon={Download}
          label="Export CSV"
          variant="success"
          onClick={handleExport}
        />
      </div>

      {/* Search and Filter Section - Enhanced */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden mb-6">
        {/* Section Header - Clickable */}
        <button
          onClick={() => setFilterCollapsed(!filterCollapsed)}
          className={`w-full px-5 py-4 flex items-center justify-between hover:bg-gray-50/50 transition-colors ${!filterCollapsed ? 'border-b border-gray-100' : ''}`}
        >
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-gray-500" />
            <h2 className="text-base font-semibold text-gray-900">Search & Filter</h2>
          </div>
          <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform duration-200 ${filterCollapsed ? '' : 'rotate-180'}`} />
        </button>
        {/* Filter Bar */}
        {!filterCollapsed && (
        <>
        <div className="p-4 sm:p-5">
          <div className="flex flex-col xl:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by MAC or IP address..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all"
              />
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Status Filter */}
              <div className="flex items-center gap-2 bg-gray-50 rounded-xl px-3 py-1.5">
                <Filter className="h-4 w-4 text-gray-500 flex-shrink-0" />
                <select
                  value={filterStatus}
                  onChange={(e) => {
                    setFilterStatus(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[6rem]"
                >
                  <option value="all">All Status</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="frozen">Blocked</option>
                  <option value="pending">Pending</option>
                  <option value="unfrozen">Unblocked</option>
                  <option value="bypass">Bypass</option>
                </select>
              </div>

              {/* Compliance Filter */}
              <div className="flex items-center gap-2 bg-gray-50 rounded-xl px-3 py-1.5">
                <Shield className="h-4 w-4 text-gray-500 flex-shrink-0" />
                <select
                  value={filterCompliance}
                  onChange={(e) => {
                    setFilterCompliance(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[7rem]"
                >
                  <option value="all">All Compliance</option>
                  <option value="compliant">Normal</option>
                  <option value="bypass">Bypass</option>
                  <option value="non_compliant">Blocked</option>
                  <option value="unknown">Pending</option>
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
                title="Refresh"
                onClick={handleManualRefresh}
              />

              {/* Auto Refresh Selector */}
              <div className="flex items-center gap-2 bg-gray-50 rounded-xl px-3 py-1.5">
                <Clock className="h-4 w-4 text-gray-500 flex-shrink-0" />
                <select
                  value={autoRefresh}
                  onChange={(e) => setAutoRefresh(Number(e.target.value))}
                  className="bg-transparent py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[4rem]"
                >
                  {REFRESH_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Reset Button */}
              <PrimaryButton
                icon={RefreshCw}
                label="Reset"
                variant="secondary"
                size="sm"
                onClick={handleReset}
              />
            </div>
          </div>
        </div>

        {/* Top Pagination - Info Row */}
        {totalPages > 1 && (
          <div className="px-4 sm:px-5 py-3 bg-gray-50 border-t border-gray-200">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={handlePageChange}
              pageSize={pageSize}
              onPageSizeChange={handlePageSizeChange}
              totalItems={filteredAddresses.length}
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
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title="Total ARP entries">
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-900">{totalTerminals}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Total</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-300 to-gray-500" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title="Terminal complies with security policy">
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-green-600">{normalCount}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Normal</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-green-400 to-green-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title="In whitelist, bypasses security checks">
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-blue-600">{bypassCount}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Bypass</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title="Terminal is blocked by blacklist">
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-red-600">{blockedCount}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Blocked</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-red-400 to-red-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden relative group">
          <div className="absolute top-2 right-2 z-10" title="Compliance status has not been determined">
            <Info className="h-3.5 w-3.5 text-gray-300 group-hover:text-gray-500 transition-colors cursor-help" />
          </div>
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-yellow-600">{pendingCount}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Pending</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-yellow-400 to-yellow-600" />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  MAC Address
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  IP Address
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Source
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Compliance
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Firewall Tag
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Added
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Comments
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={9}>
                    <LoadingState message="Loading terminals..." />
                  </td>
                </tr>
              ) : filteredAddresses?.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <EmptyState
                      icon={Server}
                      title="No Terminals Found"
                      description="Try adjusting your search filters or add terminals to the whitelist"
                    />
                  </td>
                </tr>
              ) : (
                (paginatedAddresses || []).map((mac) => (
                  <tr key={mac.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                        <span className="font-medium text-gray-900 font-mono text-sm">
                          {mac.mac_address}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-gray-600">
                      {mac.ip_address}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${STATUS_CONFIG[mac.status]?.className || 'bg-gray-100 text-gray-800'}`}
                      >
                        {STATUS_CONFIG[mac.status]?.label || mac.status}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="text-sm text-gray-600 capitalize">
                        {mac.source}{mac.source_tag ? <span className="text-gray-400"> ({mac.source_tag})</span> : ''}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.className || 'bg-gray-100 text-gray-800'}`}
                      >
                        {COMPLIANCE_CONFIG[mac.compliance_status || 'unknown']?.label || 'Unknown'}
                        {mac.compliance_status === 'bypass' && mac.wl_match_type && (
                          <span className="ml-1 text-xs opacity-75">({mac.wl_match_type.toUpperCase()})</span>
                        )}
                        {mac.compliance_status === 'non_compliant' && mac.black_match_type && (
                          <span className="ml-1 text-xs opacity-75">({mac.black_match_type.toUpperCase()})</span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {mac.firewall_tag || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-gray-600">
                        <Clock className="h-4 w-4 mr-1.5 text-gray-400" />
                        {formatDate(mac.timestamp)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <p className="text-sm text-gray-600 max-w-xs truncate">{mac.comments}</p>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <ButtonGroup>
                        <IconButton
                          icon={Eye}
                          variant="primary"
                          size="md"
                          title="View Details"
                          onClick={() => handleViewDetails(mac)}
                        />
                        {mac.compliance_status === 'bypass' ? (
                          <IconButton
                            icon={Trash2}
                            variant="danger"
                            size="md"
                            title="Remove from Whitelist"
                            loading={removingWlId === String(mac.id)}
                            onClick={() => handleRemoveFromWhitelist(mac)}
                          />
                        ) : mac.compliance_status === 'non_compliant' && mac.black_match_type ? (
                          <IconButton
                            icon={Trash2}
                            variant="danger"
                            size="md"
                            title="Remove from Blacklist"
                            loading={removingBlId === String(mac.id)}
                            onClick={() => handleRemoveFromBlacklist(mac)}
                          />
                        ) : mac.compliance_status !== 'bypass' && mac.compliance_status !== 'non_compliant' ? (
                          <>
                            <IconButton
                              icon={Plus}
                              variant="success"
                              size="md"
                              title="Add to Whitelist"
                              loading={whitelistId === String(mac.id)}
                              onClick={() => handleAddToWhitelist(mac)}
                            />
                            {mac.status !== 'frozen' ? (
                              <IconButton
                                icon={Shield}
                                variant="danger"
                                size="md"
                                title="Block Terminal"
                                loading={blockingId === String(mac.id)}
                                onClick={() => handleBlock(mac)}
                              />
                            ) : (
                              <IconButton
                                icon={ShieldOff}
                                variant="secondary"
                                size="md"
                                title="Unblock Terminal"
                                loading={blockingId === String(mac.id)}
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
          totalItems={filteredAddresses.length}
          variant="bottom"
        />
      </div>

      {/* Details Modal */}
      {showModal && selectedTerminal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                  <Server className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">Terminal Details</h2>
                  <p className="text-sm text-gray-500">ID: {selectedTerminal.id}</p>
                </div>
              </div>
              <IconButton
                icon={X}
                variant="ghost"
                size="md"
                onClick={() => setShowModal(false)}
              />
            </div>

            <div className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-500">MAC Address</span>
                    <span className="font-mono text-gray-900">{selectedTerminal.mac_address}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">IP Address</span>
                    <span className="font-mono text-gray-900">{selectedTerminal.ip_address}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Status</span>
                    <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${STATUS_CONFIG[selectedTerminal.status]?.className || 'bg-gray-100 text-gray-800'}`}>
                      {STATUS_CONFIG[selectedTerminal.status]?.label || selectedTerminal.status}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Source</span>
                    <span className="capitalize text-gray-900">{selectedTerminal.source}</span>
                  </div>
                  {selectedTerminal.source_tag && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Source Tag</span>
                    <span className="text-gray-900">{selectedTerminal.source_tag}</span>
                  </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-500">Compliance Status</span>
                    <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${COMPLIANCE_CONFIG[selectedTerminal.compliance_status || 'unknown']?.className || 'bg-gray-100 text-gray-800'}`}>
                      {COMPLIANCE_CONFIG[selectedTerminal.compliance_status || 'unknown']?.label || 'Unknown'}
                    </span>
                  </div>
                  {selectedTerminal.compliance_status === 'bypass' && selectedTerminal.wl_match_type && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Whitelist Match</span>
                    <span className="text-gray-900">{selectedTerminal.wl_match_type.toUpperCase()}</span>
                  </div>
                  )}
                  {selectedTerminal.compliance_status === 'non_compliant' && selectedTerminal.black_match_type && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Blacklist Match</span>
                    <span className="text-gray-900">{selectedTerminal.black_match_type.toUpperCase()}</span>
                  </div>
                  )}
                  {selectedTerminal.firewall_tag && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Firewall Tag</span>
                    <span className="text-gray-900">{selectedTerminal.firewall_tag}</span>
                  </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-500">Added Date</span>
                    <span className="text-gray-900">{formatDate(selectedTerminal.timestamp)}</span>
                  </div>
                </div>
              </div>

              <div>
                <span className="text-gray-500 block mb-2">Comments</span>
                <p className="text-gray-900 bg-gray-50 rounded-lg p-4">
                  {selectedTerminal.comments || 'No comments available'}
                </p>
              </div>

              <div className="flex gap-3">
                {selectedTerminal.compliance_status === 'bypass' ? (
                  <PrimaryButton
                    icon={Trash2}
                    label="Remove from Whitelist"
                    variant="danger"
                    onClick={() => {
                      handleRemoveFromWhitelist(selectedTerminal);
                      setShowModal(false);
                    }}
                    className="flex-1"
                  />
                ) : selectedTerminal.compliance_status === 'non_compliant' && selectedTerminal.black_match_type ? (
                  <PrimaryButton
                    icon={Trash2}
                    label="Remove from Blacklist"
                    variant="danger"
                    onClick={() => {
                      handleRemoveFromBlacklist(selectedTerminal);
                      setShowModal(false);
                    }}
                    className="flex-1"
                  />
                ) : (
                  <>
                    <PrimaryButton
                      icon={Plus}
                      label="Add to Whitelist"
                      variant="success"
                      onClick={() => handleAddToWhitelist(selectedTerminal)}
                      className="flex-1"
                    />
                    {selectedTerminal.status !== 'frozen' ? (
                      <PrimaryButton
                        icon={Shield}
                        label="Block Terminal"
                        variant="danger"
                        onClick={() => handleBlock(selectedTerminal)}
                        className="flex-1"
                      />
                    ) : (
                      <PrimaryButton
                        icon={ShieldOff}
                        label="Unblock Terminal"
                        variant="secondary"
                        onClick={() => handleUnblock(selectedTerminal)}
                        className="flex-1"
                      />
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Terminals;
