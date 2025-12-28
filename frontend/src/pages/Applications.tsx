import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  MagnifyingGlassIcon,
  PlusIcon,
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  StarIcon,
  MapIcon,
  PencilIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { applicationsApi, assetApi } from '../services/api';
import { formatRelativeTime } from '../utils/format';
import { getProtocolName } from '../utils/network';
import type {
  Application,
  ApplicationWithMembers,
  ApplicationCreate,
  ApplicationMember,
  Criticality,
  Asset,
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
  const [editingEntryPoint, setEditingEntryPoint] = useState<ApplicationMember | null>(null);
  const [entryPointForm, setEntryPointForm] = useState<{ port: string; protocol: string }>({
    port: '',
    protocol: '6', // Default to TCP
  });

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
    mutationFn: ({ appId, assetId, isEntryPoint }: { appId: string; assetId: string; isEntryPoint: boolean }) =>
      applicationsApi.addMember(appId, { asset_id: assetId, is_entry_point: isEntryPoint }),
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

  const toggleEntryPointMutation = useMutation({
    mutationFn: ({ appId, assetId, isEntryPoint }: { appId: string; assetId: string; isEntryPoint: boolean }) =>
      isEntryPoint
        ? applicationsApi.setEntryPoint(appId, assetId)
        : applicationsApi.unsetEntryPoint(appId, assetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
    },
  });

  const updateEntryPointMutation = useMutation({
    mutationFn: ({
      appId,
      assetId,
      port,
      protocol,
    }: {
      appId: string;
      assetId: string;
      port: number | null;
      protocol: number | null;
    }) =>
      applicationsApi.updateMember(appId, assetId, {
        is_entry_point: true,
        entry_point_port: port,
        entry_point_protocol: protocol,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application', selectedApp?.id] });
      setEditingEntryPoint(null);
    },
  });

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
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          <PlusIcon className="h-4 w-4 mr-2" />
          Create Application
        </Button>
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

                  {appDetails?.members?.map((member: ApplicationMember) => (
                    <div
                      key={member.id}
                      className="flex items-center justify-between p-2 rounded bg-slate-700/50 hover:bg-slate-700"
                    >
                      <div className="flex items-center gap-3">
                        {/* Entry Point Star */}
                        <button
                          onClick={() => {
                            if (member.is_entry_point) {
                              // Remove entry point
                              toggleEntryPointMutation.mutate({
                                appId: selectedApp.id,
                                assetId: member.asset_id,
                                isEntryPoint: false,
                              });
                            } else {
                              // Open modal to define entry point with port/protocol
                              setEditingEntryPoint(member);
                              setEntryPointForm({
                                port: '',
                                protocol: '6',
                              });
                            }
                          }}
                          className="text-slate-400 hover:text-yellow-400"
                          title={member.is_entry_point ? 'Remove entry point' : 'Set as entry point'}
                        >
                          {member.is_entry_point ? (
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
                            {member.is_entry_point && (
                              <Badge variant="warning" size="sm">
                                Entry Point
                                {member.entry_point_port && (
                                  <span className="ml-1">
                                    :{member.entry_point_port}/{getProtocolName(member.entry_point_protocol ?? 6)}
                                  </span>
                                )}
                              </Badge>
                            )}
                          </div>
                          <span className="text-slate-400 text-xs">
                            {member.asset.ip_address}
                            {member.role && ` - ${member.role}`}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Edit entry point port/protocol */}
                        {member.is_entry_point && (
                          <button
                            onClick={() => {
                              setEditingEntryPoint(member);
                              setEntryPointForm({
                                port: member.entry_point_port?.toString() || '',
                                protocol: member.entry_point_protocol?.toString() || '6',
                              });
                            }}
                            className="text-slate-400 hover:text-blue-400"
                            title="Edit entry point port/protocol"
                          >
                            <PencilIcon className="h-4 w-4" />
                          </button>
                        )}
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
                  ))}
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
                            isEntryPoint: false,
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

      {/* Set/Edit Entry Point Modal */}
      {editingEntryPoint && selectedApp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">
                {editingEntryPoint.is_entry_point ? 'Edit' : 'Set'} Entry Point: {editingEntryPoint.asset.name}
              </h2>
              <button
                onClick={() => setEditingEntryPoint(null)}
                className="text-slate-400 hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <p className="text-sm text-slate-400 mb-4">
              Define the port and protocol that external clients use to access this application entry point.
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Port <span className="text-slate-500">(required)</span></label>
                <input
                  type="number"
                  min="1"
                  max="65535"
                  value={entryPointForm.port}
                  onChange={(e) =>
                    setEntryPointForm({ ...entryPointForm, port: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g., 443, 80, 8080"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Protocol</label>
                <select
                  value={entryPointForm.protocol}
                  onChange={(e) =>
                    setEntryPointForm({ ...entryPointForm, protocol: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="6">TCP</option>
                  <option value="17">UDP</option>
                  <option value="1">ICMP</option>
                  <option value="47">GRE</option>
                  <option value="50">ESP</option>
                </select>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="ghost"
                onClick={() => setEditingEntryPoint(null)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  updateEntryPointMutation.mutate({
                    appId: selectedApp.id,
                    assetId: editingEntryPoint.asset_id,
                    port: entryPointForm.port ? parseInt(entryPointForm.port, 10) : null,
                    protocol: entryPointForm.protocol
                      ? parseInt(entryPointForm.protocol, 10)
                      : null,
                  });
                }}
                disabled={updateEntryPointMutation.isPending || !entryPointForm.port}
              >
                {updateEntryPointMutation.isPending ? 'Saving...' : (editingEntryPoint.is_entry_point ? 'Save' : 'Set Entry Point')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
