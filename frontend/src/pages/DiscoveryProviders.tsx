import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  PlayIcon,
  PauseIcon,
  ArrowPathIcon,
  BeakerIcon,
  XMarkIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { discoveryProviderApi } from '../services/api';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import { LoadingPage } from '../components/common/Loading';
import type {
  DiscoveryProvider,
  DiscoveryProviderType,
  DiscoveryProviderStatus,
  DiscoveryProviderCreate,
  DiscoveryProviderSummary,
} from '../types';

interface ProviderFormData {
  name: string;
  display_name: string;
  provider_type: DiscoveryProviderType;
  api_url: string;
  username: string;
  password: string;
  verify_ssl: boolean;
  timeout_seconds: number;
  is_enabled: boolean;
  priority: number;
  sync_interval_minutes: number;
  // Kubernetes specific
  cluster_name: string;
  namespace: string;
  token: string;
  ca_cert: string;
  // vCenter specific
  include_tags: boolean;
}

const initialFormData: ProviderFormData = {
  name: '',
  display_name: '',
  provider_type: 'kubernetes',
  api_url: '',
  username: '',
  password: '',
  verify_ssl: true,
  timeout_seconds: 15,
  is_enabled: true,
  priority: 100,
  sync_interval_minutes: 15,
  cluster_name: 'default-cluster',
  namespace: '',
  token: '',
  ca_cert: '',
  include_tags: true,
};

const providerTypeLabels: Record<DiscoveryProviderType, string> = {
  kubernetes: 'Kubernetes',
  vcenter: 'vCenter',
  nutanix: 'Nutanix',
};

const statusConfig: Record<DiscoveryProviderStatus, { label: string; variant: 'success' | 'warning' | 'error' | 'default' }> = {
  idle: { label: 'Idle', variant: 'default' },
  running: { label: 'Running', variant: 'warning' },
  success: { label: 'Success', variant: 'success' },
  failed: { label: 'Failed', variant: 'error' },
};

function formatDate(dateString: string | null): string {
  if (!dateString) return 'Never';
  return new Date(dateString).toLocaleString();
}

