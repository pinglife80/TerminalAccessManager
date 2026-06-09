import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Filter, Download, Clock, User, AlertCircle, X, FileText, RefreshCw, ChevronDown } from 'lucide-react';
import { useAuditLogs, AuditLog as AuditLogType } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { API_ENDPOINTS } from '@/lib/constants';
import { PrimaryButton, IconButton } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { DateRangeFilter } from '@/components/DateRangeFilter';
import { formatDate, useDebounce, getErrorMessage } from '@/lib/utils';

const ACTION_CATEGORIES = [
  {
    key: 'all',
    labelKey: 'auditLogs.categories.all',
    actions: [] as string[],
  },
  {
    key: 'auth',
    labelKey: 'auditLogs.categories.auth',
    actions: ['login', 'logout'],
  },
  {
    key: 'terminal',
    labelKey: 'auditLogs.categories.terminal',
    actions: ['block_terminal', 'unblock_terminal'],
  },
  {
    key: 'whitelist',
    labelKey: 'auditLogs.categories.whitelist',
    actions: ['add_whitelist', 'remove_whitelist'],
  },
  {
    key: 'blacklist',
    labelKey: 'auditLogs.categories.blacklist',
    actions: ['block_blacklist', 'unblock_blacklist', 'cleanup_expired'],
  },
  {
    key: 'datasource',
    labelKey: 'auditLogs.categories.datasource',
    actions: ['create_datasource', 'update_datasource', 'delete_datasource', 'test_datasource', 'sync_datasource'],
  },
  {
    key: 'user',
    labelKey: 'auditLogs.categories.user',
    actions: ['create_user', 'update_user', 'delete_user', 'reset_password', 'unlock_user'],
  },
  {
    key: 'system',
    labelKey: 'auditLogs.categories.system',
    actions: ['update_config'],
  },
] as const;

const actionLabelKeys: Record<string, string> = {
  login: 'auditLogs.actionLabels.login',
  logout: 'auditLogs.actionLabels.logout',
  block_terminal: 'auditLogs.actionLabels.block_terminal',
  unblock_terminal: 'auditLogs.actionLabels.unblock_terminal',
  add_whitelist: 'auditLogs.actionLabels.add_whitelist',
  remove_whitelist: 'auditLogs.actionLabels.remove_whitelist',
  block_blacklist: 'auditLogs.actionLabels.block_blacklist',
  unblock_blacklist: 'auditLogs.actionLabels.unblock_blacklist',
  cleanup_expired: 'auditLogs.actionLabels.cleanup_expired',
  create_datasource: 'auditLogs.actionLabels.create_datasource',
  update_datasource: 'auditLogs.actionLabels.update_datasource',
  delete_datasource: 'auditLogs.actionLabels.delete_datasource',
  test_datasource: 'auditLogs.actionLabels.test_datasource',
  sync_datasource: 'auditLogs.actionLabels.sync_datasource',
  create_user: 'auditLogs.actionLabels.create_user',
  update_user: 'auditLogs.actionLabels.update_user',
  delete_user: 'auditLogs.actionLabels.delete_user',
  reset_password: 'auditLogs.actionLabels.reset_password',
  unlock_user: 'auditLogs.actionLabels.unlock_user',
  update_config: 'auditLogs.actionLabels.update_config',
  // Legacy action names (backward compatibility)
  block_ip: 'auditLogs.actionLabels.block_terminal',
  unblock_ip: 'auditLogs.actionLabels.unblock_terminal',
  block: 'auditLogs.actionLabels.block_blacklist',
  unblock: 'auditLogs.actionLabels.unblock_blacklist',
};

