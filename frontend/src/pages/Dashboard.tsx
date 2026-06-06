import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { useStats } from '@/hooks/useMacData';
import {
  Server, List, ShieldOff, AlertCircle, Search, FileText,
  Network, Shield, Activity, Wifi, Database, ArrowRight, Clock
} from 'lucide-react';
import { DashboardSkeleton } from '@/components/Skeleton';
import { PrimaryButton } from '@/components/Button';

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { data: stats, isLoading, error } = useStats();

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 mb-2 text-center">Error Loading Data</h2>
          <p className="text-gray-600 text-center">{error.message}</p>
          <PrimaryButton
            label="Refresh"
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
      label: 'Search Terminals',
      description: 'Find and manage network terminals',
      path: '/mac-addresses',
      color: 'blue',
      bgClass: 'bg-blue-50',
      iconBgClass: 'bg-blue-100',
      iconClass: 'text-blue-600',
      hoverClass: 'hover:border-blue-300 hover:shadow-blue-100',
    },
    {
      icon: Shield,
      label: 'Manage Whitelist',
      description: 'Add or remove trusted terminals',
      path: '/whitelist',
      color: 'green',
      bgClass: 'bg-green-50',
      iconBgClass: 'bg-green-100',
      iconClass: 'text-green-600',
      hoverClass: 'hover:border-green-300 hover:shadow-green-100',
    },
    {
      icon: ShieldOff,
      label: 'Block Terminals',
      description: 'Block or unblock network access',
      path: '/blacklist',
      color: 'red',
      bgClass: 'bg-red-50',
      iconBgClass: 'bg-red-100',
      iconClass: 'text-red-600',
      hoverClass: 'hover:border-red-300 hover:shadow-red-100',
    },
    {
      icon: FileText,
      label: 'Audit Logs',
      description: 'Review system activity logs',
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
      name: 'Backend API',
      status: 'connected' as const,
      icon: Activity,
      detail: 'Running',
    },
    {
      name: 'Database',
      status: 'connected' as const,
      icon: Database,
      detail: 'Active',
    },
    {
      name: 'Network Scanner',
      status: 'pending' as const,
      icon: Wifi,
      detail: 'Pending configuration',
    },
  ];

  return (
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-1">Welcome back, {user?.username}</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 mb-8">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                <Server className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Total Terminals</p>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900">{stats?.total || 0}</p>
              </div>
            </div>
          </div>
          <div className="h-1 bg-gradient-to-r from-blue-400 to-blue-600" />
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
                <List className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Whitelisted</p>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900">{stats?.whitelisted || 0}</p>
              </div>
            </div>
          </div>
          <div className="h-1 bg-gradient-to-r from-green-400 to-green-600" />
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-red-100 rounded-xl flex items-center justify-center">
                <ShieldOff className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Blocked</p>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900">{stats?.blocked || 0}</p>
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
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Network className="h-5 w-5 text-gray-500" />
                  <h2 className="text-lg font-semibold text-gray-900">Quick Actions</h2>
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
                    className={`group flex items-start gap-4 p-4 rounded-xl border border-gray-200 bg-white ${action.hoverClass} hover:shadow-md transition-all duration-200 text-left`}
                  >
                    <div className={`flex-shrink-0 w-10 h-10 ${action.iconBgClass} rounded-lg flex items-center justify-center`}>
                      <action.icon className={`h-5 w-5 ${action.iconClass}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-900 group-hover:text-gray-700">
                        {action.label}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {action.description}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500 mt-1 flex-shrink-0 transition-colors" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* System Status - Takes 1 column */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden h-full">
            <div className="px-6 py-5 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-gray-500" />
                <h2 className="text-lg font-semibold text-gray-900">System Status</h2>
              </div>
            </div>
            <div className="p-4 sm:p-6">
              <div className="space-y-4">
                {systemStatusItems.map((item) => (
                  <div
                    key={item.name}
                    className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl"
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
                      <p className="text-sm font-medium text-gray-900">{item.name}</p>
                      <p className="text-xs text-gray-500">{item.detail}</p>
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
                        {item.status === 'connected' ? 'Online' : 'Pending'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Last updated indicator */}
              <div className="mt-6 pt-4 border-t border-gray-100">
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <Clock className="h-3.5 w-3.5" />
                  <span>Last updated: just now</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Overview Section */}
      <div className="mt-6 bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">Dashboard Overview</h2>
        </div>
        <div className="p-6">
          <p className="text-gray-600 text-sm leading-relaxed">
            Welcome to the Terminal Network Access Manager. This dashboard provides real-time monitoring
            and management of network terminals, access control, and security controls. Use the quick actions
            above to navigate to key features, or check the system status to ensure all services are running properly.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
