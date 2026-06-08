import React, { useState, useMemo } from 'react';
import {
  Plus,
  Trash2,
  Database,
  Server,
  Clock,
  Plug,
  Link2,
  RefreshCw,
  CheckCircle,
  XCircle,
  Pencil,
  Shield,
} from 'lucide-react';
import { useDataSources, useDataSourceBindings, DataSourceItem, useComplianceBaselines, ComplianceBaselineItem } from '@/hooks/useTerminalData';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';
import { formatDate } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Type-specific config field definitions
// ---------------------------------------------------------------------------
interface ConfigFieldDef {
  key: string;
  label: string;
  type: 'text' | 'password' | 'number' | 'select';
  placeholder?: string;
  options?: { value: string; label: string }[];
  defaultValue?: string;
}

const CONFIG_FIELDS: Record<string, ConfigFieldDef[]> = {
  arp_ssh: [
    { key: 'host', label: 'Host', type: 'text', placeholder: '192.168.1.1' },
    { key: 'port', label: 'Port', type: 'number', placeholder: '22', defaultValue: '22' },
    { key: 'username', label: 'Username', type: 'text', placeholder: 'root' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '********' },
    { key: 'command', label: 'Command', type: 'text', placeholder: 'show arp' },
  ],
  arp_api: [
    { key: 'url', label: 'URL', type: 'text', placeholder: 'https://api.example.com/arp' },
    { key: 'method', label: 'Method', type: 'select', options: [{ value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' }], defaultValue: 'GET' },
    { key: 'headers', label: 'Headers (JSON)', type: 'text', placeholder: '{"Authorization": "Bearer ..."}' },
    { key: 'auth_type', label: 'Auth Type', type: 'select', options: [{ value: 'none', label: 'None' }, { value: 'bearer', label: 'Bearer Token' }, { value: 'basic', label: 'Basic Auth' }], defaultValue: 'none' },
    { key: 'token', label: 'Token / Password', type: 'password', placeholder: '********' },
  ],
  sangfor: [
    { key: 'base_url', label: 'Base URL', type: 'text', placeholder: 'https://sangfor.example.com' },
    { key: 'username', label: 'Username', type: 'text', placeholder: 'admin' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '********' },
    { key: 'verify_ssl', label: 'Verify SSL', type: 'select', options: [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }], defaultValue: 'false' },
    { key: 'ca_bundle', label: 'CA Bundle Path', type: 'text', placeholder: '/path/to/ca-bundle.crt' },
  ],
};

const TYPE_BADGE: Record<string, { label: string; className: string }> = {
  arp_ssh: { label: 'ARP SSH', className: 'bg-blue-100 text-blue-800' },
  arp_api: { label: 'ARP API', className: 'bg-green-100 text-green-800' },
  sangfor: { label: 'Sangfor', className: 'bg-orange-100 text-orange-800' },
};

// Baseline type config fields (only ipguard)
const BASELINE_CONFIG_FIELDS: Record<string, ConfigFieldDef[]> = {
  ipguard: [
    { key: 'host', label: 'Host', type: 'text', placeholder: '192.168.1.100' },
    { key: 'port', label: 'Port', type: 'number', placeholder: '3306', defaultValue: '3306' },
    { key: 'username', label: 'Username', type: 'text', placeholder: 'admin' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '********' },
    { key: 'database', label: 'Database', type: 'text', placeholder: 'ipguard' },
  ],
};

const BASELINE_TYPE_BADGE: Record<string, { label: string; className: string }> = {
  ipguard: { label: 'IP-Guard', className: 'bg-purple-100 text-purple-800' },
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
const DataSources: React.FC = () => {
  // Tab state
  const [activeTab, setActiveTab] = useState<'sources' | 'bindings' | 'baselines'>('sources');

  // Data Source queries
  const { data: dataSources, isLoading: dsLoading, refetch: dsRefetch } = useDataSources();
  const { data: bindings, isLoading: bindLoading, refetch: bindRefetch } = useDataSourceBindings();
  const { data: baselines, isLoading: blLoading, refetch: blRefetch } = useComplianceBaselines();

  // Pagination
  const [dsPage, setDsPage] = useState(1);
  const [dsPageSize, setDsPageSize] = useState(10);
  const [bindPage, setBindPage] = useState(1);
  const [bindPageSize, setBindPageSize] = useState(10);

  // Add Data Source modal
  const [showAddDsModal, setShowAddDsModal] = useState(false);
  const [dsForm, setDsForm] = useState({
    name: '',
    type: 'arp_ssh',
    tag: '',
    enabled: true,
  });
  const [dsConfig, setDsConfig] = useState<Record<string, string>>({});
  const [isAddingDs, setIsAddingDs] = useState(false);

  // Delete Data Source modal
  const [showDeleteDsModal, setShowDeleteDsModal] = useState(false);
  const [deleteDsItem, setDeleteDsItem] = useState<DataSourceItem | null>(null);
  const [isDeletingDs, setIsDeletingDs] = useState(false);

  // Test connection
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);

  // Edit Data Source modal
  const [showEditDsModal, setShowEditDsModal] = useState(false);
  const [editDsForm, setEditDsForm] = useState({
    id: 0,
    name: '',
    type: 'arp_ssh',
    tag: '',
    enabled: true,
  });
  const [editDsConfig, setEditDsConfig] = useState<Record<string, string>>({});
  const [isEditingDs, setIsEditingDs] = useState(false);

  // Sync Data Source
  const [syncingId, setSyncingId] = useState<number | null>(null);

  // Compliance Baselines state
  const [blPage, setBlPage] = useState(1);
  const [blPageSize, setBlPageSize] = useState(10);

  // Add Baseline modal
  const [showAddBlModal, setShowAddBlModal] = useState(false);
  const [blForm, setBlForm] = useState({
    name: '',
    type: 'ipguard',
    tag: '',
    enabled: true,
  });
  const [blConfig, setBlConfig] = useState<Record<string, string>>({});
  const [isAddingBl, setIsAddingBl] = useState(false);

  // Delete Baseline modal
  const [showDeleteBlModal, setShowDeleteBlModal] = useState(false);
  const [deleteBlItem, setDeleteBlItem] = useState<ComplianceBaselineItem | null>(null);
  const [isDeletingBl, setIsDeletingBl] = useState(false);

  // Test Baseline connection
  const [blTestingId, setBlTestingId] = useState<number | null>(null);
  const [blTestResult, setBlTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);

  // Edit Baseline modal
  const [showEditBlModal, setShowEditBlModal] = useState(false);
  const [editBlForm, setEditBlForm] = useState({
    id: 0,
    name: '',
    type: 'ipguard',
    tag: '',
    enabled: true,
  });
  const [editBlConfig, setEditBlConfig] = useState<Record<string, string>>({});
  const [isEditingBl, setIsEditingBl] = useState(false);

  // Sync Baseline
  const [blSyncingId, setBlSyncingId] = useState<number | null>(null);

  // Add Binding modal
  const [showAddBindModal, setShowAddBindModal] = useState(false);
  const [bindForm, setBindForm] = useState({ arp_source_tag: '', firewall_tag: '' });
  const [isAddingBind, setIsAddingBind] = useState(false);

  // Delete Binding modal
  const [showDeleteBindModal, setShowDeleteBindModal] = useState(false);
  const [deleteBindId, setDeleteBindId] = useState<number | null>(null);
  const [isDeletingBind, setIsDeletingBind] = useState(false);

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------
  const dsList = dataSources || [];
  const bindList = bindings || [];
  const blList = baselines || [];

  const dsTotalPages = Math.max(1, Math.ceil(dsList.length / dsPageSize));
  const paginatedDs = useMemo(() => {
    const start = (dsPage - 1) * dsPageSize;
    return dsList.slice(start, start + dsPageSize);
  }, [dsList, dsPage, dsPageSize]);

  const bindTotalPages = Math.max(1, Math.ceil(bindList.length / bindPageSize));
  const paginatedBind = useMemo(() => {
    const start = (bindPage - 1) * bindPageSize;
    return bindList.slice(start, start + bindPageSize);
  }, [bindList, bindPage, bindPageSize]);

  const blTotalPages = Math.max(1, Math.ceil(blList.length / blPageSize));
  const paginatedBl = useMemo(() => {
    const start = (blPage - 1) * blPageSize;
    return blList.slice(start, start + blPageSize);
  }, [blList, blPage, blPageSize]);

  // ARP sources for binding dropdown (arp_ssh / arp_api)
  const arpSourceOptions = useMemo(
    () => dsList.filter((ds) => (ds.type === 'arp_ssh' || ds.type === 'arp_api') && ds.enabled),
    [dsList],
  );
  // Firewall sources for binding dropdown (sangfor)
  const firewallOptions = useMemo(
    () => dsList.filter((ds) => ds.type === 'sangfor' && ds.enabled),
    [dsList],
  );

  // ---------------------------------------------------------------------------
  // Handlers - Data Sources
  // ---------------------------------------------------------------------------
  const handleDsTypeChange = (newType: string) => {
    setDsForm((prev) => ({ ...prev, type: newType }));
    // Reset config with defaults
    const fields = CONFIG_FIELDS[newType] || [];
    const defaults: Record<string, string> = {};
    fields.forEach((f) => {
      defaults[f.key] = f.defaultValue || '';
    });
    setDsConfig(defaults);
  };

  const handleAddDs = async () => {
    if (!dsForm.name.trim()) {
      toast.error('Please enter a name');
      return;
    }
    if (!dsForm.tag.trim()) {
      toast.error('Please enter a tag');
      return;
    }

    setIsAddingDs(true);
    try {
      // Build config object, parsing JSON fields
      const config: Record<string, any> = {};
      const fields = CONFIG_FIELDS[dsForm.type] || [];
      fields.forEach((f) => {
        const val = dsConfig[f.key];
        if (val === undefined || val === '') return;
        if (f.key === 'headers' || f.key === 'port' || f.key === 'verify_ssl') {
          try {
            config[f.key] = JSON.parse(val);
          } catch {
            if (f.key === 'port') config[f.key] = Number(val);
            else if (f.key === 'verify_ssl') config[f.key] = val === 'true';
            else config[f.key] = val;
          }
        } else {
          config[f.key] = val;
        }
      });

      await apiClient.post('/data-sources/', {
        name: dsForm.name,
        type: dsForm.type,
        tag: dsForm.tag,
        config,
        enabled: dsForm.enabled,
      });
      toast.success('Data source created successfully');
      setShowAddDsModal(false);
      resetDsForm();
      dsRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create data source');
    } finally {
      setIsAddingDs(false);
    }
  };

  const resetDsForm = () => {
    setDsForm({ name: '', type: 'arp_ssh', tag: '', enabled: true });
    setDsConfig({});
  };

  const handleDeleteDs = async () => {
    if (!deleteDsItem) return;
    setIsDeletingDs(true);
    try {
      await apiClient.delete(`/data-sources/${deleteDsItem.id}`);
      toast.success(`Data source "${deleteDsItem.name}" deleted`);
      dsRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to delete data source');
    } finally {
      setIsDeletingDs(false);
      setShowDeleteDsModal(false);
      setDeleteDsItem(null);
    }
  };

  const handleTestConnection = async (ds: DataSourceItem) => {
    setTestingId(ds.id);
    setTestResult(null);
    try {
      const response = await apiClient.post(`/data-sources/${ds.id}/test`);
      const data = response.data;
      setTestResult({ id: ds.id, success: data.success ?? true, message: data.message || data.detail || 'Connection successful' });
      if (data.success ?? true) {
        toast.success(`Connection to "${ds.name}" successful`);
      } else {
        toast.error(`Connection to "${ds.name}" failed: ${data.message || data.detail || 'Unknown error'}`);
      }
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.response?.data?.message || 'Connection failed';
      setTestResult({ id: ds.id, success: false, message: msg });
      toast.error(`Connection to "${ds.name}" failed: ${msg}`);
    } finally {
      setTestingId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Handlers - Edit Data Source
  // ---------------------------------------------------------------------------
  const openEditDsModal = (ds: DataSourceItem) => {
    setEditDsForm({
      id: ds.id,
      name: ds.name,
      type: ds.type,
      tag: ds.tag,
      enabled: ds.enabled,
    });
    // Populate config from existing data
    const fields = CONFIG_FIELDS[ds.type] || [];
    const configVals: Record<string, string> = {};
    const rawConfig = (ds as any).config || {};
    fields.forEach((f) => {
      const val = rawConfig[f.key];
      if (val === undefined || val === null) {
        configVals[f.key] = f.defaultValue || '';
      } else if (typeof val === 'object') {
        configVals[f.key] = JSON.stringify(val);
      } else {
        configVals[f.key] = String(val);
      }
    });
    setEditDsConfig(configVals);
    setShowEditDsModal(true);
  };

  const handleEditDsTypeChange = (newType: string) => {
    setEditDsForm((prev) => ({ ...prev, type: newType }));
    const fields = CONFIG_FIELDS[newType] || [];
    const defaults: Record<string, string> = {};
    fields.forEach((f) => {
      defaults[f.key] = editDsConfig[f.key] ?? f.defaultValue ?? '';
    });
    setEditDsConfig(defaults);
  };

  const handleEditDs = async () => {
    if (!editDsForm.name.trim()) {
      toast.error('Please enter a name');
      return;
    }
    if (!editDsForm.tag.trim()) {
      toast.error('Please enter a tag');
      return;
    }

    setIsEditingDs(true);
    try {
      const config: Record<string, any> = {};
      const fields = CONFIG_FIELDS[editDsForm.type] || [];
      fields.forEach((f) => {
        const val = editDsConfig[f.key];
        if (val === undefined || val === '') return;
        if (f.key === 'headers' || f.key === 'port' || f.key === 'verify_ssl') {
          try {
            config[f.key] = JSON.parse(val);
          } catch {
            if (f.key === 'port') config[f.key] = Number(val);
            else if (f.key === 'verify_ssl') config[f.key] = val === 'true';
            else config[f.key] = val;
          }
        } else {
          config[f.key] = val;
        }
      });

      await apiClient.put(`/data-sources/${editDsForm.id}`, {
        name: editDsForm.name,
        type: editDsForm.type,
        tag: editDsForm.tag,
        config,
        enabled: editDsForm.enabled,
      });
      toast.success('Data source updated successfully');
      setShowEditDsModal(false);
      dsRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update data source');
    } finally {
      setIsEditingDs(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Handlers - Sync Data Source
  // ---------------------------------------------------------------------------
  const handleSyncDs = async (ds: DataSourceItem) => {
    setSyncingId(ds.id);
    try {
      await apiClient.post(`/data-sources/${ds.id}/sync`);
      toast.success(`Data source "${ds.name}" synced successfully`);
      dsRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || `Failed to sync "${ds.name}"`);
    } finally {
      setSyncingId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Handlers - Compliance Baselines
  // ---------------------------------------------------------------------------
  const handleBlTypeChange = (newType: string) => {
    setBlForm((prev) => ({ ...prev, type: newType }));
    const fields = BASELINE_CONFIG_FIELDS[newType] || [];
    const defaults: Record<string, string> = {};
    fields.forEach((f) => {
      defaults[f.key] = f.defaultValue || '';
    });
    setBlConfig(defaults);
  };

  const handleAddBl = async () => {
    if (!blForm.name.trim()) {
      toast.error('Please enter a name');
      return;
    }
    if (!blForm.tag.trim()) {
      toast.error('Please enter a tag');
      return;
    }

    setIsAddingBl(true);
    try {
      const config: Record<string, any> = {};
      const fields = BASELINE_CONFIG_FIELDS[blForm.type] || [];
      fields.forEach((f) => {
        const val = blConfig[f.key];
        if (val === undefined || val === '') return;
        if (f.key === 'port') {
          config[f.key] = Number(val);
        } else {
          config[f.key] = val;
        }
      });

      await apiClient.post('/compliance-baselines/', {
        name: blForm.name,
        type: blForm.type,
        tag: blForm.tag,
        config,
        enabled: blForm.enabled,
      });
      toast.success('Compliance baseline created successfully');
      setShowAddBlModal(false);
      resetBlForm();
      blRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create compliance baseline');
    } finally {
      setIsAddingBl(false);
    }
  };

  const resetBlForm = () => {
    setBlForm({ name: '', type: 'ipguard', tag: '', enabled: true });
    setBlConfig({});
  };

  const handleDeleteBl = async () => {
    if (!deleteBlItem) return;
    setIsDeletingBl(true);
    try {
      await apiClient.delete(`/compliance-baselines/${deleteBlItem.id}`);
      toast.success(`Compliance baseline "${deleteBlItem.name}" deleted`);
      blRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to delete compliance baseline');
    } finally {
      setIsDeletingBl(false);
      setShowDeleteBlModal(false);
      setDeleteBlItem(null);
    }
  };

  const handleTestBlConnection = async (bl: ComplianceBaselineItem) => {
    setBlTestingId(bl.id);
    setBlTestResult(null);
    try {
      const response = await apiClient.post(`/compliance-baselines/${bl.id}/test`);
      const data = response.data;
      setBlTestResult({ id: bl.id, success: data.success ?? true, message: data.message || data.detail || 'Connection successful' });
      if (data.success ?? true) {
        toast.success(`Connection to "${bl.name}" successful`);
      } else {
        toast.error(`Connection to "${bl.name}" failed: ${data.message || data.detail || 'Unknown error'}`);
      }
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.response?.data?.message || 'Connection failed';
      setBlTestResult({ id: bl.id, success: false, message: msg });
      toast.error(`Connection to "${bl.name}" failed: ${msg}`);
    } finally {
      setBlTestingId(null);
    }
  };

  const openEditBlModal = (bl: ComplianceBaselineItem) => {
    setEditBlForm({
      id: bl.id,
      name: bl.name,
      type: bl.type,
      tag: bl.tag,
      enabled: bl.enabled,
    });
    const fields = BASELINE_CONFIG_FIELDS[bl.type] || [];
    const configVals: Record<string, string> = {};
    const rawConfig = (bl as any).config || {};
    fields.forEach((f) => {
      const val = rawConfig[f.key];
      if (val === undefined || val === null) {
        configVals[f.key] = f.defaultValue || '';
      } else if (typeof val === 'object') {
        configVals[f.key] = JSON.stringify(val);
      } else {
        configVals[f.key] = String(val);
      }
    });
    setEditBlConfig(configVals);
    setShowEditBlModal(true);
  };

  const handleEditBl = async () => {
    if (!editBlForm.name.trim()) {
      toast.error('Please enter a name');
      return;
    }
    if (!editBlForm.tag.trim()) {
      toast.error('Please enter a tag');
      return;
    }

    setIsEditingBl(true);
    try {
      const config: Record<string, any> = {};
      const fields = BASELINE_CONFIG_FIELDS[editBlForm.type] || [];
      fields.forEach((f) => {
        const val = editBlConfig[f.key];
        if (val === undefined || val === '') return;
        if (f.key === 'port') {
          config[f.key] = Number(val);
        } else {
          config[f.key] = val;
        }
      });

      await apiClient.put(`/compliance-baselines/${editBlForm.id}`, {
        name: editBlForm.name,
        type: editBlForm.type,
        tag: editBlForm.tag,
        config,
        enabled: editBlForm.enabled,
      });
      toast.success('Compliance baseline updated successfully');
      setShowEditBlModal(false);
      blRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update compliance baseline');
    } finally {
      setIsEditingBl(false);
    }
  };

  const handleSyncBl = async (bl: ComplianceBaselineItem) => {
    setBlSyncingId(bl.id);
    try {
      await apiClient.post(`/compliance-baselines/${bl.id}/sync`);
      toast.success(`Compliance baseline "${bl.name}" synced successfully`);
      blRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || `Failed to sync "${bl.name}"`);
    } finally {
      setBlSyncingId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Handlers - Bindings
  // ---------------------------------------------------------------------------
  const handleAddBinding = async () => {
    if (!bindForm.arp_source_tag) {
      toast.error('Please select an ARP source tag');
      return;
    }
    if (!bindForm.firewall_tag) {
      toast.error('Please select a firewall tag');
      return;
    }

    setIsAddingBind(true);
    try {
      await apiClient.post('/data-sources/bindings/', {
        arp_source_tag: bindForm.arp_source_tag,
        firewall_tag: bindForm.firewall_tag,
      });
      toast.success('Binding created successfully');
      setShowAddBindModal(false);
      setBindForm({ arp_source_tag: '', firewall_tag: '' });
      bindRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create binding');
    } finally {
      setIsAddingBind(false);
    }
  };

  const handleDeleteBinding = async () => {
    if (!deleteBindId) return;
    setIsDeletingBind(true);
    try {
      await apiClient.delete(`/data-sources/bindings/${deleteBindId}`);
      toast.success('Binding deleted');
      bindRefetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to delete binding');
    } finally {
      setIsDeletingBind(false);
      setShowDeleteBindModal(false);
      setDeleteBindId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  const renderTypeBadge = (type: string) => {
    const badge = TYPE_BADGE[type];
    if (!badge) return <span className="text-sm text-gray-400">{type}</span>;
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>
        {badge.label}
      </span>
    );
  };

  const renderEnabledBadge = (enabled: boolean) => (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${enabled ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
      {enabled ? 'Enabled' : 'Disabled'}
    </span>
  );

  const renderLastSync = (ds: DataSourceItem) => {
    if (!ds.last_sync_at) {
      return <span className="text-sm text-gray-400">Never</span>;
    }
    const statusColor = ds.last_sync_status === 'success'
      ? 'text-green-600'
      : ds.last_sync_status === 'failed'
        ? 'text-red-600'
        : 'text-gray-600';
    return (
      <div>
        <span className={`text-sm font-medium ${statusColor}`}>
          {ds.last_sync_status === 'success' ? 'Success' : ds.last_sync_status === 'failed' ? 'Failed' : ds.last_sync_status}
        </span>
        <div className="flex items-center text-xs text-gray-400 mt-0.5">
          <Clock className="h-3 w-3 mr-1" />
          {formatDate(ds.last_sync_at)}
        </div>
        {ds.last_sync_error && (
          <p className="text-xs text-red-500 mt-0.5 max-w-xs truncate" title={ds.last_sync_error}>
            {ds.last_sync_error}
          </p>
        )}
      </div>
    );
  };

  // ---------------------------------------------------------------------------
  // Config form for add modal
  // ---------------------------------------------------------------------------
  const renderConfigFields = () => {
    const fields = CONFIG_FIELDS[dsForm.type] || [];
    return fields.map((field) => (
      <div key={field.key}>
        <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
        {field.type === 'select' ? (
          <select
            value={dsConfig[field.key] ?? field.defaultValue ?? ''}
            onChange={(e) => setDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            {field.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        ) : (
          <input
            type={field.type}
            placeholder={field.placeholder}
            value={dsConfig[field.key] ?? field.defaultValue ?? ''}
            onChange={(e) => setDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
        )}
      </div>
    ));
  };

  // ---------------------------------------------------------------------------
  // JSX
  // ---------------------------------------------------------------------------
  return (
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Data Sources</h1>
          <p className="text-gray-600 mt-1">Manage data source connections and bindings</p>
        </div>
        <ButtonGroup>
          <PrimaryButton
            icon={RefreshCw}
            label="Refresh"
            variant="secondary"
            onClick={() => { dsRefetch(); bindRefetch(); blRefetch(); }}
          />
          {activeTab === 'sources' ? (
            <PrimaryButton
              icon={Plus}
              label="Add Data Source"
              variant="success"
              onClick={() => {
                resetDsForm();
                handleDsTypeChange('arp_ssh');
                setShowAddDsModal(true);
              }}
            />
          ) : activeTab === 'bindings' ? (
            <PrimaryButton
              icon={Link2}
              label="Add Binding"
              variant="success"
              onClick={() => {
                setBindForm({ arp_source_tag: '', firewall_tag: '' });
                setShowAddBindModal(true);
              }}
            />
          ) : activeTab === 'baselines' ? (
            <PrimaryButton
              icon={Plus}
              label="Add Baseline"
              variant="success"
              onClick={() => {
                resetBlForm();
                handleBlTypeChange('ipguard');
                setShowAddBlModal(true);
              }}
            />
          ) : null}
        </ButtonGroup>
      </div>

      {/* Tabs */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('sources')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'sources'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Database className="h-4 w-4 inline mr-2" />
            Data Sources
          </button>
          <button
            onClick={() => setActiveTab('bindings')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'bindings'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Link2 className="h-4 w-4 inline mr-2" />
            Bindings
          </button>
          <button
            onClick={() => setActiveTab('baselines')}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === 'baselines'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Shield className="h-4 w-4 inline mr-2" />
            Compliance Baselines
          </button>
        </nav>
      </div>

      {/* ===================== Data Sources Tab ===================== */}
      {activeTab === 'sources' && (
        <>
          {/* Table */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Name</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Type</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Tag</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Enabled</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Last Sync</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {dsLoading ? (
                    <tr>
                      <td colSpan={6}>
                        <LoadingState message="Loading data sources..." />
                      </td>
                    </tr>
                  ) : dsList.length === 0 ? (
                    <tr>
                      <td colSpan={6}>
                        <EmptyState
                          icon={Database}
                          title="No Data Sources"
                          description="Add a data source to connect to external systems"
                          action={{ label: 'Add Data Source', onClick: () => { resetDsForm(); handleDsTypeChange('arp_ssh'); setShowAddDsModal(true); } }}
                        />
                      </td>
                    </tr>
                  ) : (
                    paginatedDs.map((ds) => (
                      <tr key={ds.id} className="hover:bg-blue-50/30 transition-colors">
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <Server className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                            <span className="text-sm font-medium text-gray-900">{ds.name}</span>
                          </div>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          {renderTypeBadge(ds.type)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            {ds.tag}
                          </span>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          {renderEnabledBadge(ds.enabled)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          {renderLastSync(ds)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <ButtonGroup>
                            <IconButton
                              icon={testingId === ds.id ? RefreshCw : Plug}
                              variant="primary"
                              size="md"
                              title="Test Connection"
                              onClick={() => handleTestConnection(ds)}
                              loading={testingId === ds.id}
                            />
                            <IconButton
                              icon={Pencil}
                              variant="primary"
                              size="md"
                              title="Edit Data Source"
                              onClick={() => openEditDsModal(ds)}
                            />
                            <IconButton
                              icon={RefreshCw}
                              variant="secondary"
                              size="md"
                              title="Sync Data Source"
                              onClick={() => handleSyncDs(ds)}
                              loading={syncingId === ds.id}
                            />
                            <IconButton
                              icon={Trash2}
                              variant="danger"
                              size="md"
                              title="Delete Data Source"
                              onClick={() => { setDeleteDsItem(ds); setShowDeleteDsModal(true); }}
                            />
                          </ButtonGroup>
                          {/* Test result inline */}
                          {testResult && testResult.id === ds.id && (
                            <div className={`mt-1 text-xs flex items-center gap-1 ${testResult.success ? 'text-green-600' : 'text-red-600'}`}>
                              {testResult.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                              <span className="max-w-[200px] truncate" title={testResult.message}>{testResult.message}</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={dsPage}
              totalPages={dsTotalPages}
              onPageChange={setDsPage}
              pageSize={dsPageSize}
              onPageSizeChange={(s) => { setDsPageSize(s); setDsPage(1); }}
              totalItems={dsList.length}
              variant="bottom"
            />
          </div>
        </>
      )}

      {/* ===================== Bindings Tab ===================== */}
      {activeTab === 'bindings' && (
        <>
          {/* Table */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">ARP Source Tag</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Firewall Tag</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Created At</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {bindLoading ? (
                    <tr>
                      <td colSpan={4}>
                        <LoadingState message="Loading bindings..." />
                      </td>
                    </tr>
                  ) : bindList.length === 0 ? (
                    <tr>
                      <td colSpan={4}>
                        <EmptyState
                          icon={Link2}
                          title="No Bindings"
                          description="Create a binding to link ARP sources with firewalls"
                          action={{ label: 'Add Binding', onClick: () => { setBindForm({ arp_source_tag: '', firewall_tag: '' }); setShowAddBindModal(true); } }}
                        />
                      </td>
                    </tr>
                  ) : (
                    paginatedBind.map((b) => (
                      <tr key={b.id} className="hover:bg-blue-50/30 transition-colors">
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            {b.arp_source_tag}
                          </span>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                            {b.firewall_tag}
                          </span>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center text-sm text-gray-600">
                            <Clock className="h-4 w-4 mr-1.5 text-gray-400" />
                            {formatDate(b.created_at)}
                          </div>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <IconButton
                            icon={Trash2}
                            variant="danger"
                            size="md"
                            title="Delete Binding"
                            onClick={() => { setDeleteBindId(b.id); setShowDeleteBindModal(true); }}
                          />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={bindPage}
              totalPages={bindTotalPages}
              onPageChange={setBindPage}
              pageSize={bindPageSize}
              onPageSizeChange={(s) => { setBindPageSize(s); setBindPage(1); }}
              totalItems={bindList.length}
              variant="bottom"
            />
          </div>
        </>
      )}

      {/* ===================== Compliance Baselines Tab ===================== */}
      {activeTab === 'baselines' && (
        <>
          {/* Table */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Name</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Type</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Tag</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Enabled</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Last Sync</th>
                    <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {blLoading ? (
                    <tr>
                      <td colSpan={6}>
                        <LoadingState message="Loading compliance baselines..." />
                      </td>
                    </tr>
                  ) : blList.length === 0 ? (
                    <tr>
                      <td colSpan={6}>
                        <EmptyState
                          icon={Shield}
                          title="No Compliance Baselines"
                          description="Add a compliance baseline to connect to IP-Guard"
                          action={{ label: 'Add Baseline', onClick: () => { resetBlForm(); handleBlTypeChange('ipguard'); setShowAddBlModal(true); } }}
                        />
                      </td>
                    </tr>
                  ) : (
                    paginatedBl.map((bl) => (
                      <tr key={bl.id} className="hover:bg-blue-50/30 transition-colors">
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <Server className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                            <span className="text-sm font-medium text-gray-900">{bl.name}</span>
                          </div>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          {(() => {
                            const badge = BASELINE_TYPE_BADGE[bl.type];
                            if (!badge) return <span className="text-sm text-gray-400">{bl.type}</span>;
                            return (
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>
                                {badge.label}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            {bl.tag}
                          </span>
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          {renderEnabledBadge(bl.enabled)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          {renderLastSync(bl as any)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <ButtonGroup>
                            <IconButton
                              icon={blTestingId === bl.id ? RefreshCw : Plug}
                              variant="primary"
                              size="md"
                              title="Test Connection"
                              onClick={() => handleTestBlConnection(bl)}
                              loading={blTestingId === bl.id}
                            />
                            <IconButton
                              icon={Pencil}
                              variant="primary"
                              size="md"
                              title="Edit Baseline"
                              onClick={() => openEditBlModal(bl)}
                            />
                            <IconButton
                              icon={RefreshCw}
                              variant="secondary"
                              size="md"
                              title="Sync Baseline"
                              onClick={() => handleSyncBl(bl)}
                              loading={blSyncingId === bl.id}
                            />
                            <IconButton
                              icon={Trash2}
                              variant="danger"
                              size="md"
                              title="Delete Baseline"
                              onClick={() => { setDeleteBlItem(bl); setShowDeleteBlModal(true); }}
                            />
                          </ButtonGroup>
                          {/* Test result inline */}
                          {blTestResult && blTestResult.id === bl.id && (
                            <div className={`mt-1 text-xs flex items-center gap-1 ${blTestResult.success ? 'text-green-600' : 'text-red-600'}`}>
                              {blTestResult.success ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                              <span className="max-w-[200px] truncate" title={blTestResult.message}>{blTestResult.message}</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={blPage}
              totalPages={blTotalPages}
              onPageChange={setBlPage}
              pageSize={blPageSize}
              onPageSizeChange={(s) => { setBlPageSize(s); setBlPage(1); }}
              totalItems={blList.length}
              variant="bottom"
            />
          </div>
        </>
      )}

      {/* ===================== Add Data Source Modal ===================== */}
      {showAddDsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Add Data Source</h2>
            <p className="text-sm text-gray-500 mb-6">Configure a new data source connection</p>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  placeholder="My Data Source"
                  value={dsForm.name}
                  onChange={(e) => setDsForm((prev) => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <select
                  value={dsForm.type}
                  onChange={(e) => handleDsTypeChange(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="arp_ssh">ARP SSH</option>
                  <option value="arp_api">ARP API</option>
                  <option value="sangfor">Sangfor</option>
                </select>
              </div>

              {/* Tag */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tag</label>
                <input
                  type="text"
                  placeholder="unique-tag"
                  value={dsForm.tag}
                  onChange={(e) => setDsForm((prev) => ({ ...prev, tag: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Dynamic Config Fields */}
              {renderConfigFields()}

              {/* Enabled */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="ds-enabled"
                  checked={dsForm.enabled}
                  onChange={(e) => setDsForm((prev) => ({ ...prev, enabled: e.target.checked }))}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="ds-enabled" className="text-sm font-medium text-gray-700">Enabled</label>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <PrimaryButton
                  label="Cancel"
                  variant="secondary"
                  onClick={() => { setShowAddDsModal(false); resetDsForm(); }}
                  className="flex-1"
                />
                <PrimaryButton
                  icon={Plus}
                  label="Create"
                  variant="success"
                  onClick={handleAddDs}
                  loading={isAddingDs}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================== Delete Data Source Modal ===================== */}
      {showDeleteDsModal && deleteDsItem && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                <Trash2 className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Delete Data Source</h2>
                <p className="text-sm text-gray-500">This action cannot be undone</p>
              </div>
            </div>

            <p className="text-gray-700 mb-6">
              Are you sure you want to delete data source <span className="font-medium">{deleteDsItem.name}</span> (tag: <span className="font-mono">{deleteDsItem.tag}</span>)?
            </p>

            <div className="flex gap-3">
              <PrimaryButton
                label="Cancel"
                variant="secondary"
                onClick={() => { setShowDeleteDsModal(false); setDeleteDsItem(null); }}
                className="flex-1"
              />
              <PrimaryButton
                icon={Trash2}
                label="Delete"
                variant="danger"
                onClick={handleDeleteDs}
                loading={isDeletingDs}
                className="flex-1"
              />
            </div>
          </div>
        </div>
      )}

      {/* ===================== Edit Data Source Modal ===================== */}
      {showEditDsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Edit Data Source</h2>
            <p className="text-sm text-gray-500 mb-6">Update data source connection settings</p>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  placeholder="My Data Source"
                  value={editDsForm.name}
                  onChange={(e) => setEditDsForm((prev) => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <select
                  value={editDsForm.type}
                  onChange={(e) => handleEditDsTypeChange(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="arp_ssh">ARP SSH</option>
                  <option value="arp_api">ARP API</option>
                  <option value="sangfor">Sangfor</option>
                </select>
              </div>

              {/* Tag */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tag</label>
                <input
                  type="text"
                  placeholder="unique-tag"
                  value={editDsForm.tag}
                  onChange={(e) => setEditDsForm((prev) => ({ ...prev, tag: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Dynamic Config Fields */}
              {(CONFIG_FIELDS[editDsForm.type] || []).map((field) => (
                <div key={field.key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
                  {field.type === 'select' ? (
                    <select
                      value={editDsConfig[field.key] ?? field.defaultValue ?? ''}
                      onChange={(e) => setEditDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    >
                      {field.options?.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={field.type}
                      placeholder={field.placeholder}
                      value={editDsConfig[field.key] ?? field.defaultValue ?? ''}
                      onChange={(e) => setEditDsConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  )}
                </div>
              ))}

              {/* Enabled */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="edit-ds-enabled"
                  checked={editDsForm.enabled}
                  onChange={(e) => setEditDsForm((prev) => ({ ...prev, enabled: e.target.checked }))}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="edit-ds-enabled" className="text-sm font-medium text-gray-700">Enabled</label>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <PrimaryButton
                  label="Cancel"
                  variant="secondary"
                  onClick={() => setShowEditDsModal(false)}
                  className="flex-1"
                />
                <PrimaryButton
                  icon={Pencil}
                  label="Update"
                  variant="primary"
                  onClick={handleEditDs}
                  loading={isEditingDs}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================== Add Binding Modal ===================== */}
      {showAddBindModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Add Binding</h2>
            <p className="text-sm text-gray-500 mb-6">Link an ARP source with a firewall</p>

            <div className="space-y-4">
              {/* ARP Source Tag */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">ARP Source Tag</label>
                <select
                  value={bindForm.arp_source_tag}
                  onChange={(e) => setBindForm((prev) => ({ ...prev, arp_source_tag: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="">Select ARP source...</option>
                  {arpSourceOptions.map((ds) => (
                    <option key={ds.id} value={ds.tag}>
                      {ds.tag} ({ds.name} - {TYPE_BADGE[ds.type]?.label || ds.type})
                    </option>
                  ))}
                </select>
                {arpSourceOptions.length === 0 && (
                  <p className="mt-1 text-xs text-amber-600">No enabled ARP sources available. Please add one first.</p>
                )}
              </div>

              {/* Firewall Tag */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Firewall Tag</label>
                <select
                  value={bindForm.firewall_tag}
                  onChange={(e) => setBindForm((prev) => ({ ...prev, firewall_tag: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="">Select firewall...</option>
                  {firewallOptions.map((ds) => (
                    <option key={ds.id} value={ds.tag}>
                      {ds.tag} ({ds.name})
                    </option>
                  ))}
                </select>
                {firewallOptions.length === 0 && (
                  <p className="mt-1 text-xs text-amber-600">No enabled Sangfor sources available. Please add one first.</p>
                )}
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <PrimaryButton
                  label="Cancel"
                  variant="secondary"
                  onClick={() => { setShowAddBindModal(false); setBindForm({ arp_source_tag: '', firewall_tag: '' }); }}
                  className="flex-1"
                />
                <PrimaryButton
                  icon={Link2}
                  label="Create Binding"
                  variant="success"
                  onClick={handleAddBinding}
                  loading={isAddingBind}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================== Delete Binding Modal ===================== */}
      {showDeleteBindModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                <Trash2 className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Delete Binding</h2>
                <p className="text-sm text-gray-500">This action cannot be undone</p>
              </div>
            </div>

            <p className="text-gray-700 mb-6">
              Are you sure you want to delete this binding?
            </p>

            <div className="flex gap-3">
              <PrimaryButton
                label="Cancel"
                variant="secondary"
                onClick={() => { setShowDeleteBindModal(false); setDeleteBindId(null); }}
                className="flex-1"
              />
              <PrimaryButton
                icon={Trash2}
                label="Delete"
                variant="danger"
                onClick={handleDeleteBinding}
                loading={isDeletingBind}
                className="flex-1"
              />
            </div>
          </div>
        </div>
      )}

      {/* ===================== Add Compliance Baseline Modal ===================== */}
      {showAddBlModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Add Compliance Baseline</h2>
            <p className="text-sm text-gray-500 mb-6">Configure a new compliance baseline connection</p>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  placeholder="My Compliance Baseline"
                  value={blForm.name}
                  onChange={(e) => setBlForm((prev) => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <select
                  value={blForm.type}
                  onChange={(e) => handleBlTypeChange(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="ipguard">IP-Guard</option>
                </select>
              </div>

              {/* Tag */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tag</label>
                <input
                  type="text"
                  placeholder="unique-tag"
                  value={blForm.tag}
                  onChange={(e) => setBlForm((prev) => ({ ...prev, tag: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Dynamic Config Fields */}
              {(BASELINE_CONFIG_FIELDS[blForm.type] || []).map((field) => (
                <div key={field.key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
                  {field.type === 'select' ? (
                    <select
                      value={blConfig[field.key] ?? field.defaultValue ?? ''}
                      onChange={(e) => setBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    >
                      {field.options?.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={field.type}
                      placeholder={field.placeholder}
                      value={blConfig[field.key] ?? field.defaultValue ?? ''}
                      onChange={(e) => setBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  )}
                </div>
              ))}

              {/* Enabled */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="bl-enabled"
                  checked={blForm.enabled}
                  onChange={(e) => setBlForm((prev) => ({ ...prev, enabled: e.target.checked }))}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="bl-enabled" className="text-sm font-medium text-gray-700">Enabled</label>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <PrimaryButton
                  label="Cancel"
                  variant="secondary"
                  onClick={() => { setShowAddBlModal(false); resetBlForm(); }}
                  className="flex-1"
                />
                <PrimaryButton
                  icon={Plus}
                  label="Create"
                  variant="success"
                  onClick={handleAddBl}
                  loading={isAddingBl}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================== Edit Compliance Baseline Modal ===================== */}
      {showEditBlModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Edit Compliance Baseline</h2>
            <p className="text-sm text-gray-500 mb-6">Update compliance baseline connection settings</p>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  placeholder="My Compliance Baseline"
                  value={editBlForm.name}
                  onChange={(e) => setEditBlForm((prev) => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <select
                  value={editBlForm.type}
                  onChange={(e) => {
                    setEditBlForm((prev) => ({ ...prev, type: e.target.value }));
                    const fields = BASELINE_CONFIG_FIELDS[e.target.value] || [];
                    const defaults: Record<string, string> = {};
                    fields.forEach((f) => {
                      defaults[f.key] = editBlConfig[f.key] ?? f.defaultValue ?? '';
                    });
                    setEditBlConfig(defaults);
                  }}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                >
                  <option value="ipguard">IP-Guard</option>
                </select>
              </div>

              {/* Tag */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tag</label>
                <input
                  type="text"
                  placeholder="unique-tag"
                  value={editBlForm.tag}
                  onChange={(e) => setEditBlForm((prev) => ({ ...prev, tag: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
              </div>

              {/* Dynamic Config Fields */}
              {(BASELINE_CONFIG_FIELDS[editBlForm.type] || []).map((field) => (
                <div key={field.key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
                  {field.type === 'select' ? (
                    <select
                      value={editBlConfig[field.key] ?? field.defaultValue ?? ''}
                      onChange={(e) => setEditBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    >
                      {field.options?.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={field.type}
                      placeholder={field.placeholder}
                      value={editBlConfig[field.key] ?? field.defaultValue ?? ''}
                      onChange={(e) => setEditBlConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  )}
                </div>
              ))}

              {/* Enabled */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="edit-bl-enabled"
                  checked={editBlForm.enabled}
                  onChange={(e) => setEditBlForm((prev) => ({ ...prev, enabled: e.target.checked }))}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="edit-bl-enabled" className="text-sm font-medium text-gray-700">Enabled</label>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <PrimaryButton
                  label="Cancel"
                  variant="secondary"
                  onClick={() => setShowEditBlModal(false)}
                  className="flex-1"
                />
                <PrimaryButton
                  icon={Pencil}
                  label="Update"
                  variant="primary"
                  onClick={handleEditBl}
                  loading={isEditingBl}
                  className="flex-1"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================== Delete Compliance Baseline Modal ===================== */}
      {showDeleteBlModal && deleteBlItem && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                <Trash2 className="h-6 w-6 text-red-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Delete Compliance Baseline</h2>
                <p className="text-sm text-gray-500">This action cannot be undone</p>
              </div>
            </div>

            <p className="text-gray-700 mb-6">
              Are you sure you want to delete compliance baseline <span className="font-medium">{deleteBlItem.name}</span> (tag: <span className="font-mono">{deleteBlItem.tag}</span>)?
            </p>

            <div className="flex gap-3">
              <PrimaryButton
                label="Cancel"
                variant="secondary"
                onClick={() => { setShowDeleteBlModal(false); setDeleteBlItem(null); }}
                className="flex-1"
              />
              <PrimaryButton
                icon={Trash2}
                label="Delete"
                variant="danger"
                onClick={handleDeleteBl}
                loading={isDeletingBl}
                className="flex-1"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DataSources;