const ACTION_CATEGORY_MAP: Record<string, string> = {
  login: 'auth',
  logout: 'auth',
  block_terminal: 'terminal',
  unblock_terminal: 'terminal',
  add_whitelist: 'whitelist',
  remove_whitelist: 'whitelist',
  block_blacklist: 'blacklist',
  unblock_blacklist: 'blacklist',
  cleanup_expired: 'blacklist',
  create_datasource: 'datasource',
  update_datasource: 'datasource',
  delete_datasource: 'datasource',
  test_datasource: 'datasource',
  sync_datasource: 'datasource',
  create_user: 'user',
  update_user: 'user',
  delete_user: 'user',
  reset_password: 'user',
  unlock_user: 'user',
  update_config: 'system',
  // Legacy action names
  block_ip: 'terminal',
  unblock_ip: 'terminal',
  block: 'blacklist',
  unblock: 'blacklist',
};

const CATEGORY_BADGE_STYLES: Record<string, string> = {
  auth: 'bg-blue-100 text-blue-800',
  terminal: 'bg-orange-100 text-orange-800',
  whitelist: 'bg-green-100 text-green-800',
  blacklist: 'bg-red-100 text-red-800',
  datasource: 'bg-purple-100 text-purple-800',
  user: 'bg-cyan-100 text-cyan-800',
  system: 'bg-gray-100 text-gray-800',
};

const getResourceDisplay = (log: AuditLogType, t: (key: string) => string) => {
  const typeLabels: Record<string, string> = {
    auth: t('auditLogs.resourceTypes.auth'),
    mac: t('auditLogs.resourceTypes.terminal'),
    terminal: t('auditLogs.resourceTypes.terminal'),
    whitelist: t('auditLogs.resourceTypes.whitelist'),
    blacklist: t('auditLogs.resourceTypes.blacklist'),
    datasource: t('auditLogs.resourceTypes.datasource'),
    user: t('auditLogs.resourceTypes.user'),
    system: t('auditLogs.resourceTypes.system'),
  };

  const typeLabel = typeLabels[log.resource_type || ''] || log.resource_type || '-';
  const resourceId = log.resource_id || '';

  return { typeLabel, resourceId };
};

const parseDetails = (details: string | null | undefined) => {
  if (!details) return null;
  try {
    const parsed = JSON.parse(details);
    if (typeof parsed === 'object' && parsed !== null) {
      return parsed;
    }
    return { message: details };
  } catch {
    return { message: details };
  }
};

