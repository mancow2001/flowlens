import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  CheckIcon,
  XMarkIcon,
  DocumentDuplicateIcon,
  ArrowDownTrayIcon,
} from '@heroicons/react/24/outline';
import { samlProviderApi, authApi } from '../services/api';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import { LoadingPage } from '../components/common/Loading';
import type { SAMLProvider, SAMLProviderType, UserRole } from '../types';

interface ProviderFormData {
  name: string;
  provider_type: SAMLProviderType;
  entity_id: string;
  sso_url: string;
  slo_url: string;
  certificate: string;
  sp_entity_id: string;
  role_attribute: string;
  role_mapping: Record<string, string>;
  default_role: UserRole;
  auto_provision_users: boolean;
}

const initialFormData: ProviderFormData = {
  name: '',
  provider_type: 'azure_ad',
  entity_id: '',
  sso_url: '',
  slo_url: '',
  certificate: '',
  sp_entity_id: window.location.origin + '/api/v1/auth/saml/metadata',
  role_attribute: '',
  role_mapping: {},
  default_role: 'viewer',
  auto_provision_users: true,
};

const providerTypeLabels: Record<SAMLProviderType, string> = {
  azure_ad: 'Azure AD',
  okta: 'Okta',
  ping_identity: 'Ping Identity',
};

