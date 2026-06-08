import React, { useState, useMemo } from 'react';
import { Search, Filter, Download, Clock, User, AlertCircle, X, FileText, RefreshCw, ChevronDown } from 'lucide-react';
import { useAuditLogs, AuditLog as AuditLogType } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { PrimaryButton, IconButton } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { DateRangeFilter } from '@/components/DateRangeFilter';
import { formatDate } from '@/lib/utils';

const AuditLogs: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterAction, setFilterAction] = useState<string>('all');
  const [selectedLog, setSelectedLog] = useState<AuditLogType | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const { data: logs, isLoading, refetch } = useAuditLogs({
    search: searchTerm || undefined,
    action: filterAction !== 'all' ? filterAction : undefined,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
  });

  const actions = [
    'all',
    'login',
    'logout',
    'add_whitelist',
    'remove_whitelist',
    'block_ip',
    'unblock_ip',
    'search_mac',
    'view_logs',
    'export_data',
    'update_mac',
  ];

  const actionLabels: Record<string, string> = {
    login: 'Logged In',
    logout: 'Logged Out',
    add_whitelist: 'Added to Whitelist',
    remove_whitelist: 'Removed from Whitelist',
    block_ip: 'Blocked IP',
    unblock_ip: 'Unblocked IP',
    search_mac: 'Searched MAC Address',
    view_logs: 'Viewed Logs',
    export_data: 'Exported Data',
    update_mac: 'Updated MAC',
  };

  const filteredLogs = logs || [];

  const totalPages = Math.ceil(filteredLogs.length / pageSize);
  const paginatedLogs = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return filteredLogs.slice(start, end);
  }, [filteredLogs, currentPage, pageSize]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (searchTerm) params.search = searchTerm;
      if (filterAction !== 'all') params.action = filterAction;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;

      const response = await apiClient.get('/logs/export', {
        params,
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to export logs');
    }
  };

  const handleReset = () => {
    refetch();
    setSearchTerm('');
    setFilterAction('all');
    setStartDate('');
    setEndDate('');
    setCurrentPage(1);
  };

  return (
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-600 mt-1">Track all system activities</p>
        </div>
        <PrimaryButton
          icon={Download}
          label="Export Logs"
          variant="success"
          onClick={handleExport}
        />
      </div>

      {/* Search and Filters */}
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
          <div className="flex flex-col lg:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by user, action, or IP..."
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
              {/* Action Filter */}
              <div className="flex items-center gap-2 bg-gray-50 rounded-xl px-3 py-1.5">
                <Filter className="h-4 w-4 text-gray-500 flex-shrink-0" />
                <select
                  value={filterAction}
                  onChange={(e) => {
                    setFilterAction(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent py-1 text-sm text-gray-700 focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[8rem]"
                >
                  {actions.map((action) => (
                    <option key={action} value={action}>
                      {actionLabels[action] || action}
                    </option>
                  ))}
                </select>
              </div>

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
              totalItems={filteredLogs.length}
              variant="top"
              showPageSizeSelector={false}
            />
          </div>
        )}
        </>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-900">{filteredLogs.length}</div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Total Logs</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-400 to-gray-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-blue-600">
              {new Set(filteredLogs.map((l) => l.username)).size || 0}
            </div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Unique Users</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-green-600">
              {new Set(filteredLogs.map((l) => l.action)).size || 0}
            </div>
            <div className="text-xs sm:text-sm text-gray-600 mt-1">Unique Actions</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-green-400 to-green-600" />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Time
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  User
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Action
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Resource
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  IP Address
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Details
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={6}>
                    <LoadingState message="Loading audit logs..." />
                  </td>
                </tr>
              ) : filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={FileText}
                      title="No Audit Logs Found"
                      description="Try adjusting your search filters"
                    />
                  </td>
                </tr>
              ) : (
                (paginatedLogs || []).map((log) => (
                  <tr key={log.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center text-sm text-gray-600">
                        <Clock className="h-4 w-4 mr-1.5 text-gray-400" />
                        {formatDate(log.timestamp)}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <User className="h-4 w-4 mr-1.5 text-gray-400" />
                        <span className="text-sm font-medium text-gray-900">
                          {log.username}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
                        {actionLabels[log.action] || log.action}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      <span className="capitalize">{log.resource_type || '-'}</span>
                      <span className="mx-1">/</span>
                      <span className="font-mono">{log.resource_id || '-'}</span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-gray-600">
                      {log.ip_address || '-'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <IconButton
                        icon={AlertCircle}
                        variant="primary"
                        size="sm"
                        title={log.details ? 'View Details' : 'No Details'}
                        onClick={() => {
                          setSelectedLog(log);
                          setShowModal(true);
                        }}
                      />
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
          totalItems={filteredLogs.length}
          variant="bottom"
        />
      </div>

      {/* Details Modal */}
      {showModal && selectedLog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Log Details</h2>
              <IconButton
                icon={X}
                variant="ghost"
                size="md"
                onClick={() => setShowModal(false)}
              />
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">Log ID</span>
                <span className="font-mono text-gray-900">{selectedLog.id}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">Timestamp</span>
                <span className="text-gray-900">{formatDate(selectedLog.timestamp)}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">User</span>
                <span className="text-gray-900">{selectedLog.username}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">Action</span>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                  {actionLabels[selectedLog.action] || selectedLog.action}
                </span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">Resource Type</span>
                <span className="text-gray-900 capitalize">{selectedLog.resource_type || '-'}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">Resource ID</span>
                <span className="font-mono text-gray-900">{selectedLog.resource_id || '-'}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-gray-200">
                <span className="text-gray-500">IP Address</span>
                <span className="font-mono text-gray-900">{selectedLog.ip_address || '-'}</span>
              </div>

              <div className="py-2">
                <span className="text-gray-500 block mb-2">Details</span>
                <div className="bg-gray-50 rounded-lg p-4 max-h-40 overflow-y-auto">
                  <p className="text-gray-900 whitespace-pre-wrap">{selectedLog.details || 'No details available'}</p>
                </div>
              </div>
            </div>

            <PrimaryButton
              label="Close"
              variant="secondary"
              onClick={() => setShowModal(false)}
              className="w-full mt-6"
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default AuditLogs;
