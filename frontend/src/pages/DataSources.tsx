import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  Database,
  Link2,
  RefreshCw,
  Shield,
} from 'lucide-react';
import { useDataSources, useDataSourceBindings, useComplianceBaselines } from '@/hooks/useTerminalData';
import { PrimaryButton, ButtonGroup } from '@/components/Button';
import { PageSkeleton } from '@/components/Skeleton';
import DataSourcesTab from '@/components/datasources/DataSourcesTab';
import ComplianceBaselinesTab from '@/components/datasources/ComplianceBaselinesTab';
import BindingsTab from '@/components/datasources/BindingsTab';

const DataSources: React.FC = () => {
  const { t } = useTranslation();
  // Tab state
  const [activeTab, setActiveTab] = useState<'sources' | 'bindings' | 'baselines'>('sources');

  // Data queries for refetch
  const { isLoading: dsLoading, data: dsData, refetch: dsRefetch } = useDataSources();
  const { isLoading: bindLoading, data: bindData, refetch: bindRefetch } = useDataSourceBindings();
  const { isLoading: blLoading, data: blData, refetch: blRefetch } = useComplianceBaselines();

  // Refs to child tab components for triggering add modals
  const dsTabRef = React.useRef<{ openAddModal: () => void } | null>(null);
  const blTabRef = React.useRef<{ openAddModal: () => void } | null>(null);
  const bindTabRef = React.useRef<{ openAddModal: () => void } | null>(null);

  const isLoading = ((activeTab === 'sources' && dsLoading && !dsData) ||
    (activeTab === 'bindings' && bindLoading && !bindData) ||
    (activeTab === 'baselines' && blLoading && !blData));

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('dataSources.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('dataSources.manageConnections')}</p>
        </div>
        <ButtonGroup>
          <PrimaryButton
            icon={RefreshCw}
            label={t('common.refresh')}
            variant="secondary"
            onClick={() => { dsRefetch(); bindRefetch(); blRefetch(); }}
          />
          {activeTab === 'sources' && (
            <PrimaryButton
              icon={Plus}
              label={t('dataSources.addSource')}
              variant="success"
              onClick={() => dsTabRef.current?.openAddModal()}
            />
          )}
          {activeTab === 'bindings' && (
            <PrimaryButton
              icon={Link2}
              label={t('dataSources.addBinding')}
              variant="success"
              onClick={() => bindTabRef.current?.openAddModal()}
            />
          )}
          {activeTab === 'baselines' && (
            <PrimaryButton
              icon={Plus}
              label={t('dataSources.addBaseline')}
              variant="success"
              onClick={() => blTabRef.current?.openAddModal()}
            />
          )}
        </ButtonGroup>
      </div>

      {/* Tabs */}
      <div className="mb-6 border-b border-border">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('sources')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'sources'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-muted-foreground hover:text-muted-foreground hover:border-border'
            }`}
          >
            <Database className="h-4 w-4 inline mr-2" />
            {t('dataSources.dataSourcesTab')}
          </button>
          <button
            onClick={() => setActiveTab('bindings')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'bindings'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-muted-foreground hover:text-muted-foreground hover:border-border'
            }`}
          >
            <Link2 className="h-4 w-4 inline mr-2" />
            {t('dataSources.bindingsTab')}
          </button>
          <button
            onClick={() => setActiveTab('baselines')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'baselines'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-muted-foreground hover:text-muted-foreground hover:border-border'
            }`}
          >
            <Shield className="h-4 w-4 inline mr-2" />
            {t('dataSources.complianceBaselines')}
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {isLoading ? (
        <PageSkeleton />
      ) : (
        <>
          {activeTab === 'sources' && (
            <DataSourcesTab
              ref={dsTabRef}
              onAddClick={() => dsTabRef.current?.openAddModal()}
            />
          )}
          {activeTab === 'bindings' && (
            <BindingsTab
              ref={bindTabRef}
              onAddClick={() => bindTabRef.current?.openAddModal()}
            />
          )}
          {activeTab === 'baselines' && (
            <ComplianceBaselinesTab
              ref={blTabRef}
              onAddClick={() => blTabRef.current?.openAddModal()}
            />
          )}
        </>
      )}
    </div>
  );
};

export default DataSources;
