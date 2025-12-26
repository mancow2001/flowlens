import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { maintenanceApi, MaintenanceWindow, MaintenanceWindowSummary, classificationApi } from '../services/api';

interface WindowFormData {
  name: string;
  description: string;
  environments: string[];
  datacenters: string[];
  start_time: string;
  end_time: string;
  suppress_alerts: boolean;
  suppress_notifications: boolean;
  created_by: string;
}

const emptyFormData: WindowFormData = {
  name: '',
  description: '',
  environments: [],
  datacenters: [],
  start_time: '',
  end_time: '',
  suppress_alerts: true,
  suppress_notifications: true,
  created_by: 'admin',
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function formatDateTimeLocal(iso: string): string {
  const date = new Date(iso);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

function getWindowStatus(window: MaintenanceWindowSummary): { label: string; color: string } {
  const now = new Date();
  const start = new Date(window.start_time);
  const end = new Date(window.end_time);

  if (!window.is_active) {
    return { label: 'Cancelled', color: 'bg-slate-500/20 text-slate-400' };
  }
  if (now < start) {
    return { label: 'Scheduled', color: 'bg-blue-500/20 text-blue-400' };
  }
  if (now >= start && now <= end) {
    return { label: 'Active', color: 'bg-green-500/20 text-green-400' };
  }
  return { label: 'Completed', color: 'bg-slate-500/20 text-slate-400' };
}

export default function Maintenance() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingWindow, setEditingWindow] = useState<MaintenanceWindow | null>(null);
  const [formData, setFormData] = useState<WindowFormData>(emptyFormData);
  const [showPast, setShowPast] = useState(false);

  // Fetch windows
  const { data: windowsData, isLoading } = useQuery({
    queryKey: ['maintenance-windows', showPast],
    queryFn: () => maintenanceApi.list({ page_size: 100, includePast: showPast }),
  });

  // Fetch environments and datacenters for the form
  const { data: environments = [] } = useQuery({
    queryKey: ['classification-environments'],
    queryFn: () => classificationApi.listEnvironments(),
  });

  const { data: datacenters = [] } = useQuery({
    queryKey: ['classification-datacenters'],
    queryFn: () => classificationApi.listDatacenters(),
  });

  // Active windows
  const { data: activeWindows = [] } = useQuery({
    queryKey: ['maintenance-windows', 'active'],
    queryFn: () => maintenanceApi.getActive(),
    refetchInterval: 60000, // Refresh every minute
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: WindowFormData) => maintenanceApi.create({
      name: data.name,
      description: data.description || null,
      asset_ids: null,
      environments: data.environments.length > 0 ? data.environments : null,
      datacenters: data.datacenters.length > 0 ? data.datacenters : null,
      start_time: new Date(data.start_time).toISOString(),
      end_time: new Date(data.end_time).toISOString(),
      is_recurring: false,
      recurrence_rule: null,
      suppress_alerts: data.suppress_alerts,
      suppress_notifications: data.suppress_notifications,
      created_by: data.created_by,
      tags: null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-windows'] });
      setShowModal(false);
      setFormData(emptyFormData);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: WindowFormData }) => maintenanceApi.update(id, {
      name: data.name,
      description: data.description || null,
      environments: data.environments.length > 0 ? data.environments : null,
      datacenters: data.datacenters.length > 0 ? data.datacenters : null,
      start_time: new Date(data.start_time).toISOString(),
      end_time: new Date(data.end_time).toISOString(),
      suppress_alerts: data.suppress_alerts,
      suppress_notifications: data.suppress_notifications,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-windows'] });
      setShowModal(false);
      setEditingWindow(null);
      setFormData(emptyFormData);
    },
  });

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: (id: string) => maintenanceApi.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-windows'] });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => maintenanceApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maintenance-windows'] });
    },
  });

  const handleEdit = (window: MaintenanceWindowSummary) => {
    maintenanceApi.get(window.id).then((fullWindow) => {
      setEditingWindow(fullWindow);
      setFormData({
        name: fullWindow.name,
        description: fullWindow.description || '',
        environments: fullWindow.environments || [],
        datacenters: fullWindow.datacenters || [],
        start_time: formatDateTimeLocal(fullWindow.start_time),
        end_time: formatDateTimeLocal(fullWindow.end_time),
        suppress_alerts: fullWindow.suppress_alerts,
        suppress_notifications: fullWindow.suppress_notifications,
        created_by: fullWindow.created_by,
      });
      setShowModal(true);
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingWindow) {
      updateMutation.mutate({ id: editingWindow.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
  };

  const toggleEnvironment = (env: string) => {
    setFormData(prev => ({
      ...prev,
      environments: prev.environments.includes(env)
        ? prev.environments.filter(e => e !== env)
        : [...prev.environments, env],
    }));
  };

  const toggleDatacenter = (dc: string) => {
    setFormData(prev => ({
      ...prev,
      datacenters: prev.datacenters.includes(dc)
        ? prev.datacenters.filter(d => d !== dc)
        : [...prev.datacenters, dc],
    }));
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  const windows = windowsData?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Maintenance Windows</h1>
          <p className="text-slate-400 mt-1">
            Schedule maintenance periods to suppress alerts during planned downtime
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditingWindow(null);
            setFormData({
              ...emptyFormData,
              start_time: formatDateTimeLocal(new Date().toISOString()),
              end_time: formatDateTimeLocal(new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString()),
            });
            setShowModal(true);
          }}
        >
          Schedule Maintenance
        </Button>
      </div>

      {/* Active Windows Alert */}
      {activeWindows.length > 0 && (
        <Card className="border-l-4 border-l-yellow-500">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-yellow-500/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="text-white font-medium">
                {activeWindows.length} Active Maintenance Window{activeWindows.length > 1 ? 's' : ''}
              </h3>
              <p className="text-sm text-slate-400">
                {activeWindows.map(w => w.name).join(', ')} - Alerts are being suppressed
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <div className="text-sm text-slate-400">Total Windows</div>
          <div className="text-2xl font-bold text-white">{windows.length}</div>
        </Card>
        <Card>
          <div className="text-sm text-slate-400">Currently Active</div>
          <div className="text-2xl font-bold text-green-400">{activeWindows.length}</div>
        </Card>
        <Card>
          <div className="text-sm text-slate-400">Scheduled</div>
          <div className="text-2xl font-bold text-blue-400">
            {windows.filter(w => {
              const now = new Date();
              return w.is_active && new Date(w.start_time) > now;
            }).length}
          </div>
        </Card>
        <Card>
          <div className="text-sm text-slate-400">Alerts Suppressed</div>
          <div className="text-2xl font-bold text-yellow-400">
            {windows.reduce((sum, w) => sum + w.suppressed_alerts_count, 0)}
          </div>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showPast}
            onChange={(e) => setShowPast(e.target.checked)}
            className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
          />
          <span className="text-sm text-slate-300">Show past windows</span>
        </label>
      </div>

      {/* Windows Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                <th className="pb-3 font-medium">Name</th>
                <th className="pb-3 font-medium">Start</th>
                <th className="pb-3 font-medium">End</th>
                <th className="pb-3 font-medium">Scope</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Suppressed</th>
                <th className="pb-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {windows.map((window) => {
                const status = getWindowStatus(window);
                return (
                  <tr key={window.id} className="text-slate-200">
                    <td className="py-3">
                      <div className="font-medium">{window.name}</div>
                    </td>
                    <td className="py-3 text-sm">{formatDateTime(window.start_time)}</td>
                    <td className="py-3 text-sm">{formatDateTime(window.end_time)}</td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-1">
                        {(!window.environments?.length && !window.datacenters?.length) && (
                          <span className="px-2 py-0.5 bg-slate-700 text-slate-300 text-xs rounded">
                            All Assets
                          </span>
                        )}
                        {window.environments?.map(env => (
                          <span
                            key={env}
                            className="px-2 py-0.5 bg-blue-500/20 text-blue-300 text-xs rounded"
                          >
                            {env}
                          </span>
                        ))}
                        {window.datacenters?.map(dc => (
                          <span
                            key={dc}
                            className="px-2 py-0.5 bg-green-500/20 text-green-300 text-xs rounded"
                          >
                            {dc}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${status.color}`}>
                        {status.label}
                      </span>
                    </td>
                    <td className="py-3">{window.suppressed_alerts_count}</td>
                    <td className="py-3">
                      <div className="flex gap-2">
                        {window.is_active && new Date(window.end_time) > new Date() && (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleEdit(window)}
                            >
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-yellow-400 hover:text-yellow-300"
                              onClick={() => {
                                if (confirm('Cancel this maintenance window?')) {
                                  cancelMutation.mutate(window.id);
                                }
                              }}
                            >
                              Cancel
                            </Button>
                          </>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-400 hover:text-red-300"
                          onClick={() => {
                            if (confirm('Delete this maintenance window?')) {
                              deleteMutation.mutate(window.id);
                            }
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {windows.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    No maintenance windows scheduled. Create one to suppress alerts during planned downtime.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Add/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold text-white mb-4">
              {editingWindow ? 'Edit Maintenance Window' : 'Schedule Maintenance Window'}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  placeholder="e.g., Database Upgrade"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Start Time *</label>
                  <input
                    type="datetime-local"
                    value={formData.start_time}
                    onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">End Time *</label>
                  <input
                    type="datetime-local"
                    value={formData.end_time}
                    onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
                    required
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              {/* Scope */}
              <div>
                <label className="block text-sm text-slate-400 mb-2">Scope (leave empty for all assets)</label>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-slate-500 uppercase mb-2">Environments</div>
                    <div className="flex flex-wrap gap-2">
                      {environments.map(env => (
                        <button
                          key={env}
                          type="button"
                          onClick={() => toggleEnvironment(env)}
                          className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                            formData.environments.includes(env)
                              ? 'bg-blue-500 text-white'
                              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                          }`}
                        >
                          {env}
                        </button>
                      ))}
                      {environments.length === 0 && (
                        <span className="text-xs text-slate-500 italic">No environments defined</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 uppercase mb-2">Datacenters</div>
                    <div className="flex flex-wrap gap-2">
                      {datacenters.map(dc => (
                        <button
                          key={dc}
                          type="button"
                          onClick={() => toggleDatacenter(dc)}
                          className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                            formData.datacenters.includes(dc)
                              ? 'bg-green-500 text-white'
                              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                          }`}
                        >
                          {dc}
                        </button>
                      ))}
                      {datacenters.length === 0 && (
                        <span className="text-xs text-slate-500 italic">No datacenters defined</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Settings */}
              <div className="space-y-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.suppress_alerts}
                    onChange={(e) => setFormData({ ...formData, suppress_alerts: e.target.checked })}
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  <span className="text-sm text-slate-300">Suppress alert creation</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.suppress_notifications}
                    onChange={(e) => setFormData({ ...formData, suppress_notifications: e.target.checked })}
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  <span className="text-sm text-slate-300">Suppress notifications</span>
                </label>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={2}
                  placeholder="Optional description of the maintenance activity"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-700">
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditingWindow(null);
                    setFormData(emptyFormData);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {createMutation.isPending || updateMutation.isPending
                    ? 'Saving...'
                    : editingWindow
                    ? 'Update Window'
                    : 'Schedule Window'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}
