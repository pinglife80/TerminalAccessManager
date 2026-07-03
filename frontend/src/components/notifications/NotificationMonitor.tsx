import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import {
  BarChart3, RefreshCw, CheckCircle, XCircle, Clock,
  Send, Activity, Zap, RotateCcw,
} from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';

interface OverviewStats {
  total: number;
  sent: number;
  failed: number;
  pending: number;
  retrying: number;
  suppressed: number;
  success_rate: number;
  avg_latency_ms: number | null;
  queue_size: number;
  retry_queue_size: number;
}

interface ChannelStat {
  channel_name: string;
  total: number;
  sent: number;
  failed: number;
  success_rate: number;
}

interface EventStat {
  event_type: string;
  total: number;
  sent: number;
  failed: number;
  success_rate: number;
}

interface StatsResponse {
  overview: OverviewStats;
  by_channel: ChannelStat[];
  by_event: EventStat[];
}

const NotificationMonitor: React.FC = () => {
  const { t } = useTranslation();
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [retryingAll, setRetryingAll] = useState(false);

  const fetchStats = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const response = await apiClient.get<StatsResponse>(API_ENDPOINTS.NOTIFICATION_STATS);
      setStats(response.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(() => fetchStats(false), 30000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchStats(false);
    setRefreshing(false);
  };

  const handleRetryAll = async () => {
    if (!stats || stats.overview.failed === 0) return;
    if (!window.confirm(t('notificationMonitor.retryAllConfirm'))) return;
    setRetryingAll(true);
    try {
      const res = await apiClient.post<{ count: number }>(API_ENDPOINTS.NOTIFICATION_LOGS_RETRY_ALL);
      toast.success(t('notificationMonitor.retryAllSuccess', { count: res.data.count }));
      await fetchStats(false);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setRetryingAll(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  const ov = stats?.overview;

  const statCards = ov ? [
    {
      label: t('notificationMonitor.total'),
      value: ov.total,
      icon: BarChart3,
      color: 'text-slate-600 bg-slate-100 dark:text-slate-300 dark:bg-slate-800',
    },
    {
      label: t('notificationMonitor.sent'),
      value: ov.sent,
      icon: CheckCircle,
      color: 'text-green-600 bg-green-100 dark:text-green-300 dark:bg-green-900/30',
    },
    {
      label: t('notificationMonitor.failed'),
      value: ov.failed,
      icon: XCircle,
      color: 'text-red-600 bg-red-100 dark:text-red-300 dark:bg-red-900/30',
    },
    {
      label: t('notificationMonitor.successRate'),
      value: `${ov.success_rate.toFixed(1)}%`,
      icon: Activity,
      color: 'text-blue-600 bg-blue-100 dark:text-blue-300 dark:bg-blue-900/30',
    },
    {
      label: t('notificationMonitor.pending'),
      value: ov.pending,
      icon: Clock,
      color: 'text-amber-600 bg-amber-100 dark:text-amber-300 dark:bg-amber-900/30',
    },
    {
      label: t('notificationMonitor.retrying'),
      value: ov.retrying,
      icon: RotateCcw,
      color: 'text-orange-600 bg-orange-100 dark:text-orange-300 dark:bg-orange-900/30',
    },
    {
      label: t('notificationMonitor.suppressed'),
      value: ov.suppressed,
      icon: Zap,
      color: 'text-purple-600 bg-purple-100 dark:text-purple-300 dark:bg-purple-900/30',
    },
    {
      label: t('notificationMonitor.queueSize'),
      value: ov.queue_size,
      icon: Send,
      color: 'text-indigo-600 bg-indigo-100 dark:text-indigo-300 dark:bg-indigo-900/30',
    },
  ] : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            {t('notificationMonitor.title')}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t('notificationMonitor.description')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {ov && ov.failed > 0 && (
            <PrimaryButton
              onClick={handleRetryAll}
              loading={retryingAll}
              variant="secondary"
              icon={RotateCcw}
              label={t('notificationMonitor.retryAll')}
            />
          )}
          <PrimaryButton
            onClick={handleRefresh}
            variant="ghost"
            loading={refreshing}
            icon={RefreshCw}
            label={t('common.refresh')}
          />
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
        {statCards.map((card, i) => {
          const Icon = card.icon;
          return (
            <div
              key={i}
              className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`p-1.5 rounded ${card.color}`}>
                  <Icon className="h-4 w-4" />
                </div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {card.label}
                </span>
              </div>
              <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {card.value}
              </div>
            </div>
          );
        })}
      </div>

      {/* Latency & Queue Info */}
      {ov && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
              {t('notificationMonitor.avgLatency')}
            </div>
            <div className="text-xl font-semibold text-slate-900 dark:text-slate-100">
              {ov.avg_latency_ms !== null ? `${ov.avg_latency_ms.toFixed(0)} ms` : t('notificationMonitor.notAvailable')}
            </div>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
              {t('notificationMonitor.retryQueueSize')}
            </div>
            <div className="text-xl font-semibold text-slate-900 dark:text-slate-100">
              {ov.retry_queue_size}
            </div>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
              {t('notificationMonitor.autoRefresh')}
            </div>
            <div className="text-sm text-slate-700 dark:text-slate-300">
              {t('notificationMonitor.autoRefreshDesc')}
            </div>
          </div>
        </div>
      )}

      {/* Two Column: Channel Stats + Event Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Per-Channel Stats */}
        <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              {t('notificationMonitor.byChannel')}
            </h3>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {stats?.by_channel.length === 0 ? (
              <div className="p-6 text-center text-slate-500 dark:text-slate-400 text-sm">
                {t('notificationMonitor.noData')}
              </div>
            ) : (
              stats?.by_channel.map((ch) => (
                <div key={ch.channel_name} className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {ch.channel_name}
                    </span>
                    <span className={`text-sm font-medium ${
                      ch.success_rate >= 90 ? 'text-green-600 dark:text-green-400' :
                      ch.success_rate >= 70 ? 'text-amber-600 dark:text-amber-400' :
                      'text-red-600 dark:text-red-400'
                    }`}>
                      {ch.success_rate.toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2 mb-1">
                    <div
                      className={`h-2 rounded-full ${
                        ch.success_rate >= 90 ? 'bg-green-500' :
                        ch.success_rate >= 70 ? 'bg-amber-500' :
                        'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(ch.success_rate, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                    <span>{t('notificationMonitor.total')}: {ch.total}</span>
                    <span>
                      <span className="text-green-600 dark:text-green-400">
                        {t('notificationMonitor.sent')}: {ch.sent}
                      </span>
                      {' / '}
                      <span className="text-red-600 dark:text-red-400">
                        {t('notificationMonitor.failed')}: {ch.failed}
                      </span>
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Per-Event Stats */}
        <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              {t('notificationMonitor.byEvent')}
            </h3>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-700 max-h-96 overflow-y-auto">
            {stats?.by_event.length === 0 ? (
              <div className="p-6 text-center text-slate-500 dark:text-slate-400 text-sm">
                {t('notificationMonitor.noData')}
              </div>
            ) : (
              stats?.by_event.map((ev) => (
                <div key={ev.event_type} className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <code className="text-sm text-slate-700 dark:text-slate-300 font-mono">
                      {ev.event_type}
                    </code>
                    <span className={`text-sm font-medium ${
                      ev.success_rate >= 90 ? 'text-green-600 dark:text-green-400' :
                      ev.success_rate >= 70 ? 'text-amber-600 dark:text-amber-400' :
                      'text-red-600 dark:text-red-400'
                    }`}>
                      {ev.success_rate.toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                    <span>{t('notificationMonitor.total')}: {ev.total}</span>
                    <span>
                      <span className="text-green-600 dark:text-green-400">
                        {t('notificationMonitor.sent')}: {ev.sent}
                      </span>
                      {' / '}
                      <span className="text-red-600 dark:text-red-400">
                        {t('notificationMonitor.failed')}: {ev.failed}
                      </span>
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default NotificationMonitor;
