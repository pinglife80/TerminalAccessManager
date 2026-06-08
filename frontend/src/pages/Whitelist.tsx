import React, { useState, useMemo } from 'react';
import { useWhitelist, WhitelistEntry } from '@/hooks/useTerminalData';
import { Search, Plus, Trash2, User, Server, Globe, RefreshCw, Download, Clock, ChevronDown, Eye, X } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { PrimaryButton, IconButton } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { DateRangeFilter } from '@/components/DateRangeFilter';
import { normalizeMacAddress, isValidMacAddress, isValidCidrOrRange, formatDate, downloadCSV } from '@/lib/utils';

const Whitelist: React.FC = () => {
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

  const { data: whitelist, isLoading, refetch } = useWhitelist({
    search: searchTerm || undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
  });

  const filteredWhitelist = whitelist || [];

  const totalPages = useMemo(() => Math.ceil(filteredWhitelist.length / pageSize), [filteredWhitelist, pageSize]);
  const paginatedWhitelist = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return filteredWhitelist.slice(start, end);
  }, [filteredWhitelist, currentPage, pageSize]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleAddWhitelist = async () => {
    if (!macAddress.trim() && !ipAddress.trim()) {
      toast.error('Please enter at least a MAC address or IP address');
      return;
    }

    if (macAddress && !isValidMacAddress(macAddress)) {
      toast.error(
        'Invalid MAC address format. Supported formats: AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABBCCDDEEFF'
      );
      return;
    }

    if (ipAddress && !isValidCidrOrRange(ipAddress)) {
      toast.error('Invalid IP address format. Supported: single IP (192.168.1.100), CIDR (192.168.1.0/24), or range (192.168.1.1-100/24)');
      return;
    }

    // Comments is required
    if (!comments.trim()) {
      setCommentsError('Comments is required');
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

      const response = await apiClient.post('/whitelist/', payload);

      const result = response.data;
      if (result.success) {
        let successMsg = '';
        if (result.added > 0) {
          successMsg = `${result.added} terminal(s) added successfully`;
        }
        if (result.skipped > 0) {
          successMsg += ` (${result.skipped} skipped)`;
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
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to add to whitelist');
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

  const handleExport = () => {
    const headers = ['MAC Address', 'IP Pattern', 'Pattern Type', 'Added By', 'Added Date', 'Comments'];
    const rows = filteredWhitelist?.map((item) => [
      item.mac_address || '-',
      item.ip_pattern || '-',
      item.pattern_type || '-',
      item.added_by,
      formatDate(item.created_at),
      item.comments || ''
    ]) || [];

    downloadCSV(headers, rows, 'whitelist');
  };

  const handleRemoveWhitelist = (identifier: string | null, ipPattern?: string | null) => {
    setDeleteIdentifier(identifier || '');
    setDeleteIpPattern(ipPattern || '');
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    const identifier = deleteIdentifier || deleteIpPattern;
    const displayText = deleteIpPattern ? `${deleteIdentifier || deleteIpPattern}` : deleteIdentifier;

    setIsDeleting(true);
    try {
      await apiClient.delete(`/whitelist/${identifier}`);
      toast.success(`Removed ${displayText} from whitelist`);
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to remove from whitelist');
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
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Whitelist Terminals</h1>
          <p className="text-gray-600 mt-1">Manage trusted network terminals (MAC + IP addresses)</p>
        </div>
        <div className="flex gap-2">
          <PrimaryButton
            icon={Download}
            label="Export"
            variant="success"
            onClick={handleExport}
          />
          <PrimaryButton
            icon={Plus}
            label="Add Terminal"
            variant="success"
            onClick={() => setShowAddModal(true)}
          />
        </div>
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
                placeholder="Search by MAC address, IP pattern, or description..."
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
              totalItems={filteredWhitelist.length}
              variant="top"
              showPageSizeSelector={false}
            />
          </div>
        )}
        </>
        )}
      </div>

      {/* Stats */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-5 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-shrink-0 w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
            <Globe className="h-6 w-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Total Entries</p>
            <p className="text-2xl sm:text-3xl font-bold text-gray-900">{filteredWhitelist.length}</p>
          </div>
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
                  IP Pattern
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Added By
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Added Date
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
                  <td colSpan={7}>
                    <LoadingState message="Loading whitelist..." />
                  </td>
                </tr>
              ) : filteredWhitelist?.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={Server}
                      title="No Whitelist Entries"
                      description="Add trusted terminals to bypass security checks"
                      action={{
                        label: "Add Terminal",
                        onClick: () => setShowAddModal(true)
                      }}
                    />
                  </td>
                </tr>
              ) : (
                (paginatedWhitelist || []).map((item) => (
                  <tr key={item.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm font-medium text-gray-900">
                      {item.mac_address || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-gray-600">
                      {item.ip_pattern || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      {item.pattern_type === 'single_ip' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">Single IP</span>
                      )}
                      {item.pattern_type === 'cidr' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">CIDR</span>
                      )}
                      {item.pattern_type === 'ip_range' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">IP Range</span>
                      )}
                      {item.pattern_type === 'mac_only' && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">MAC Only</span>
                      )}
                      {!item.pattern_type && (
                        <span className="text-sm text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-gray-600">
                        <User className="h-4 w-4 mr-1.5 text-gray-400" />
                        {item.added_by}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-gray-600">
                        <Clock className="h-4 w-4 mr-1.5 text-gray-400" />
                        {formatDate(item.created_at)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <p className="text-sm text-gray-600 max-w-xs truncate">{item.comments}</p>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <IconButton
                          icon={Eye}
                          variant="primary"
                          size="md"
                          title="View Details"
                          onClick={() => handleViewDetails(item)}
                        />
                        <IconButton
                          icon={Trash2}
                          variant="danger"
                          size="md"
                          title="Remove from whitelist"
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
          totalItems={filteredWhitelist.length}
          variant="bottom"
        />
      </div>

      {/* Add Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Add Allowed Terminal</h2>
            <p className="text-sm text-gray-500 mb-6">Enter MAC address, IP address/range, or both</p>

            {/* Format Help - Always visible */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <p className="text-sm font-medium text-blue-800 mb-2">Format Tips:</p>
              <div className="grid grid-cols-2 gap-2 text-xs text-blue-700">
                <div>
                  <p className="font-medium">MAC Address:</p>
                  <ul className="space-y-0.5 ml-2">
                    <li>• <code className="bg-blue-100 px-1 rounded">AA:BB:CC:DD:EE:FF</code></li>
                    <li>• <code className="bg-blue-100 px-1 rounded">AA-BB-CC-DD-EE-FF</code></li>
                    <li>• <code className="bg-blue-100 px-1 rounded">AABBCCDDEEFF</code></li>
                  </ul>
                </div>
                <div>
                  <p className="font-medium">IP Address/Range:</p>
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
                <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                  <Server className="h-4 w-4 text-gray-400" />
                  MAC Address <span className="text-gray-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="00:11:22:33:44:55"
                  value={macAddress}
                  onChange={(e) => setMacAddress(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                />
                {macAddress && isValidMacAddress(macAddress) && (
                  <p className="mt-2 text-sm text-green-600 flex items-center gap-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    Normalized: {normalizeMacAddress(macAddress)}
                  </p>
                )}
              </div>

              {/* IP Address Field */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                  <Globe className="h-4 w-4 text-gray-400" />
                  IP Address/Range <span className="text-gray-400 font-normal">(Optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="192.168.1.1, 192.168.1.0/24, 10.0.1.1-100"
                  value={ipAddress}
                  onChange={(e) => setIpAddress(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                />
                <p className="mt-1.5 text-xs text-gray-500">
                  Supports: Single IP / CIDR / IP Range
                </p>
              </div>

              {/* Comments - Required */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Comments <span className="text-red-500">*</span>
                </label>
                <textarea
                  placeholder="Required: describe this entry..."
                  value={comments}
                  onChange={(e) => {
                    setComments(e.target.value);
                    if (e.target.value.trim()) {
                      setCommentsError('');
                    }
                  }}
                  rows={2}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none text-sm ${
                    commentsError ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
                {commentsError && <p className="text-red-600 text-xs mt-1">{commentsError}</p>}
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <PrimaryButton
                  label="Cancel"
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
                  label="Add"
                  variant="success"
                  onClick={handleAddWhitelist}
                  loading={isAdding}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                <Trash2 className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Remove from Whitelist</h2>
                <p className="text-sm text-gray-500">This action cannot be undone</p>
              </div>
            </div>

            <p className="text-gray-700 mb-6">
              Are you sure you want to remove <span className="font-mono font-medium">{deleteIdentifier || deleteIpPattern}</span> from the whitelist?
            </p>

            <div className="flex gap-3">
              <PrimaryButton
                label="Cancel"
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
                label="Remove"
                variant="danger"
                onClick={confirmDelete}
                loading={isDeleting}
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
                <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                  <Globe className="h-6 w-6 text-green-600" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">Whitelist Entry Details</h2>
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
                  {selectedEntry.ip_pattern && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">IP Pattern</span>
                      <span className="font-mono text-gray-900">{selectedEntry.ip_pattern}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-500">Pattern Type</span>
                    <span className="text-gray-900 capitalize">{selectedEntry.pattern_type?.replace('_', ' ') || '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Added By</span>
                    <span className="text-gray-900">{selectedEntry.added_by}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Added Date</span>
                    <span className="text-gray-900">{formatDate(selectedEntry.created_at)}</span>
                  </div>
                </div>
              </div>

              <div>
                <span className="text-gray-500 block mb-2">Comments</span>
                <p className="text-gray-900 bg-gray-50 rounded-lg p-4">
                  {selectedEntry.comments || 'No comments available'}
                </p>
              </div>

              <PrimaryButton
                icon={Trash2}
                label="Remove from Whitelist"
                variant="danger"
                onClick={() => {
                  handleRemoveWhitelist(selectedEntry.mac_address, selectedEntry.ip_pattern);
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

export default Whitelist;