const AuditLogs: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterAction, setFilterAction] = useState<string>('all');
  const [selectedLog, setSelectedLog] = useState<AuditLogType | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  // Debounce search term
  const debouncedSearch = useDebounce(searchTerm, 300);

  // Get available actions for the selected category
  const availableActions = useMemo(() => {
    if (filterCategory === 'all') return [];
    const category = ACTION_CATEGORIES.find((c) => c.key === filterCategory);
    return category?.actions ?? [];
  }, [filterCategory]);

  // Determine the action parameter for the API
  // When a specific action is selected within a category, pass it to the API
  // When a category is selected but no specific action, pass undefined (filter client-side)
  const apiActionParam = useMemo(() => {
    if (filterCategory === 'all') return undefined;
    if (filterAction !== 'all') return filterAction;
    return undefined;
  }, [filterCategory, filterAction]);

  const { data: logsData, isLoading, refetch } = useAuditLogs({
    search: debouncedSearch || undefined,
    action: apiActionParam,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    skip: (currentPage - 1) * pageSize,
    limit: pageSize,
  });

  // Client-side filtering for category (when no specific action is selected)
  const filteredLogs = useMemo(() => {
    const items = logsData?.items ?? [];
    if (filterCategory === 'all' || filterAction !== 'all') return items;
    const category = ACTION_CATEGORIES.find((c) => c.key === filterCategory);
    if (!category) return items;
    return items.filter((log) => (category.actions as readonly string[]).includes(log.action));
  }, [logsData?.items, filterCategory, filterAction]);

  const totalFromServer = useMemo(() => {
    if (filterCategory === 'all' || filterAction !== 'all') {
      return logsData?.total ?? 0;
    }
    // When filtering client-side, use the filtered count
    return filteredLogs.length;
  }, [logsData?.total, filterCategory, filterAction, filteredLogs.length]);

  const totalPages = Math.ceil(totalFromServer / pageSize);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleCategoryChange = (category: string) => {
    setFilterCategory(category);
    setFilterAction('all');
    setCurrentPage(1);
  };

  const handleActionChange = (action: string) => {
    setFilterAction(action);
    setCurrentPage(1);
  };

  const handleExport = async () => {
    try {
      const params: Record<string, string> = {};
      if (searchTerm) params.search = searchTerm;
      if (filterCategory !== 'all' && filterAction !== 'all') params.action = filterAction;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;

      const response = await apiClient.get(API_ENDPOINTS.AUDIT_LOGS_EXPORT, {
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
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t('auditLogs.failedToExportLogs')));
    }
  };

  const handleReset = () => {
    refetch();
    setSearchTerm('');
    setFilterCategory('all');
    setFilterAction('all');
    setStartDate('');
    setEndDate('');
    setCurrentPage(1);
  };

  const getActionBadgeStyle = (action: string) => {
    const category = ACTION_CATEGORY_MAP[action];
    return CATEGORY_BADGE_STYLES[category || ''] || 'bg-gray-100 text-gray-800';
  };

  const renderDetailsContent = (details: string | null | undefined) => {
    const parsed = parseDetails(details);
    if (!parsed) {
      return <p className="text-foreground whitespace-pre-wrap">{t('auditLogs.noDetailsAvailable')}</p>;
    }

    // If it's a simple message object (plain text fallback)
    if (Object.keys(parsed).length === 1 && parsed.message) {
      return <p className="text-foreground whitespace-pre-wrap">{String(parsed.message)}</p>;
    }

    // If it's a JSON object, render key-value pairs
    const message = parsed.message;
    const otherEntries = Object.entries(parsed).filter(([key]) => key !== 'message');

    return (
      <div className="space-y-2">
        {message && (
          <p className="text-foreground font-medium whitespace-pre-wrap">{String(message)}</p>
        )}
        {otherEntries.length > 0 && (
          <div className="space-y-1.5">
            {otherEntries.map(([key, value]) => (
              <div key={key} className="flex gap-2 text-sm">
                <span className="text-muted-foreground min-w-fit">{key}:</span>
                <span className="text-foreground font-mono break-all">
                  {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {isLoading && !logsData ? (
        <PageSkeleton />
      ) : (
      <>
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('auditLogs.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('auditLogs.trackAllActivities')}</p>
        </div>
        <PrimaryButton
          icon={Download}
          label={t('auditLogs.exportLogs')}
          variant="success"
          onClick={handleExport}
        />
      </div>

      {/* Search and Filters */}
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
          <div className="flex flex-col lg:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <input
                type="text"
                placeholder={t('auditLogs.searchByUserActionIp')}
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
              {/* Category Filter */}
              <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                <Filter className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <select
                  value={filterCategory}
                  onChange={(e) => handleCategoryChange(e.target.value)}
                  className="bg-transparent py-1 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[8rem]"
                >
                  {ACTION_CATEGORIES.map((category) => (
                    <option key={category.key} value={category.key}>
                      {t(category.labelKey)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Action Filter (only shown when a category is selected) */}
              {filterCategory !== 'all' && availableActions.length > 0 && (
                <div className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5">
                  <select
                    value={filterAction}
                    onChange={(e) => handleActionChange(e.target.value)}
                    className="bg-transparent py-1 text-sm text-muted-foreground focus:outline-none focus:ring-0 cursor-pointer font-medium min-w-[8rem]"
                  >
                    <option value="all">{t('auditLogs.categories.all')}</option>
                    {availableActions.map((action) => (
                      <option key={action} value={action}>
                        {actionLabelKeys[action] ? t(actionLabelKeys[action]) : action}
                      </option>
                    ))}
                  </select>
                </div>
              )}

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
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-foreground">{totalFromServer}</div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('auditLogs.totalLogs')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-gray-400 to-gray-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-blue-600">
              {new Set(filteredLogs.map((l) => l.username)).size || 0}
            </div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('auditLogs.uniqueUsers')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-4 text-center">
            <div className="text-xl sm:text-2xl font-bold text-green-600">
              {new Set(filteredLogs.map((l) => l.action)).size || 0}
            </div>
            <div className="text-xs sm:text-sm text-muted-foreground mt-1">{t('auditLogs.uniqueActions')}</div>
          </div>
          <div className="h-1 bg-gradient-to-r from-green-400 to-green-600" />
        </div>
      </div>

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('auditLogs.timestamp')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('auditLogs.user')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('auditLogs.action')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('auditLogs.resource')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('auditLogs.ip')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.details')}
                </th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={FileText}
                      title={t('auditLogs.noAuditLogsFound')}
                      description={t('auditLogs.tryAdjustingFilters')}
                    />
                  </td>
                </tr>
              ) : (
                (filteredLogs || []).map((log) => {
                  const { typeLabel, resourceId } = getResourceDisplay(log, t);
                  return (
                    <tr key={log.id} className="hover:bg-blue-50/30 transition-colors">
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center text-sm text-muted-foreground">
                          <Clock className="h-4 w-4 mr-1.5 text-muted-foreground" />
                          {formatDate(log.timestamp)}
                        </div>
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <User className="h-4 w-4 mr-1.5 text-muted-foreground" />
                          <span className="text-sm font-medium text-foreground">
                            {log.username}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${getActionBadgeStyle(log.action)}`}>
                          {actionLabelKeys[log.action] ? t(actionLabelKeys[log.action]) : log.action}
                        </span>
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700 mr-1.5">
                          {typeLabel}
                        </span>
                        {resourceId && (
                          <span className="font-mono text-xs">{resourceId}</span>
                        )}
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap font-mono text-sm text-muted-foreground">
                        {log.ip_address || '-'}
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <IconButton
                          icon={AlertCircle}
                          variant="primary"
                          size="sm"
                          title={log.details ? t('terminal.viewDetails') : t('common.noDetails')}
                          onClick={() => {
                            setSelectedLog(log);
                            setShowModal(true);
                          }}
                        />
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
          totalItems={filteredLogs.length}
          variant="bottom"
        />
      </div>

      {/* Details Modal */}
      {showModal && selectedLog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-xl shadow-xl p-6 w-full max-w-lg">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-foreground">{t('auditLogs.logDetails')}</h2>
              <IconButton
                icon={X}
                variant="ghost"
                size="md"
                onClick={() => setShowModal(false)}
              />
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.logId')}</span>
                <span className="font-mono text-foreground">{selectedLog.id}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.timestamp')}</span>
                <span className="text-foreground">{formatDate(selectedLog.timestamp)}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.user')}</span>
                <span className="text-foreground">{selectedLog.username}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.action')}</span>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getActionBadgeStyle(selectedLog.action)}`}>
                  {actionLabelKeys[selectedLog.action] ? t(actionLabelKeys[selectedLog.action]) : selectedLog.action}
                </span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.resourceType')}</span>
                <span className="text-foreground">{getResourceDisplay(selectedLog, t).typeLabel}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.resourceId')}</span>
                <span className="font-mono text-foreground">{selectedLog.resource_id || '-'}</span>
              </div>

              <div className="flex justify-between items-center py-2 border-b border-border">
                <span className="text-muted-foreground">{t('auditLogs.ip')}</span>
                <span className="font-mono text-foreground">{selectedLog.ip_address || '-'}</span>
              </div>

              <div className="py-2">
                <span className="text-muted-foreground block mb-2">{t('common.details')}</span>
                <div className="bg-background rounded-lg p-4 max-h-40 overflow-y-auto">
                  {renderDetailsContent(selectedLog.details)}
                </div>
              </div>
            </div>

            <PrimaryButton
              label={t('common.close')}
              variant="secondary"
              onClick={() => setShowModal(false)}
              className="w-full mt-6"
            />
          </div>
        </div>
      )}
      </>
      )}
    </div>
  );
};

export default AuditLogs;
