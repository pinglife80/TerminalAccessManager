import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/auth';
import { useStats, useSystemStatus } from '@/hooks/useTerminalData';
import {
  Server, List, ShieldOff, AlertCircle, Search, FileText,
  Network, Shield, Activity, Wifi, Database, ArrowRight, Clock
} from 'lucide-react';
import { DashboardSkeleton } from '@/components/Skeleton';
import { PrimaryButton } from '@/components/Button';

const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { data: stats, isLoading, error, dataUpdatedAt } = useStats();
  const { data: systemStatus } = useSystemStatus();

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="bg-card rounded-2xl shadow-lg p-8 max-w-md">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-foreground mb-2 text-center">{t('dashboard.errorLoadingData')}</h2>
          <p className="text-muted-foreground text-center">{error.message}</p>
          <PrimaryButton
            label={t('common.refresh')}
            variant="primary"
            onClick={() => window.location.reload()}
            className="mt-4 w-full"
          />
        </div>
      </div>
    );
  }

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  const quickActions = [
    {
      icon: Search,
      label: t('dashboard.searchTerminals'),
      description: t('dashboard.findAndManage'),
      path: '/terminals',
      color: 'blue',
      bgClass: 'bg-blue-50',
      iconBgClass: 'bg-blue-100',
      iconClass: 'text-blue-600',
      hoverClass: 'hover:border-blue-300 hover:shadow-blue-100',
    },
    {
      icon: Shield,
      label: t('dashboard.manageWhitelist'),
      description: t('dashboard.addOrRemoveTrusted'),
      path: '/whitelist',
      color: 'green',
      bgClass: 'bg-green-50',
      iconBgClass: 'bg-green-100',
      iconClass: 'text-green-600',
      hoverClass: 'hover:border-green-300 hover:shadow-green-100',
    },
    {
      icon: ShieldOff,
      label: t('dashboard.blockTerminals'),
      description: t('dashboard.blockOrUnblock'),
      path: '/blacklist',
      color: 'red',
      bgClass: 'bg-red-50',
      iconBgClass: 'bg-red-100',
      iconClass: 'text-red-600',
      hoverClass: 'hover:border-red-300 hover:shadow-red-100',
    },
    {
      icon: FileText,
      label: t('dashboard.auditLogsAction'),
      description: t('dashboard.reviewSystemLogs'),
      path: '/audit-logs',
      color: 'purple',
      bgClass: 'bg-purple-50',
      iconBgClass: 'bg-purple-100',
      iconClass: 'text-purple-600',
      hoverClass: 'hover:border-purple-300 hover:shadow-purple-100',
    },
  ];

  const systemStatusItems = [
    {
      name: t('dashboard.backendApi'),
      status: (systemStatus?.backend_api === 'connected' ? 'connected' : 'disconnected') as 'connected' | 'pending',
      icon: Activity,
      detail: systemStatus?.backend_api === 'connected' ? t('dashboard.running') : t('dashboard.disconnected'),
    },
    {
      name: t('dashboard.database'),
      status: (systemStatus?.database === 'connected' ? 'connected' : 'pending') as 'connected' | 'pending',
      icon: Database,
      detail: systemStatus?.database === 'connected' ? t('dashboard.activeStatus') : t('dashboard.unavailable'),
    },
    {
      name: t('dashboard.sangforAf'),
      status: (systemStatus?.sangfor?.connected ? 'connected' : 'pending') as 'connected' | 'pending',
      icon: Shield,
      detail: systemStatus?.sangfor?.connected
        ? `CPU: ${systemStatus.sangfor.cpu ?? '-'}% | Mem: ${systemStatus.sangfor.memory ?? '-'}%`
        : (systemStatus?.sangfor?.error || t('dashboard.notConfigured')),
    },
    {
      name: t('dashboard.networkScanner'),
      status: (systemStatus?.network_scanner === 'connected' ? 'connected' : 'pending') as 'connected' | 'pending',
      icon: Wifi,
      detail: systemStatus?.network_scanner === 'connected' ? t('dashboard.running') : t('dashboard.pendingConfiguration'),
    },
  ];

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('dashboard.title')}</h1>
            <p className="text-muted-foreground mt-1">{t('dashboard.welcomeBack')}, {user?.username}</p>
          </div>
        </div>
      </div>

      {/* Overview Section */}
      <div className="mb-6 bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">{t('dashboard.dashboardOverview')}</h2>
        </div>
        <div className="p-6">
          <p className="text-muted-foreground text-sm leading-relaxed">
            {t('dashboard.welcomeDescription')}
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 mb-8">
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                <Server className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">{t('dashboard.totalTerminals')}</p>
                <p className="text-2xl sm:text-3xl font-bold text-foreground">{stats?.total || 0}</p>
              </div>
            </div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>

        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
                <List className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">{t('dashboard.whitelisted')}</p>
                <p className="text-2xl sm:text-3xl font-bold text-foreground">{stats?.whitelisted || 0}</p>
              </div>
            </div>
          </div>
          <div className="h-1 bg-gradient-to-r from-green-400 to-green-600" />
        </div>

        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-red-100 rounded-xl flex items-center justify-center">
                <ShieldOff className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">{t('dashboard.blocked')}</p>
                <p className="text-2xl sm:text-3xl font-bold text-foreground">{stats?.blocked || 0}</p>
              </div>
            </div>
          </div>
          <div className="h-1 bg-gradient-to-r from-red-400 to-red-600" />
        </div>
      </div>

      {/* Quick Actions & System Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Quick Actions - Takes 2 columns */}
        <div className="lg:col-span-2">
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
            <div className="px-6 py-5 border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Network className="h-5 w-5 text-muted-foreground" />
                  <h2 className="text-lg font-semibold text-foreground">{t('dashboard.quickActions')}</h2>
                </div>
              </div>
            </div>
            <div className="p-4 sm:p-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {quickActions.map((action) => (
                  <button
                    key={action.path}
                    type="button"
                    onClick={() => navigate(action.path)}
                    className={`group flex items-start gap-4 p-4 rounded-xl border border-border bg-card ${action.hoverClass} hover:shadow-md transition-all duration-200 text-left`}
                  >
                    <div className={`flex-shrink-0 w-10 h-10 ${action.iconBgClass} rounded-lg flex items-center justify-center`}>
                      <action.icon className={`h-5 w-5 ${action.iconClass}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-foreground group-hover:text-muted-foreground">
                        {action.label}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {action.description}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-muted-foreground mt-1 flex-shrink-0 transition-colors" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* System Status - Takes 1 column */}
        <div className="lg:col-span-1">
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden h-full">
            <div className="px-6 py-5 border-b border-border">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-muted-foreground" />
                <h2 className="text-lg font-semibold text-foreground">{t('dashboard.systemStatus')}</h2>
              </div>
            </div>
            <div className="p-4 sm:p-6">
              <div className="space-y-4">
                {systemStatusItems.map((item) => (
                  <div
                    key={item.name}
                    className="flex items-center gap-3 p-3 bg-background rounded-xl"
                  >
                    <div className={`flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${
                      item.status === 'connected'
                        ? 'bg-green-100'
                        : 'bg-yellow-100'
                    }`}>
                      <item.icon className={`h-4 w-4 ${
                        item.status === 'connected'
                          ? 'text-green-600'
                          : 'text-yellow-600'
                      }`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground">{item.name}</p>
                      <p className="text-xs text-muted-foreground">{item.detail}</p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-full ${
                        item.status === 'connected'
                          ? 'bg-green-500'
                          : 'bg-yellow-500 animate-pulse'
                      }`} />
                      <span className={`text-xs font-semibold ${
                        item.status === 'connected'
                          ? 'text-green-700'
                          : 'text-yellow-700'
                      }`}>
                        {item.status === 'connected' ? t('common.online') : t('common.pending')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Last updated indicator */}
              <div className="mt-6 pt-4 border-t border-border">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" />
                  <span>{t('common.lastUpdated')}: {dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—'}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
