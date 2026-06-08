import React, { useState, useMemo } from 'react';
import { Search, Trash2, AlertTriangle, Clock, Server, X, Download, Eye, Shield, RefreshCw, ChevronDown } from 'lucide-react';
import { useBlacklist, BlacklistEntry, useDataSources } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { DateRangeFilter } from '@/components/DateRangeFilter';
import { downloadCSV, formatDate, normalizeMacAddress, isValidMacAddress, isValidCidrOrRange } from '@/lib/utils';

const REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '5m', value: 300000 },
  { label: '10m', value: 600000 },
];

const Blacklist: React.FC = () => {
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

  const { data: blacklist, isLoading, refetch } = useBlacklist({
    search: searchTerm || undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    refetchInterval: autoRefresh || undefined,
  });

  const { data: dataSources } = useDataSources();

  const firewallOptions = useMemo(
    () => (dataSources || []).filter((ds) => ds.type === 'sangfor' && ds.enabled),
    [dataSources],
  );

  const filteredBlacklist = blacklist || [];

  const totalPages = Math.ceil(filteredBlacklist.length / pageSize);
  const paginatedBlacklist = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return filteredBlacklist.slice(start, end);
  }, [filteredBlacklist, currentPage, pageSize]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleAddBlacklist = async () => {
    if (!newEntry.mac_address && !newEntry.ip_address) {
      toast.error('Please enter at least a MAC address or IP address');
      return;
    }
    if (!newEntry.reason) {
      toast.error('Please select a reason for blocking');
      return;
    }

    // Validate MAC address format
    if (newEntry.mac_address && !isValidMacAddress(newEntry.mac_address)) {
      setMacError('Invalid MAC address format. Supported: AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABBCCDDEEFF');
      return;
    }
    setMacError('');

    // Validate IP address format
    if (newEntry.ip_address && !isValidCidrOrRange(newEntry.ip_address)) {
      setIpError('Invalid IP address format. Supported: 192.168.1.100, 192.168.1.0/24, 192.168.1.1-100');
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

      await apiClient.post('/blacklist/', payload);
      toast.success('Terminal blocked successfully');
      setNewEntry({ mac_address: '', ip_address: '', reason: '', block_time: '30d', firewall_tag: '' });
      setShowAddModal(false);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to block terminal');
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
      await apiClient.delete(`/blacklist/${identifier}`);
      toast.success(`Unblocked ${identifier}`);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to unblock terminal');
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
    const headers = ['MAC Address', 'IP Address', 'Reason', 'Blocked By', 'Firewall Tag', 'Block Type', 'Auto Unblocked', 'Blocked At', 'Expires At'];
    const rows = filteredBlacklist?.map((item) => [
      item.mac_address || '',
      item.ip_address || '',
      item.reason,
      item.blocked_by,
      item.firewall_tag || '',
      item.is_auto_blocked ? 'Auto' : 'Manual',
      item.auto_unblocked ? 'Yes' : 'No',
      formatDate(item.blocked_at),
      formatDate(item.expires_at)
    ]) || [];

    downloadCSV(headers, rows, 'blocked-terminals');
  };

  const isExpired = (expiresAt: string | null) => expiresAt ? new Date(expiresAt) < new Date() : false;

  return (
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Blocked Terminals</h1>
          <p className="text-gray-600 mt-1">Manage blocked network terminals</p>
        </div>
        <ButtonGroup>
          <PrimaryButton
            icon={Download}
            label="Export"
            variant="success"
            onClick={handleExport}
          />
          <PrimaryButton
            icon={Shield}
            label="Block Terminal"
            variant="danger"
            onClick={() => setShowAddModal(true)}
          />
        </ButtonGroup>
      </div>

      {/* Search and Filter */}
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
                title="Refresh"
                onClick={() => refetch()}
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
              totalItems={filteredBlacklist.length}
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
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-red-600">{filteredBlacklist.length}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Blocked Devices</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-red-400 to-red-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-orange-600">
              {filteredBlacklist?.filter((b) => b.is_auto_blocked).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Auto Blocked</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-orange-400 to-orange-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-blue-600">
              {filteredBlacklist?.filter((b) => !b.is_auto_blocked).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Manual Blocked</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-amber-600">
              {filteredBlacklist?.filter((b) => isExpired(b.expires_at)).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Expired Blocks</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-amber-400 to-amber-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-600">
              {filteredBlacklist?.filter((b) => !isExpired(b.expires_at)).length || 0}
            </div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Active Blocks</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-400 to-gray-600" />
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
                  Reason
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Blocked By
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Firewall
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Blocked At
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Expires
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
                    <LoadingState message="Loading blocked terminals..." />
                  </td>
                </tr>
              ) : filteredBlacklist?.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <EmptyState
                      icon={Shield}
                      title="No Blocked Terminals"
                      description="No terminals are currently blocked"
                    />
                  </td>
                </tr>
              ) : (
                (paginatedBlacklist || []).map((item) => (
                  <tr
                    key={item.id}
                    className={`hover:bg-blue-50/30 transition-colors ${
                      isExpired(item.expires_at) ? 'opacity-50' : ''
                    } ${item.is_auto_blocked ? 'bg-orange-50/30' : ''}`}
                  >
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                        <span className="font-mono text-sm font-medium text-gray-900">
                          {item.mac_address}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-gray-600">
                      {item.ip_address}
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <div className="flex items-center">
                        <AlertTriangle className="h-4 w-4 text-red-400 mr-2 flex-shrink-0" />
                        <span className="text-sm text-gray-600">{item.reason}</span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {item.is_auto_blocked ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                          Auto
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          Manual
                        </span>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {item.blocked_by}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {item.firewall_tag || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-gray-600">
                        <Clock className="h-4 w-4 mr-1.5 text-gray-400" />
                        {formatDate(item.blocked_at)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center text-sm ${
                          isExpired(item.expires_at) ? 'text-gray-400 line-through' : 'text-gray-600'
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
                          title="View Details"
                          onClick={() => handleViewDetails(item)}
                        />
                        <IconButton
                          icon={Trash2}
                          variant="success"
                          size="md"
                          title="Unblock Terminal"
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
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Block Terminal</h2>
            <p className="text-sm text-gray-500 mb-6">Enter MAC address, IP address, or both</p>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  MAC Address <span className="text-gray-400 font-normal">(Optional)</span>
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
                    macError ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
                {macError && <p className="text-red-600 text-xs mt-1">{macError}</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  IP Address <span className="text-gray-400 font-normal">(Optional)</span>
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
                    ipError ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
                {ipError && <p className="text-red-600 text-xs mt-1">{ipError}</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Reason
                </label>
                <select
                  value={newEntry.reason}
                  onChange={(e) => setNewEntry({ ...newEntry, reason: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="">Select reason</option>
                  <option value="Unauthorized access attempt">Unauthorized access attempt</option>
                  <option value="Security violation">Security violation</option>
                  <option value="Malware detected">Malware detected</option>
                  <option value="Policy violation">Policy violation</option>
                  <option value="Suspicious activity">Suspicious activity</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Block Duration
                </label>
                <select
                  value={newEntry.block_time}
                  onChange={(e) => setNewEntry({ ...newEntry, block_time: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="30m">30 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="7d">7 days</option>
                  <option value="15d">15 days</option>
                  <option value="30d">30 days</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Firewall <span className="text-gray-400 font-normal">(Optional)</span>
                </label>
                <select
                  value={newEntry.firewall_tag}
                  onChange={(e) => setNewEntry({ ...newEntry, firewall_tag: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="">Default Firewall</option>
                  {firewallOptions.map((ds) => (
                    <option key={ds.id} value={ds.tag}>
                      {ds.tag} ({ds.name})
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3 pt-2">
                <PrimaryButton
                  label="Cancel"
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
                  label="Block"
                  variant="danger"
                  onClick={handleAddBlacklist}
                  loading={isAdding}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && deleteEntry && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                <Trash2 className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Confirm Unblock</h2>
                <p className="text-sm text-gray-500">Are you sure you want to unblock this terminal?</p>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-4 mb-6">
              <div className="space-y-2 text-sm">
                {deleteEntry.mac_address && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">MAC Address:</span>
                    <span className="font-mono text-gray-900">{deleteEntry.mac_address}</span>
                  </div>
                )}
                {deleteEntry.ip_address && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">IP Address:</span>
                    <span className="font-mono text-gray-900">{deleteEntry.ip_address}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-gray-500">Reason:</span>
                  <span className="text-gray-900">{deleteEntry.reason}</span>
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
                label="Unblock"
                variant="success"
                onClick={confirmUnblock}
                loading={isUnblocking}
                className="flex-1"
              />
            </div>
          </div>
        </div>
      )}

      {/* Details Modal */}
      {showDetailsModal && selectedEntry && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                  <AlertTriangle className="h-6 w-6 text-red-600" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">Blocked Terminal Details</h2>
                  <p className="text-sm text-gray-500">ID: {selectedEntry.id}</p>
                </div>
              </div>
              <IconButton
                icon={X}
                variant="ghost"
                size="md"
                onClick={() => {
                  setShowDetailsModal(false);
                  setSelectedEntry(null);
                }}
              />
            </div>

            <div className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="space-y-3">
                  {selectedEntry.mac_address && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">MAC Address</span>
                      <span className="font-mono text-gray-900">{selectedEntry.mac_address}</span>
                    </div>
                  )}
                  {selectedEntry.ip_address && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">IP Address</span>
                      <span className="font-mono text-gray-900">{selectedEntry.ip_address}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-500">Reason</span>
                    <span className="text-gray-900">{selectedEntry.reason}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Blocked By</span>
                    <span className="text-gray-900">{selectedEntry.blocked_by}</span>
                  </div>
                  {selectedEntry.source_tag && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Source Tag</span>
                      <span className="text-gray-900">{selectedEntry.source_tag}</span>
                    </div>
                  )}
                  {selectedEntry.firewall_tag && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Firewall Tag</span>
                      <span className="text-gray-900">{selectedEntry.firewall_tag}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-500">Block Type</span>
                    <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${selectedEntry.is_auto_blocked ? 'bg-orange-100 text-orange-800' : 'bg-blue-100 text-blue-800'}`}>
                      {selectedEntry.is_auto_blocked ? 'Auto' : 'Manual'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Auto Unblocked</span>
                    <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${selectedEntry.auto_unblocked ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                      {selectedEntry.auto_unblocked ? 'Yes' : 'No'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Blocked At</span>
                    <span className="text-gray-900">{formatDate(selectedEntry.blocked_at)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Expires</span>
                    <span className={`${isExpired(selectedEntry.expires_at) ? 'text-gray-400 line-through' : 'text-gray-900'}`}>
                      {formatDate(selectedEntry.expires_at)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Status</span>
                    <span className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${isExpired(selectedEntry.expires_at) ? 'bg-gray-100 text-gray-800' : 'bg-red-100 text-red-800'}`}>
                      {isExpired(selectedEntry.expires_at) ? 'Expired' : 'Active'}
                    </span>
                  </div>
                </div>
              </div>

              <PrimaryButton
                icon={Trash2}
                label="Unblock Terminal"
                variant="success"
                onClick={() => {
                  handleRemoveBlacklist(selectedEntry);
                  setShowDetailsModal(false);
                  setSelectedEntry(null);
                }}
                className="w-full"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Blacklist;
