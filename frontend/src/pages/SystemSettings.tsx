import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Settings, Key, HardDrive, Bell, Shield, Mail, Info } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { CardSkeleton } from '@/components/Skeleton';

interface SystemConfigInfo {
  version: string;
  environment: string;
  debug: boolean;
  log_level: string;
  email_enabled: boolean;
  metrics_enabled: boolean;
}

const ConfigItem: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex flex-col gap-1 p-3 rounded-lg bg-muted/50">
    <span className="text-xs text-muted-foreground">{label}</span>
    <span className="text-sm font-medium text-foreground">{value}</span>
  </div>
);

const SystemSettings: React.FC = () => {
  const { t } = useTranslation();

  const { data: systemConfig, isLoading: configLoading } = useQuery<SystemConfigInfo>({
    queryKey: ['system-config'],
    queryFn: async () => {
      const res = await apiClient.get(API_ENDPOINTS.SYSTEM_CONFIG);
      return res.data;
    },
  });

  const configCards = [
    {
      title: t('systemSettings.general'),
      description: t('systemSettings.generalDesc'),
      icon: Settings,
      path: '/general-settings',
      color: 'bg-blue-500',
      lightColor: 'bg-blue-50',
      textColor: 'text-blue-600',
    },
    {
      title: t('systemSettings.authProviders'),
      description: t('systemSettings.authProvidersDesc'),
      icon: Key,
      path: '/auth-providers',
      color: 'bg-green-500',
      lightColor: 'bg-green-50',
      textColor: 'text-green-600',
    },
    {
      title: t('systemSettings.backup'),
      description: t('systemSettings.backupDesc'),
      icon: HardDrive,
      path: '/backup',
      color: 'bg-purple-500',
      lightColor: 'bg-purple-50',
      textColor: 'text-purple-600',
    },
    {
      title: t('systemSettings.notifications'),
      description: t('systemSettings.notificationsDesc'),
      icon: Bell,
      path: '/notifications',
      color: 'bg-orange-500',
      lightColor: 'bg-orange-50',
      textColor: 'text-orange-600',
    },
    {
      title: t('systemSettings.email'),
      description: t('systemSettings.emailDesc'),
      icon: Mail,
      path: '/email-settings',
      color: 'bg-indigo-500',
      lightColor: 'bg-indigo-50',
      textColor: 'text-indigo-600',
    },
    {
      title: t('systemSettings.users'),
      description: t('systemSettings.usersDesc'),
      icon: Shield,
      path: '/users',
      color: 'bg-cyan-500',
      lightColor: 'bg-cyan-50',
      textColor: 'text-cyan-600',
    },
    {
      title: t('systemSettings.roles'),
      description: t('systemSettings.rolesDesc'),
      icon: Shield,
      path: '/roles',
      color: 'bg-red-500',
      lightColor: 'bg-red-50',
      textColor: 'text-red-600',
    },
  ];

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2">
              <Settings className="h-6 w-6" />
              {t('systemSettings.title')}
            </h1>
            <p className="text-muted-foreground mt-1">{t('systemSettings.description')}</p>
          </div>
        </div>

        {/* Configuration Cards */}
        <div className="bg-card rounded-xl border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-6">{t('systemSettings.configuration')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {configCards.map((card) => (
              <Link
                key={card.path}
                to={card.path}
                className={`${card.lightColor} rounded-xl p-5 hover:shadow-md transition-all duration-200 group cursor-pointer`}
              >
                <div className={`w-12 h-12 rounded-lg ${card.color} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                  <card.icon className="h-6 w-6 text-white" />
                </div>
                <h3 className={`font-semibold ${card.textColor} mb-2`}>{card.title}</h3>
                <p className="text-sm text-muted-foreground">{card.description}</p>
              </Link>
            ))}
          </div>
        </div>

        {/* System Config Summary */}
        <div className="bg-card rounded-xl border border-border p-6 mt-6">
          <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
            <Info className="h-5 w-5 text-primary-600" />
            {t('systemSettings.systemConfig')}
          </h2>
          {configLoading ? (
            <CardSkeleton />
          ) : systemConfig ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <ConfigItem label={t('systemSettings.version')} value={systemConfig.version} />
              <ConfigItem label={t('systemSettings.environment')} value={systemConfig.environment} />
              <ConfigItem label={t('systemSettings.debugMode')} value={systemConfig.debug ? t('systemSettings.enabled') : t('systemSettings.disabled')} />
              <ConfigItem label={t('systemSettings.logLevel')} value={systemConfig.log_level} />
              <ConfigItem label={t('systemSettings.emailService')} value={systemConfig.email_enabled ? t('systemSettings.enabled') : t('systemSettings.disabled')} />
              <ConfigItem label={t('systemSettings.metricsService')} value={systemConfig.metrics_enabled ? t('systemSettings.enabled') : t('systemSettings.disabled')} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('systemSettings.configUnavailable')}</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default SystemSettings;