export default function SAMLConfiguration() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<SAMLProvider | null>(null);
  const [formData, setFormData] = useState<ProviderFormData>(initialFormData);
  const [roleMappingInput, setRoleMappingInput] = useState({ key: '', value: 'viewer' });
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Fetch auth status to check if SAML is enabled
  const { data: authStatus } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.getStatus,
  });

  // Fetch SAML providers
  const { data: providersData, isLoading } = useQuery({
    queryKey: ['saml-providers'],
    queryFn: () => samlProviderApi.list(),
  });

  // Create provider mutation
  const createMutation = useMutation({
    mutationFn: (data: ProviderFormData) => samlProviderApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saml-providers'] });
      queryClient.invalidateQueries({ queryKey: ['auth-status'] });
      closeModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  // Update provider mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ProviderFormData> }) =>
      samlProviderApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saml-providers'] });
      queryClient.invalidateQueries({ queryKey: ['auth-status'] });
      closeModal();
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || err.message);
    },
  });

  // Delete provider mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => samlProviderApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saml-providers'] });
      queryClient.invalidateQueries({ queryKey: ['auth-status'] });
    },
  });

  // Activate provider mutation
  const activateMutation = useMutation({
    mutationFn: (id: string) => samlProviderApi.activate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saml-providers'] });
      queryClient.invalidateQueries({ queryKey: ['auth-status'] });
    },
  });

  const openCreateModal = () => {
    setEditingProvider(null);
    setFormData(initialFormData);
    setError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (provider: SAMLProvider) => {
    setEditingProvider(provider);
    setFormData({
      name: provider.name,
      provider_type: provider.provider_type,
      entity_id: provider.entity_id,
      sso_url: provider.sso_url,
      slo_url: provider.slo_url || '',
      certificate: provider.certificate,
      sp_entity_id: provider.sp_entity_id,
      role_attribute: provider.role_attribute || '',
      role_mapping: provider.role_mapping || {},
      default_role: provider.default_role,
      auto_provision_users: provider.auto_provision_users,
    });
    setError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingProvider(null);
    setFormData(initialFormData);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (editingProvider) {
      updateMutation.mutate({ id: editingProvider.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
  };

  const handleDelete = (provider: SAMLProvider) => {
    if (confirm(`Are you sure you want to delete the SAML provider "${provider.name}"?`)) {
      deleteMutation.mutate(provider.id);
    }
  };

  const handleActivate = (provider: SAMLProvider) => {
    activateMutation.mutate(provider.id);
  };

  const addRoleMapping = () => {
    if (roleMappingInput.key && roleMappingInput.value) {
      setFormData({
        ...formData,
        role_mapping: {
          ...formData.role_mapping,
          [roleMappingInput.key]: roleMappingInput.value,
        },
      });
      setRoleMappingInput({ key: '', value: 'viewer' });
    }
  };

  const removeRoleMapping = (key: string) => {
    const newMapping = { ...formData.role_mapping };
    delete newMapping[key];
    setFormData({ ...formData, role_mapping: newMapping });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  const providers = providersData?.items ?? [];
  const activeProvider = providers.find((p) => p.is_active);
  const spMetadataUrl = `${window.location.origin}/api/v1/auth/saml/metadata`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">SAML Configuration</h1>
          <p className="text-slate-400 mt-1">Configure Single Sign-On with SAML 2.0</p>
        </div>
        <Button onClick={openCreateModal} className="flex items-center gap-2">
          <PlusIcon className="w-4 h-4" />
          Add Provider
        </Button>
      </div>

      {/* Status Card */}
      <Card>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white">SAML Status</h2>
              <p className="text-slate-400 text-sm mt-1">
                {authStatus?.saml_enabled
                  ? `Active provider: ${activeProvider?.name || 'Unknown'}`
                  : 'SAML is not enabled or no provider is active'}
              </p>
            </div>
            <Badge variant={authStatus?.saml_enabled ? 'success' : 'default'}>
              {authStatus?.saml_enabled ? 'Enabled' : 'Disabled'}
            </Badge>
          </div>

          {/* SP Metadata URL */}
          <div className="mt-4 p-4 bg-slate-700/50 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-300">Service Provider Metadata URL</p>
                <p className="text-sm text-slate-400 mt-1 font-mono">{spMetadataUrl}</p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => copyToClipboard(spMetadataUrl)}
                >
                  <DocumentDuplicateIcon className="w-4 h-4" />
                  {copied ? 'Copied!' : 'Copy'}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => window.open(spMetadataUrl, '_blank')}
                >
                  <ArrowDownTrayIcon className="w-4 h-4" />
                  Download
                </Button>
              </div>
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
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Entity ID</th>
                <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">Status</th>
                <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {providers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    No SAML providers configured. Add a provider to enable SSO.
                  </td>
                </tr>
              ) : (
                providers.map((provider) => (
                  <tr key={provider.id} className="border-b border-slate-700/50 hover:bg-slate-800/50">
                    <td className="px-4 py-3">
                      <span className="text-white font-medium">{provider.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="info">
                        {providerTypeLabels[provider.provider_type]}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-slate-300 text-sm font-mono truncate max-w-xs block">
                        {provider.entity_id}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={provider.is_active ? 'success' : 'default'}>
                        {provider.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {!provider.is_active && (
                          <button
                            onClick={() => handleActivate(provider)}
                            className="p-1.5 text-slate-400 hover:text-green-400 hover:bg-slate-700 rounded transition-colors"
                            title="Activate provider"
                          >
                            <CheckIcon className="w-4 h-4" />
                          </button>
                        )}
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
                {editingProvider ? 'Edit SAML Provider' : 'Add SAML Provider'}
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

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Provider Name
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="My IdP"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Provider Type
                  </label>
                  <select
                    value={formData.provider_type}
                    onChange={(e) => setFormData({ ...formData, provider_type: e.target.value as SAMLProviderType })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="azure_ad">Azure AD</option>
                    <option value="okta">Okta</option>
                    <option value="ping_identity">Ping Identity</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  IdP Entity ID
                </label>
                <input
                  type="text"
                  value={formData.entity_id}
                  onChange={(e) => setFormData({ ...formData, entity_id: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="https://idp.example.com/entity"
                />
                <p className="text-slate-500 text-xs mt-1">
                  The Entity ID of your Identity Provider
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  SSO URL
                </label>
                <input
                  type="url"
                  value={formData.sso_url}
                  onChange={(e) => setFormData({ ...formData, sso_url: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="https://idp.example.com/sso"
                />
                <p className="text-slate-500 text-xs mt-1">
                  Single Sign-On service URL
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  SLO URL (Optional)
                </label>
                <input
                  type="url"
                  value={formData.slo_url}
                  onChange={(e) => setFormData({ ...formData, slo_url: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="https://idp.example.com/slo"
                />
                <p className="text-slate-500 text-xs mt-1">
                  Single Logout service URL (optional)
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  X.509 Certificate
                </label>
                <textarea
                  value={formData.certificate}
                  onChange={(e) => setFormData({ ...formData, certificate: e.target.value })}
                  required
                  rows={4}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                />
                <p className="text-slate-500 text-xs mt-1">
                  The IdP's public X.509 certificate for signature verification
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  SP Entity ID
                </label>
                <input
                  type="text"
                  value={formData.sp_entity_id}
                  onChange={(e) => setFormData({ ...formData, sp_entity_id: e.target.value })}
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <p className="text-slate-500 text-xs mt-1">
                  The Entity ID for FlowLens (Service Provider)
                </p>
              </div>

              <div className="border-t border-slate-700 pt-4">
                <h3 className="text-sm font-medium text-white mb-3">Role Mapping</h3>

                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Role Attribute
                  </label>
                  <input
                    type="text"
                    value={formData.role_attribute}
                    onChange={(e) => setFormData({ ...formData, role_attribute: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    placeholder="http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
                  />
                  <p className="text-slate-500 text-xs mt-1">
                    SAML attribute containing user roles or groups
                  </p>
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Role Mappings
                  </label>
                  <div className="space-y-2">
                    {Object.entries(formData.role_mapping).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2 p-2 bg-slate-700/50 rounded-lg">
                        <span className="text-slate-300 flex-1">{key}</span>
                        <span className="text-slate-500">→</span>
                        <Badge variant={value === 'admin' ? 'error' : value === 'analyst' ? 'warning' : 'info'}>
                          {value}
                        </Badge>
                        <button
                          type="button"
                          onClick={() => removeRoleMapping(key)}
                          className="text-slate-400 hover:text-red-400"
                        >
                          <XMarkIcon className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <input
                      type="text"
                      value={roleMappingInput.key}
                      onChange={(e) => setRoleMappingInput({ ...roleMappingInput, key: e.target.value })}
                      className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                      placeholder="IdP Group Name"
                    />
                    <select
                      value={roleMappingInput.value}
                      onChange={(e) => setRoleMappingInput({ ...roleMappingInput, value: e.target.value })}
                      className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="viewer">Viewer</option>
                      <option value="analyst">Analyst</option>
                      <option value="admin">Admin</option>
                    </select>
                    <Button type="button" variant="secondary" onClick={addRoleMapping}>
                      Add
                    </Button>
                  </div>
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-slate-300 mb-1">
                    Default Role
                  </label>
                  <select
                    value={formData.default_role}
                    onChange={(e) => setFormData({ ...formData, default_role: e.target.value as UserRole })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="viewer">Viewer</option>
                    <option value="analyst">Analyst</option>
                    <option value="admin">Admin</option>
                  </select>
                  <p className="text-slate-500 text-xs mt-1">
                    Role assigned when no mapping matches
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="auto_provision"
                  checked={formData.auto_provision_users}
                  onChange={(e) => setFormData({ ...formData, auto_provision_users: e.target.checked })}
                  className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                />
                <label htmlFor="auto_provision" className="text-slate-300 text-sm">
                  Auto-provision users on first login
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
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
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