export default function DiscoveryProviders() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<DiscoveryProvider | null>(null);
  const [formData, setFormData] = useState<ProviderFormData>(initialFormData);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Fetch discovery providers
  const { data: providersData, isLoading } = useQuery({
    queryKey: ['discovery-providers'],
    queryFn: () => discoveryProviderApi.list(),
    refetchInterval: 10000, // Refresh every 10 seconds to update status
  });

  // Create provider mutation
  const createMutation = useMutation({
    mutationFn: (data: DiscoveryProviderCreate) => discoveryProviderApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-providers'] });
      closeModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  // Update provider mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<DiscoveryProviderCreate> }) =>
      discoveryProviderApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-providers'] });
      closeModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  // Delete provider mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => discoveryProviderApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-providers'] });
    },
  });

  // Enable provider mutation
  const enableMutation = useMutation({
    mutationFn: (id: string) => discoveryProviderApi.enable(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-providers'] });
    },
  });

  // Disable provider mutation
  const disableMutation = useMutation({
    mutationFn: (id: string) => discoveryProviderApi.disable(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-providers'] });
    },
  });

  // Sync provider mutation
  const syncMutation = useMutation({
    mutationFn: (id: string) => discoveryProviderApi.sync(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discovery-providers'] });
    },
  });

  // Test connection mutation
  const testMutation = useMutation({
    mutationFn: (id: string) => discoveryProviderApi.test(id),
    onSuccess: (result) => {
      setTestResult({ success: result.success, message: result.message });
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setTestResult({ success: false, message: err.response?.data?.detail || err.message });
    },
  });

  const openCreateModal = () => {
    setEditingProvider(null);
    setFormData(initialFormData);
    setError(null);
    setTestResult(null);
    setIsModalOpen(true);
  };

  const openEditModal = async (provider: DiscoveryProviderSummary) => {
    try {
      const fullProvider = await discoveryProviderApi.get(provider.id);
      setEditingProvider(fullProvider);
      setFormData({
        name: fullProvider.name,
        display_name: fullProvider.display_name || '',
        provider_type: fullProvider.provider_type,
        api_url: fullProvider.api_url,
        username: fullProvider.username || '',
        password: '',
        verify_ssl: fullProvider.verify_ssl,
        timeout_seconds: fullProvider.timeout_seconds,
        is_enabled: fullProvider.is_enabled,
        priority: fullProvider.priority,
        sync_interval_minutes: fullProvider.sync_interval_minutes,
        cluster_name: fullProvider.kubernetes_config?.cluster_name || 'default-cluster',
        namespace: fullProvider.kubernetes_config?.namespace || '',
        token: '',
        ca_cert: fullProvider.kubernetes_config?.ca_cert || '',
        include_tags: fullProvider.vcenter_config?.include_tags ?? true,
      });
      setError(null);
      setTestResult(null);
      setIsModalOpen(true);
    } catch (err) {
      console.error('Failed to fetch provider details', err);
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingProvider(null);
    setFormData(initialFormData);
    setError(null);
    setTestResult(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const createData: DiscoveryProviderCreate = {
      name: formData.name,
      display_name: formData.display_name || undefined,
      provider_type: formData.provider_type,
      api_url: formData.api_url,
      username: formData.username || undefined,
      password: formData.password || undefined,
      verify_ssl: formData.verify_ssl,
      timeout_seconds: formData.timeout_seconds,
      is_enabled: formData.is_enabled,
      priority: formData.priority,
      sync_interval_minutes: formData.sync_interval_minutes,
    };

    // Add type-specific config
    if (formData.provider_type === 'kubernetes') {
      createData.kubernetes_config = {
        cluster_name: formData.cluster_name,
        namespace: formData.namespace || null,
        token: formData.token || null,
        ca_cert: formData.ca_cert || null,
      };
    } else if (formData.provider_type === 'vcenter') {
      createData.vcenter_config = {
        include_tags: formData.include_tags,
      };
    } else if (formData.provider_type === 'nutanix') {
      createData.nutanix_config = {};
    }

    if (editingProvider) {
      updateMutation.mutate({ id: editingProvider.id, data: createData });
    } else {
      createMutation.mutate(createData);
    }
  };

  const handleDelete = (provider: DiscoveryProviderSummary) => {
    if (confirm(`Are you sure you want to delete the discovery provider "${provider.name}"?`)) {
      deleteMutation.mutate(provider.id);
    }
  };

  const handleToggleEnabled = (provider: DiscoveryProviderSummary) => {
    if (provider.is_enabled) {
      disableMutation.mutate(provider.id);
    } else {
      enableMutation.mutate(provider.id);
    }
  };

  const handleSync = (provider: DiscoveryProviderSummary) => {
    syncMutation.mutate(provider.id);
  };

  const handleTest = () => {
    if (editingProvider) {
      testMutation.mutate(editingProvider.id);
    }
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  const providers = providersData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Discovery Providers</h1>
          <p className="text-slate-400 mt-1">
            Configure Kubernetes, vCenter, and Nutanix integrations for asset discovery
          </p>
        </div>
        <Button onClick={openCreateModal} className="flex items-center gap-2">
          <PlusIcon className="w-4 h-4" />
          Add Provider
        </Button>
      </div>

      {/* Summary Card */}
      <Card>
        <div className="p-6">
          <div className="grid grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-slate-400">Total Providers</p>
              <p className="text-2xl font-semibold text-white">{providers.length}</p>
            </div>
            <div>
              <p className="text-sm text-slate-400">Active</p>
              <p className="text-2xl font-semibold text-green-400">
                {providers.filter((p) => p.is_enabled).length}
              </p>
            </div>
            <div>
              <p className="text-sm text-slate-400">Total Assets</p>
              <p className="text-2xl font-semibold text-white">
                {providers.reduce((sum, p) => sum + p.assets_discovered, 0)}
              </p>
            </div>
            <div>
              <p className="text-sm text-slate-400">Running Syncs</p>
              <p className="text-2xl font-semibold text-yellow-400">
                {providers.filter((p) => p.status === 'running').length}
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* Providers Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Name</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Type</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">API URL</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Status</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Assets</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Last Sync</th>
                <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {providers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No discovery providers configured. Add a provider to start discovering assets.
                  </td>
                </tr>
              ) : (
                providers.map((provider) => (
                  <tr key={provider.id} className="border-b border-slate-700/50 hover:bg-slate-800/50">
                    <td className="px-4 py-3">
                      <div>
                        <span className="text-white font-medium">{provider.name}</span>
                        {provider.display_name && (
                          <p className="text-slate-500 text-xs">{provider.display_name}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="info">{providerTypeLabels[provider.provider_type]}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-300 text-sm font-mono truncate max-w-xs block">
                        {provider.api_url}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Badge variant={statusConfig[provider.status].variant}>
                          {statusConfig[provider.status].label}
                        </Badge>
                        {!provider.is_enabled && (
                          <Badge variant="default">Disabled</Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-300">{provider.assets_discovered}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-400 text-sm">
                        {formatDate(provider.last_success_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleSync(provider)}
                          disabled={!provider.is_enabled || provider.status === 'running'}
                          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                          title="Trigger sync"
                        >
                          <ArrowPathIcon className={`w-4 h-4 ${provider.status === 'running' ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                          onClick={() => handleToggleEnabled(provider)}
                          className={`p-1.5 hover:bg-slate-700 rounded transition-colors ${
                            provider.is_enabled
                              ? 'text-green-400 hover:text-green-300'
                              : 'text-slate-400 hover:text-white'
                          }`}
                          title={provider.is_enabled ? 'Disable provider' : 'Enable provider'}
                        >
                          {provider.is_enabled ? (
                            <PauseIcon className="w-4 h-4" />
                          ) : (
                            <PlayIcon className="w-4 h-4" />
                          )}
                        </button>
                        <button
                          onClick={() => openEditModal(provider)}
                          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded transition-colors"
                          title="Edit provider"
                        >
                          <PencilIcon className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(provider)}
                          className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded transition-colors"
                          title="Delete provider"
                        >
                          <TrashIcon className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Create/Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 overflow-y-auto py-8">
          <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-full max-w-2xl mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
              <h2 className="text-lg font-semibold text-white">
                {editingProvider ? 'Edit Discovery Provider' : 'Add Discovery Provider'}
              </h2>
              <button
                onClick={closeModal}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}

              {testResult && (
                <div
                  className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
                    testResult.success
                      ? 'bg-green-500/10 border border-green-500/50 text-green-400'
                      : 'bg-red-500/10 border border-red-500/50 text-red-400'
                  }`}
                >
                  {testResult.success ? (
                    <CheckCircleIcon className="w-5 h-5" />
                  ) : (
                    <ExclamationCircleIcon className="w-5 h-5" />
                  )}
                  {testResult.message}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Provider Name *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="prod-k8s-cluster"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Provider Type
                  </label>
                  <select
                    value={formData.provider_type}
                    onChange={(e) => setFormData({ ...formData, provider_type: e.target.value as DiscoveryProviderType })}
                    disabled={!!editingProvider}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  >
                    <option value="kubernetes">Kubernetes</option>
                    <option value="vcenter">vCenter</option>
                    <option value="nutanix">Nutanix</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Display Name
                </label>
                <input
                  type="text"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Production Kubernetes Cluster"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  API URL *
                </label>
                <input
                  type="url"
                  value={formData.api_url}
                  onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder={
                    formData.provider_type === 'kubernetes'
                      ? 'https://kubernetes.example.com:6443'
                      : formData.provider_type === 'vcenter'
                      ? 'https://vcenter.example.com'
                      : 'https://nutanix.example.com:9440'
                  }
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Username
                  </label>
                  <input
                    type="text"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder={formData.provider_type === 'kubernetes' ? '' : 'admin@example.com'}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder={editingProvider ? '(unchanged)' : ''}
                  />
                </div>
              </div>

              {/* Kubernetes specific fields */}
              {formData.provider_type === 'kubernetes' && (
                <div className="border-t border-slate-700 pt-4 space-y-4">
                  <h3 className="text-sm font-medium text-white">Kubernetes Configuration</h3>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Cluster Name
                      </label>
                      <input
                        type="text"
                        value={formData.cluster_name}
                        onChange={(e) => setFormData({ ...formData, cluster_name: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        placeholder="default-cluster"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">
                        Namespace (optional)
                      </label>
                      <input
                        type="text"
                        value={formData.namespace}
                        onChange={(e) => setFormData({ ...formData, namespace: e.target.value })}
                        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                        placeholder="Leave empty for all namespaces"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Service Account Token
                    </label>
                    <textarea
                      value={formData.token}
                      onChange={(e) => setFormData({ ...formData, token: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                      placeholder={editingProvider ? '(unchanged)' : 'eyJhbGciOiJSUzI1NiIsImtp...'}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      CA Certificate (optional)
                    </label>
                    <textarea
                      value={formData.ca_cert}
                      onChange={(e) => setFormData({ ...formData, ca_cert: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                      placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                    />
                  </div>
                </div>
              )}

              {/* vCenter specific fields */}
              {formData.provider_type === 'vcenter' && (
                <div className="border-t border-slate-700 pt-4">
                  <h3 className="text-sm font-medium text-white mb-3">vCenter Configuration</h3>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="include_tags"
                      checked={formData.include_tags}
                      onChange={(e) => setFormData({ ...formData, include_tags: e.target.checked })}
                      className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                    />
                    <label htmlFor="include_tags" className="text-slate-300 text-sm">
                      Include vSphere tags
                    </label>
                  </div>
                </div>
              )}

              {/* Common settings */}
              <div className="border-t border-slate-700 pt-4 space-y-4">
                <h3 className="text-sm font-medium text-white">Settings</h3>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Priority
                    </label>
                    <input
                      type="number"
                      value={formData.priority}
                      onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 100 })}
                      min={1}
                      max={1000}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                    <p className="text-slate-500 text-xs mt-1">Lower = higher priority</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Sync Interval (min)
                    </label>
                    <input
                      type="number"
                      value={formData.sync_interval_minutes}
                      onChange={(e) => setFormData({ ...formData, sync_interval_minutes: parseInt(e.target.value) || 15 })}
                      min={5}
                      max={1440}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Timeout (sec)
                    </label>
                    <input
                      type="number"
                      value={formData.timeout_seconds}
                      onChange={(e) => setFormData({ ...formData, timeout_seconds: parseInt(e.target.value) || 15 })}
                      min={1}
                      max={60}
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="verify_ssl"
                      checked={formData.verify_ssl}
                      onChange={(e) => setFormData({ ...formData, verify_ssl: e.target.checked })}
                      className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                    />
                    <label htmlFor="verify_ssl" className="text-slate-300 text-sm">
                      Verify SSL certificates
                    </label>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="is_enabled"
                      checked={formData.is_enabled}
                      onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                      className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                    />
                    <label htmlFor="is_enabled" className="text-slate-300 text-sm">
                      Enable provider
                    </label>
                  </div>
                </div>
              </div>

              <div className="flex justify-between gap-3 pt-4 border-t border-slate-700">
                <div>
                  {editingProvider && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleTest}
                      loading={testMutation.isPending}
                      className="flex items-center gap-2"
                    >
                      <BeakerIcon className="w-4 h-4" />
                      Test Connection
                    </Button>
                  )}
                </div>
                <div className="flex gap-3">
                  <Button type="button" variant="secondary" onClick={closeModal}>
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    loading={createMutation.isPending || updateMutation.isPending}
                  >
                    {editingProvider ? 'Save Changes' : 'Add Provider'}
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
