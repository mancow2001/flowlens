import { useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  MagnifyingGlassIcon,
  PlusIcon,
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  StarIcon,
  MapIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { applicationsApi, assetApi, ApplicationImportPreview } from '../services/api';
import { formatRelativeTime } from '../utils/format';
import { getProtocolName } from '../utils/network';
import type {
  Application,
  ApplicationWithMembers,
  ApplicationCreate,
  ApplicationMember,
  Criticality,
  Asset,
  EntryPoint,
  EntryPointCreate,
} from '../types';

const CRITICALITY_VARIANTS: Record<Criticality, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  low: 'success',
  medium: 'warning',
  high: 'error',
  critical: 'error',
};

export default function Applications() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedApp, setSelectedApp] = useState<ApplicationWithMembers | null>(null);
  const [showAddMemberModal, setShowAddMemberModal] = useState(false);
  const [assetSearch, setAssetSearch] = useState('');
  const [editingMember, setEditingMember] = useState<ApplicationMember | null>(null);
  const [editingEntryPoint, setEditingEntryPoint] = useState<EntryPoint | null>(null);
  const [showEntryPointsModal, setShowEntryPointsModal] = useState(false);
  const [entryPointForm, setEntryPointForm] = useState<{ port: string; protocol: string; label: string }>({
    port: '',
    protocol: '6', // Default to TCP
    label: '',
  });

  // Import modal state
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<ApplicationImportPreview | null>(null);
  const [skipErrors, setSkipErrors] = useState(false);
  const [syncMembers, setSyncMembers] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form state for create/edit
  const [formData, setFormData] = useState<Partial<ApplicationCreate>>({
    name: '',
    display_name: '',
    description: '',
    owner: '',
    team: '',
    environment: '',
    criticality: null,
  });

  // Fetch applications list
  const { data: applications, isLoading } = useQuery({
    queryKey: ['applications', page, search],
    queryFn: () =>
      applicationsApi.list({
        page,
        page_size: 20,
        search: search || undefined,
      }),
    placeholderData: (prev) => prev,
  });

  // Fetch selected application details
  const { data: appDetails } = useQuery({
    queryKey: ['application', selectedApp?.id],
    queryFn: () => applicationsApi.get(selectedApp!.id),
    enabled: !!selectedApp?.id,
  });

  // Fetch assets for adding members
  const { data: assets } = useQuery({
    queryKey: ['assets', 'search', assetSearch],
    queryFn: () =>
      assetApi.list({
        page: 1,
        page_size: 20,
        search: assetSearch || undefined,
      }),
    enabled: showAddMemberModal && assetSearch.length > 1,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: ApplicationCreate) => applicationsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      setShowCreateModal(false);
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => applicationsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      setSelectedApp(null);
    },
  });

  const addMemberMutation = useMutation({
    mutationFn: ({ appId, assetId }: { appId: string; assetId: string }) =>
      applicationsApi.addMember(appId, { asset_id: assetId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
      setShowAddMemberModal(false);
      setAssetSearch('');
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: ({ appId, assetId }: { appId: string; assetId: string }) =>
      applicationsApi.removeMember(appId, assetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
    },
  });

  // Helper to refresh editingMember from updated appDetails
  const refreshEditingMember = useCallback(async () => {
    if (selectedApp && editingMember) {
      const updated = await queryClient.fetchQuery({
        queryKey: ['application', selectedApp.id],
        queryFn: () => applicationsApi.get(selectedApp.id),
      });
      const member = updated.members.find((m) => m.asset_id === editingMember.asset_id);
      if (member) {
        setEditingMember(member);
      }
    }
  }, [selectedApp, editingMember, queryClient]);

  const addEntryPointMutation = useMutation({
    mutationFn: ({
      appId,
      assetId,
      entryPoint,
    }: {
      appId: string;
      assetId: string;
      entryPoint: EntryPointCreate;
    }) => applicationsApi.addEntryPoint(appId, assetId, entryPoint),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
      setEntryPointForm({ port: '', protocol: '6', label: '' });
      await refreshEditingMember();
    },
  });

  const updateEntryPointMutation = useMutation({
    mutationFn: ({
      appId,
      assetId,
      entryPointId,
      port,
      protocol,
      label,
    }: {
      appId: string;
      assetId: string;
      entryPointId: string;
      port: number;
      protocol: number;
      label: string | null;
    }) =>
      applicationsApi.updateEntryPoint(appId, assetId, entryPointId, {
        port,
        protocol,
        label: label || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
      setEditingEntryPoint(null);
      setEntryPointForm({ port: '', protocol: '6', label: '' });
      await refreshEditingMember();
    },
  });

  const deleteEntryPointMutation = useMutation({
    mutationFn: ({
      appId,
      assetId,
      entryPointId,
    }: {
      appId: string;
      assetId: string;
      entryPointId: string;
    }) => applicationsApi.deleteEntryPoint(appId, assetId, entryPointId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
      await refreshEditingMember();
    },
  });

  // Import preview mutation
  const previewImportMutation = useMutation({
    mutationFn: (file: File) => applicationsApi.previewImport(file),
    onSuccess: (data) => {
      setImportPreview(data);
    },
  });

  // Import mutation
  const importMutation = useMutation({
    mutationFn: ({ file, skipErrors, syncMembers }: { file: File; skipErrors: boolean; syncMembers: boolean }) =>
      applicationsApi.import(file, skipErrors, syncMembers),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      setShowImportModal(false);
      setImportFile(null);
      setImportPreview(null);
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportFile(file);
      setImportPreview(null);
      previewImportMutation.mutate(file);
    }
  };

  const handleImport = () => {
    if (importFile) {
      importMutation.mutate({ file: importFile, skipErrors, syncMembers });
    }
  };

  const handleExport = () => {
    window.open(applicationsApi.exportUrl(), '_blank');
  };

  const closeImportModal = () => {
    setShowImportModal(false);
    setImportFile(null);
    setImportPreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const resetForm = useCallback(() => {
    setFormData({
      name: '',
      display_name: '',
      description: '',
      owner: '',
      team: '',
      environment: '',
      criticality: null,
    });
  }, []);

  const handleCreate = () => {
    if (!formData.name) return;
    createMutation.mutate(formData as ApplicationCreate);
  };

  const totalPages = applications ? Math.ceil(applications.total / applications.page_size) : 0;

  if (isLoading) {
    return <LoadingPage />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Applications</h1>
          <p className="text-slate-400 mt-1">
            Define application boundaries and entry points
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Export Button */}
          <Button variant="secondary" onClick={handleExport}>
            <ArrowDownTrayIcon className="w-4 h-4 mr-2" />
            Export
          </Button>
          {/* Import Button */}
          <Button variant="secondary" onClick={() => setShowImportModal(true)}>
            <ArrowUpTrayIcon className="w-4 h-4 mr-2" />
            Import
          </Button>
          {/* Create Button */}
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            <PlusIcon className="h-4 w-4 mr-2" />
            Create Application
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Applications List */}
        <div className="lg:col-span-2">
          <Card>
            {/* Search */}
            <div className="mb-4">
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search applications..."
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                  className="w-full pl-10 pr-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* Applications List */}
            <div className="space-y-2">
              {applications?.items?.length === 0 && (
                <div className="text-center py-8 text-slate-400">
                  No applications found
                </div>
              )}

              {applications?.items?.map((app: Application) => (
                <div
                  key={app.id}
                  onClick={() => setSelectedApp(app as ApplicationWithMembers)}
                  className={`p-4 rounded-lg cursor-pointer transition-colors ${
                    selectedApp?.id === app.id
                      ? 'bg-blue-500/20 border border-blue-500/50'
                      : 'bg-slate-700/50 hover:bg-slate-700 border border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-white">
                        {app.display_name || app.name}
                      </div>
                      {app.display_name && (
                        <div className="text-xs text-slate-500">{app.name}</div>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      {app.criticality && (
                        <Badge variant={CRITICALITY_VARIANTS[app.criticality]}>
                          {app.criticality}
                        </Badge>
                      )}
                      {app.environment && (
                        <span className="text-xs text-slate-400">{app.environment}</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-4 text-xs text-slate-400">
                    {app.owner && <span>Owner: {app.owner}</span>}
                    <span>{formatRelativeTime(app.updated_at)}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between text-sm">
                <span className="text-slate-400">
                  Page {page} of {totalPages} ({applications?.total} total)
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Application Details */}
        <div className="space-y-4">
          {selectedApp ? (
            <>
              <Card title={appDetails?.display_name || appDetails?.name || selectedApp.name}>
                <div className="space-y-4">
                  {/* Description */}
                  {appDetails?.description && (
                    <p className="text-slate-300 text-sm">{appDetails.description}</p>
                  )}

                  {/* Metadata */}
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-slate-400">Environment</span>
                      <p className="text-white">{appDetails?.environment || '-'}</p>
                    </div>
                    <div>
                      <span className="text-slate-400">Criticality</span>
                      <p className="text-white">
                        {appDetails?.criticality ? (
                          <Badge variant={CRITICALITY_VARIANTS[appDetails.criticality]}>
                            {appDetails.criticality}
                          </Badge>
                        ) : (
                          '-'
                        )}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-400">Owner</span>
                      <p className="text-white">{appDetails?.owner || '-'}</p>
                    </div>
                    <div>
                      <span className="text-slate-400">Team</span>
                      <p className="text-white">{appDetails?.team || '-'}</p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="pt-4 border-t border-slate-700 flex gap-2">
                    <Link to={`/applications/${selectedApp.id}`}>
                      <Button variant="primary" size="sm">
                        <MapIcon className="h-4 w-4 mr-1" />
                        View Topology
                      </Button>
                    </Link>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => {
                        if (confirm('Delete this application?')) {
                          deleteMutation.mutate(selectedApp.id);
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </Card>

              {/* Members Card */}
              <Card
                title={
                  <div className="flex items-center justify-between">
                    <span>Members ({appDetails?.members?.length ?? 0})</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowAddMemberModal(true)}
                    >
                      <PlusIcon className="h-4 w-4 mr-1" />
                      Add
                    </Button>
                  </div>
                }
              >
                <div className="space-y-2">
                  {appDetails?.members?.length === 0 && (
                    <p className="text-slate-500 text-sm">No members added yet</p>
                  )}

                  {appDetails?.members?.map((member: ApplicationMember) => {
                    const hasEntryPoints = member.entry_points.length > 0;
                    return (
                      <div
                        key={member.id}
                        className="p-2 rounded bg-slate-700/50 hover:bg-slate-700"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            {/* Entry Point Star - opens entry points modal */}
                            <button
                              onClick={() => {
                                setEditingMember(member);
                                setShowEntryPointsModal(true);
                                setEditingEntryPoint(null);
                                setEntryPointForm({ port: '', protocol: '6', label: '' });
                              }}
                              className="text-slate-400 hover:text-yellow-400"
                              title={hasEntryPoints ? 'Manage entry points' : 'Add entry point'}
                            >
                              {hasEntryPoints ? (
                                <StarIconSolid className="h-5 w-5 text-yellow-400" />
                              ) : (
                                <StarIcon className="h-5 w-5" />
                              )}
                            </button>

                            <div>
                              <div className="flex items-center gap-2">
                                <span className="text-white text-sm font-medium">
                                  {member.asset.name}
                                </span>
                              </div>
                              <span className="text-slate-400 text-xs">
                                {member.asset.ip_address}
                                {member.role && ` - ${member.role}`}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <a
                              href={`/assets/${member.asset_id}`}
                              className="text-slate-400 hover:text-blue-400"
                              title="View asset"
                            >
                              <ArrowTopRightOnSquareIcon className="h-4 w-4" />
                            </a>
                            <button
                              onClick={() =>
                                removeMemberMutation.mutate({
                                  appId: selectedApp.id,
                                  assetId: member.asset_id,
                                })
                              }
                              className="text-slate-400 hover:text-red-400"
                              title="Remove from application"
                            >
                              <XMarkIcon className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        {/* Show entry points if any */}
                        {hasEntryPoints && (
                          <div className="mt-2 ml-8 flex flex-wrap gap-1">
                            {member.entry_points.map((ep) => (
                              <Badge key={ep.id} variant="warning" size="sm">
                                {ep.label ? `${ep.label}: ` : ''}{ep.port}/{getProtocolName(ep.protocol)}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
            </>
          ) : (
            <Card>
              <div className="text-center py-8 text-slate-400">
                <p>Select an application to view details</p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* Create Application Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Create Application</h2>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  resetForm();
                }}
                className="text-slate-400 hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g., payment-service"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Display Name</label>
                <input
                  type="text"
                  value={formData.display_name || ''}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g., Payment Service"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Description</label>
                <textarea
                  value={formData.description || ''}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  rows={3}
                  placeholder="Describe this application..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Owner</label>
                  <input
                    type="text"
                    value={formData.owner || ''}
                    onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Team</label>
                  <input
                    type="text"
                    value={formData.team || ''}
                    onChange={(e) => setFormData({ ...formData, team: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Environment</label>
                  <select
                    value={formData.environment || ''}
                    onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select...</option>
                    <option value="production">Production</option>
                    <option value="staging">Staging</option>
                    <option value="development">Development</option>
                    <option value="testing">Testing</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Criticality</label>
                  <select
                    value={formData.criticality || ''}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        criticality: (e.target.value as Criticality) || null,
                      })
                    }
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select...</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowCreateModal(false);
                  resetForm();
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleCreate}
                disabled={!formData.name || createMutation.isPending}
              >
                {createMutation.isPending ? 'Creating...' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Add Member Modal */}
      {showAddMemberModal && selectedApp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Add Member</h2>
              <button
                onClick={() => {
                  setShowAddMemberModal(false);
                  setAssetSearch('');
                }}
                className="text-slate-400 hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Search Assets</label>
                <div className="relative">
                  <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                  <input
                    type="text"
                    value={assetSearch}
                    onChange={(e) => setAssetSearch(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Search by name or IP..."
                  />
                </div>
              </div>

              {/* Asset Results */}
              <div className="max-h-64 overflow-y-auto space-y-2">
                {assets?.items?.map((asset: Asset) => {
                  const isAlreadyMember = appDetails?.members?.some(
                    (m) => m.asset_id === asset.id
                  );
                  return (
                    <div
                      key={asset.id}
                      className={`flex items-center justify-between p-2 rounded ${
                        isAlreadyMember
                          ? 'bg-slate-700/30 opacity-50'
                          : 'bg-slate-700/50 hover:bg-slate-700 cursor-pointer'
                      }`}
                      onClick={() => {
                        if (!isAlreadyMember) {
                          addMemberMutation.mutate({
                            appId: selectedApp.id,
                            assetId: asset.id,
                          });
                        }
                      }}
                    >
                      <div>
                        <div className="text-white text-sm">{asset.name}</div>
                        <div className="text-slate-400 text-xs">{asset.ip_address}</div>
                      </div>
                      {isAlreadyMember && (
                        <span className="text-xs text-slate-500">Already added</span>
                      )}
                    </div>
                  );
                })}

                {assetSearch.length > 1 && assets?.items?.length === 0 && (
                  <p className="text-slate-500 text-sm text-center py-4">No assets found</p>
                )}

                {assetSearch.length <= 1 && (
                  <p className="text-slate-500 text-sm text-center py-4">
                    Type at least 2 characters to search
                  </p>
                )}
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowAddMemberModal(false);
                  setAssetSearch('');
                }}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Entry Points Management Modal */}
      {showEntryPointsModal && editingMember && selectedApp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">
                Entry Points: {editingMember.asset.name}
              </h2>
              <button
                onClick={() => {
                  setShowEntryPointsModal(false);
                  setEditingMember(null);
                  setEditingEntryPoint(null);
                  setEntryPointForm({ port: '', protocol: '6', label: '' });
                }}
                className="text-slate-400 hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <p className="text-sm text-slate-400 mb-4">
              Define the ports and protocols that external clients use to access this application.
              You can add multiple entry points (e.g., HTTP on port 80 and HTTPS on port 443).
            </p>

            {/* Existing Entry Points */}
            {editingMember.entry_points.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-medium text-slate-300 mb-2">Current Entry Points</h3>
                <div className="space-y-2">
                  {editingMember.entry_points.map((ep) => (
                    <div
                      key={ep.id}
                      className="flex items-center justify-between p-2 rounded bg-slate-700/50"
                    >
                      {editingEntryPoint?.id === ep.id ? (
                        // Inline edit form
                        <div className="flex-1 flex items-center gap-2">
                          <input
                            type="text"
                            value={entryPointForm.label}
                            onChange={(e) =>
                              setEntryPointForm({ ...entryPointForm, label: e.target.value })
                            }
                            placeholder="Label"
                            className="w-20 px-2 py-1 text-sm bg-slate-600 border border-slate-500 rounded text-white"
                          />
                          <input
                            type="number"
                            min="1"
                            max="65535"
                            value={entryPointForm.port}
                            onChange={(e) =>
                              setEntryPointForm({ ...entryPointForm, port: e.target.value })
                            }
                            className="w-20 px-2 py-1 text-sm bg-slate-600 border border-slate-500 rounded text-white"
                          />
                          <select
                            value={entryPointForm.protocol}
                            onChange={(e) =>
                              setEntryPointForm({ ...entryPointForm, protocol: e.target.value })
                            }
                            className="px-2 py-1 text-sm bg-slate-600 border border-slate-500 rounded text-white"
                          >
                            <option value="6">TCP</option>
                            <option value="17">UDP</option>
                          </select>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => {
                              updateEntryPointMutation.mutate({
                                appId: selectedApp.id,
                                assetId: editingMember.asset_id,
                                entryPointId: ep.id,
                                port: parseInt(entryPointForm.port, 10),
                                protocol: parseInt(entryPointForm.protocol, 10),
                                label: entryPointForm.label || null,
                              });
                            }}
                            disabled={!entryPointForm.port || updateEntryPointMutation.isPending}
                          >
                            Save
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditingEntryPoint(null);
                              setEntryPointForm({ port: '', protocol: '6', label: '' });
                            }}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-2">
                            <Badge variant="warning" size="sm">
                              {ep.label ? `${ep.label}: ` : ''}{ep.port}/{getProtocolName(ep.protocol)}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => {
                                setEditingEntryPoint(ep);
                                setEntryPointForm({
                                  port: ep.port.toString(),
                                  protocol: ep.protocol.toString(),
                                  label: ep.label || '',
                                });
                              }}
                              className="text-slate-400 hover:text-blue-400 p-1"
                              title="Edit"
                            >
                              <PencilIcon className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => {
                                deleteEntryPointMutation.mutate({
                                  appId: selectedApp.id,
                                  assetId: editingMember.asset_id,
                                  entryPointId: ep.id,
                                });
                              }}
                              className="text-slate-400 hover:text-red-400 p-1"
                              title="Delete"
                            >
                              <TrashIcon className="h-4 w-4" />
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Add New Entry Point Form */}
            {!editingEntryPoint && (
              <div className="border-t border-slate-700 pt-4">
                <h3 className="text-sm font-medium text-slate-300 mb-2">Add Entry Point</h3>
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <label className="block text-xs text-slate-400 mb-1">Label (optional)</label>
                    <input
                      type="text"
                      value={entryPointForm.label}
                      onChange={(e) =>
                        setEntryPointForm({ ...entryPointForm, label: e.target.value })
                      }
                      placeholder="e.g., HTTPS"
                      className="w-full px-2 py-1.5 text-sm bg-slate-700 border border-slate-600 rounded text-white"
                    />
                  </div>
                  <div className="w-24">
                    <label className="block text-xs text-slate-400 mb-1">Port *</label>
                    <input
                      type="number"
                      min="1"
                      max="65535"
                      value={entryPointForm.port}
                      onChange={(e) =>
                        setEntryPointForm({ ...entryPointForm, port: e.target.value })
                      }
                      placeholder="443"
                      className="w-full px-2 py-1.5 text-sm bg-slate-700 border border-slate-600 rounded text-white"
                    />
                  </div>
                  <div className="w-24">
                    <label className="block text-xs text-slate-400 mb-1">Protocol</label>
                    <select
                      value={entryPointForm.protocol}
                      onChange={(e) =>
                        setEntryPointForm({ ...entryPointForm, protocol: e.target.value })
                      }
                      className="w-full px-2 py-1.5 text-sm bg-slate-700 border border-slate-600 rounded text-white"
                    >
                      <option value="6">TCP</option>
                      <option value="17">UDP</option>
                    </select>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      addEntryPointMutation.mutate({
                        appId: selectedApp.id,
                        assetId: editingMember.asset_id,
                        entryPoint: {
                          port: parseInt(entryPointForm.port, 10),
                          protocol: parseInt(entryPointForm.protocol, 10),
                          label: entryPointForm.label || undefined,
                        },
                      });
                    }}
                    disabled={!entryPointForm.port || addEntryPointMutation.isPending}
                  >
                    <PlusIcon className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}

            <div className="mt-6 flex justify-end">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowEntryPointsModal(false);
                  setEditingMember(null);
                  setEditingEntryPoint(null);
                  setEntryPointForm({ port: '', protocol: '6', label: '' });
                }}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Import Applications</h2>
              <button onClick={closeImportModal} className="text-slate-400 hover:text-white">
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            {/* File Input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileSelect}
              className="hidden"
            />

            {!importFile ? (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-600 rounded-lg p-8 text-center cursor-pointer hover:border-primary-500 transition-colors"
              >
                <ArrowUpTrayIcon className="w-12 h-12 mx-auto text-slate-500 mb-3" />
                <p className="text-slate-300 mb-1">Click to select a file or drag and drop</p>
                <p className="text-sm text-slate-500">Supports JSON format only (includes nested members)</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Selected File */}
                <div className="flex items-center justify-between p-3 bg-slate-700/50 rounded-lg">
                  <span className="text-slate-200">{importFile.name}</span>
                  <button
                    onClick={() => {
                      setImportFile(null);
                      setImportPreview(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                    className="text-slate-400 hover:text-white"
                  >
                    <XMarkIcon className="w-4 h-4" />
                  </button>
                </div>

                {/* Loading State */}
                {previewImportMutation.isPending && (
                  <div className="text-center py-4 text-slate-400">Analyzing file...</div>
                )}

                {/* Error State */}
                {previewImportMutation.isError && (
                  <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400">
                    Failed to parse file. Please check the format.
                  </div>
                )}

                {/* Preview */}
                {importPreview && (
                  <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-4 gap-3">
                      <div className="p-3 bg-slate-700/50 rounded-lg text-center">
                        <div className="text-2xl font-bold text-white">{importPreview.total_rows}</div>
                        <div className="text-xs text-slate-400">Total Apps</div>
                      </div>
                      <div className="p-3 bg-green-500/20 rounded-lg text-center">
                        <div className="text-2xl font-bold text-green-400">{importPreview.to_create}</div>
                        <div className="text-xs text-slate-400">To Create</div>
                      </div>
                      <div className="p-3 bg-blue-500/20 rounded-lg text-center">
                        <div className="text-2xl font-bold text-blue-400">{importPreview.to_update}</div>
                        <div className="text-xs text-slate-400">To Update</div>
                      </div>
                      <div className="p-3 bg-red-500/20 rounded-lg text-center">
                        <div className="text-2xl font-bold text-red-400">{importPreview.errors}</div>
                        <div className="text-xs text-slate-400">Errors</div>
                      </div>
                    </div>

                    {/* Validation Details */}
                    {importPreview.validations.length > 0 && (
                      <div className="max-h-60 overflow-y-auto border border-slate-700 rounded-lg">
                        <table className="w-full text-sm">
                          <thead className="bg-slate-700/50 sticky top-0">
                            <tr>
                              <th className="px-3 py-2 text-left text-slate-400">Row</th>
                              <th className="px-3 py-2 text-left text-slate-400">Name</th>
                              <th className="px-3 py-2 text-left text-slate-400">Status</th>
                              <th className="px-3 py-2 text-left text-slate-400">Message</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-700">
                            {importPreview.validations.map((v) => (
                              <tr key={v.row_number}>
                                <td className="px-3 py-2 text-slate-300">{v.row_number}</td>
                                <td className="px-3 py-2 text-slate-200">{v.name || '-'}</td>
                                <td className="px-3 py-2">
                                  <span
                                    className={`px-2 py-0.5 text-xs rounded-full ${
                                      v.status === 'create'
                                        ? 'bg-green-500/20 text-green-400'
                                        : v.status === 'update'
                                        ? 'bg-blue-500/20 text-blue-400'
                                        : v.status === 'error'
                                        ? 'bg-red-500/20 text-red-400'
                                        : 'bg-slate-500/20 text-slate-400'
                                    }`}
                                  >
                                    {v.status}
                                  </span>
                                </td>
                                <td className="px-3 py-2 text-slate-400 text-xs">{v.message}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Import Options */}
                    <div className="flex items-center gap-4 pt-2">
                      <label className="flex items-center gap-2 text-sm text-slate-300">
                        <input
                          type="checkbox"
                          checked={skipErrors}
                          onChange={(e) => setSkipErrors(e.target.checked)}
                          className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                        />
                        Skip rows with errors
                      </label>
                      <label className="flex items-center gap-2 text-sm text-slate-300">
                        <input
                          type="checkbox"
                          checked={syncMembers}
                          onChange={(e) => setSyncMembers(e.target.checked)}
                          className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                        />
                        Sync members (remove unlisted members)
                      </label>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-4 mt-4 border-t border-slate-700">
              <Button variant="ghost" onClick={closeImportModal}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleImport}
                disabled={!importPreview || importMutation.isPending || (importPreview.errors > 0 && !skipErrors)}
              >
                {importMutation.isPending ? 'Importing...' : 'Import Applications'}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
