import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  ShieldCheckIcon,
  PlusIcon,
  ArrowPathIcon,
  EyeIcon,
  TrashIcon,
  CheckCircleIcon,
  ClockIcon,
  DocumentDuplicateIcon,
  ArchiveBoxIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { segmentationApi, applicationsApi } from '../services/api';
import type {
  SegmentationPolicySummary,
  PolicyStance,
  PolicyStatus,
  PolicyGenerateRequest,
  Application,
} from '../types';

const STATUS_COLORS: Record<PolicyStatus, { bg: string; text: string }> = {
  draft: { bg: 'bg-slate-500/20', text: 'text-slate-400' },
  pending_review: { bg: 'bg-yellow-500/20', text: 'text-yellow-400' },
  approved: { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  active: { bg: 'bg-green-500/20', text: 'text-green-400' },
  archived: { bg: 'bg-slate-600/20', text: 'text-slate-500' },
};

const STATUS_LABELS: Record<PolicyStatus, string> = {
  draft: 'Draft',
  pending_review: 'Pending Review',
  approved: 'Approved',
  active: 'Active',
  archived: 'Archived',
};

const STANCE_LABELS: Record<PolicyStance, string> = {
  allow_list: 'Allow List',
  deny_list: 'Deny List',
};

interface GenerateFormData {
  application_id: string;
  stance: PolicyStance;
  include_external_inbound: boolean;
  include_internal_communication: boolean;
  include_downstream_dependencies: boolean;
  max_downstream_depth: number;
  min_bytes_threshold: number;
}

const defaultGenerateForm: GenerateFormData = {
  application_id: '',
  stance: 'allow_list',
  include_external_inbound: true,
  include_internal_communication: true,
  include_downstream_dependencies: true,
  max_downstream_depth: 3,
  min_bytes_threshold: 0,
};

export default function SegmentationPolicies() {
  const queryClient = useQueryClient();
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [generateForm, setGenerateForm] = useState<GenerateFormData>(defaultGenerateForm);
  const [filterAppId, setFilterAppId] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<PolicyStatus | ''>('');

  // Fetch policies
  const { data: policiesData, isLoading } = useQuery({
    queryKey: ['segmentation-policies', filterAppId, filterStatus],
    queryFn: () =>
      segmentationApi.list({
        page_size: 100,
        application_id: filterAppId || undefined,
        status: filterStatus || undefined,
      }),
  });

  // Fetch applications for the dropdown
  const { data: applicationsData } = useQuery({
    queryKey: ['applications-list'],
    queryFn: () => applicationsApi.list({ page_size: 200 }),
  });

  // Generate policy mutation
  const generateMutation = useMutation({
    mutationFn: (request: PolicyGenerateRequest) => segmentationApi.generate(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policies'] });
      setShowGenerateModal(false);
      setGenerateForm(defaultGenerateForm);
    },
  });

  // Delete policy mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => segmentationApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policies'] });
    },
  });

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!generateForm.application_id) return;
    generateMutation.mutate(generateForm);
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  const policies = policiesData?.items || [];
  const applications = applicationsData?.items || [];

  // Compute summary stats
  const totalPolicies = policies.length;
  const activePolicies = policies.filter((p) => p.status === 'active').length;
  const pendingReviewPolicies = policies.filter((p) => p.status === 'pending_review').length;
  const draftPolicies = policies.filter((p) => p.status === 'draft').length;

  // Get application name by id
  const getAppName = (appId: string): string => {
    const app = applications.find((a: Application) => a.id === appId);
    return app?.name || appId.slice(0, 8);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <ShieldCheckIcon className="w-7 h-7 text-primary-400" />
            Segmentation Policies
          </h1>
          <p className="text-slate-400 mt-1">
            Generate and manage micro-segmentation policies from application topology
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowGenerateModal(true)}>
          <PlusIcon className="w-4 h-4 mr-2" />
          Generate Policy
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="!p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-slate-700">
              <DocumentDuplicateIcon className="w-5 h-5 text-slate-300" />
            </div>
            <div>
              <div className="text-2xl font-bold text-white">{totalPolicies}</div>
              <div className="text-sm text-slate-400">Total Policies</div>
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/20">
              <CheckCircleIcon className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <div className="text-2xl font-bold text-green-400">{activePolicies}</div>
              <div className="text-sm text-slate-400">Active</div>
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-yellow-500/20">
              <ClockIcon className="w-5 h-5 text-yellow-400" />
            </div>
            <div>
              <div className="text-2xl font-bold text-yellow-400">{pendingReviewPolicies}</div>
              <div className="text-sm text-slate-400">Pending Review</div>
            </div>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-slate-600/20">
              <ArchiveBoxIcon className="w-5 h-5 text-slate-400" />
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-300">{draftPolicies}</div>
              <div className="text-sm text-slate-400">Draft</div>
            </div>
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Filter by Application</label>
            <select
              value={filterAppId}
              onChange={(e) => setFilterAppId(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">All Applications</option>
              {applications.map((app: Application) => (
                <option key={app.id} value={app.id}>
                  {app.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Filter by Status</label>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as PolicyStatus | '')}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">All Statuses</option>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <Button
              variant="ghost"
              onClick={() => {
                setFilterAppId('');
                setFilterStatus('');
              }}
            >
              Clear Filters
            </Button>
          </div>
        </div>
      </Card>

      {/* Policies Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                <th className="pb-3 font-medium">Policy Name</th>
                <th className="pb-3 font-medium">Application</th>
                <th className="pb-3 font-medium">Stance</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Version</th>
                <th className="pb-3 font-medium">Rules</th>
                <th className="pb-3 font-medium">Created</th>
                <th className="pb-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {policies.map((policy: SegmentationPolicySummary) => (
                <tr key={policy.id} className="text-slate-200">
                  <td className="py-3">
                    <Link
                      to={`/segmentation-policies/${policy.id}`}
                      className="font-medium text-primary-400 hover:text-primary-300"
                    >
                      {policy.name}
                    </Link>
                  </td>
                  <td className="py-3">{getAppName(policy.application_id)}</td>
                  <td className="py-3">
                    <span
                      className={`px-2 py-1 text-xs rounded-full ${
                        policy.stance === 'allow_list'
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {STANCE_LABELS[policy.stance]}
                    </span>
                  </td>
                  <td className="py-3">
                    <span
                      className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[policy.status].bg} ${STATUS_COLORS[policy.status].text}`}
                    >
                      {STATUS_LABELS[policy.status]}
                    </span>
                  </td>
                  <td className="py-3">v{policy.version}</td>
                  <td className="py-3">{policy.rule_count}</td>
                  <td className="py-3 text-sm text-slate-400">
                    {new Date(policy.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3">
                    <div className="flex items-center gap-1">
                      <Link to={`/segmentation-policies/${policy.id}`}>
                        <Button variant="ghost" size="sm" title="View Details">
                          <EyeIcon className="w-4 h-4" />
                        </Button>
                      </Link>
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Delete"
                        className="text-red-400 hover:text-red-300"
                        onClick={() => {
                          if (confirm('Delete this segmentation policy?')) {
                            deleteMutation.mutate(policy.id);
                          }
                        }}
                      >
                        <TrashIcon className="w-4 h-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {policies.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    No segmentation policies found. Generate a policy from an application topology.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Generate Policy Modal */}
      {showGenerateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-lg">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <ArrowPathIcon className="w-5 h-5 text-primary-400" />
              Generate Segmentation Policy
            </h2>
            <form onSubmit={handleGenerate} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Application *</label>
                <select
                  value={generateForm.application_id}
                  onChange={(e) =>
                    setGenerateForm({ ...generateForm, application_id: e.target.value })
                  }
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="">Select an application</option>
                  {applications.map((app: Application) => (
                    <option key={app.id} value={app.id}>
                      {app.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Policy Stance</label>
                <select
                  value={generateForm.stance}
                  onChange={(e) =>
                    setGenerateForm({ ...generateForm, stance: e.target.value as PolicyStance })
                  }
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="allow_list">Allow List (Zero Trust)</option>
                  <option value="deny_list">Deny List</option>
                </select>
                <p className="text-xs text-slate-500 mt-1">
                  Allow List: Only explicitly allowed traffic is permitted (recommended)
                </p>
              </div>

              <div className="space-y-2">
                <label className="block text-sm text-slate-400">Rule Generation Options</label>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={generateForm.include_external_inbound}
                    onChange={(e) =>
                      setGenerateForm({
                        ...generateForm,
                        include_external_inbound: e.target.checked,
                      })
                    }
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  Include external inbound rules (entry points)
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={generateForm.include_internal_communication}
                    onChange={(e) =>
                      setGenerateForm({
                        ...generateForm,
                        include_internal_communication: e.target.checked,
                      })
                    }
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  Include internal communication rules
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={generateForm.include_downstream_dependencies}
                    onChange={(e) =>
                      setGenerateForm({
                        ...generateForm,
                        include_downstream_dependencies: e.target.checked,
                      })
                    }
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  Include downstream dependency rules (outbound)
                </label>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Max Downstream Depth</label>
                  <input
                    type="number"
                    value={generateForm.max_downstream_depth}
                    onChange={(e) =>
                      setGenerateForm({
                        ...generateForm,
                        max_downstream_depth: parseInt(e.target.value) || 3,
                      })
                    }
                    min={1}
                    max={10}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Min Bytes Threshold</label>
                  <input
                    type="number"
                    value={generateForm.min_bytes_threshold}
                    onChange={(e) =>
                      setGenerateForm({
                        ...generateForm,
                        min_bytes_threshold: parseInt(e.target.value) || 0,
                      })
                    }
                    min={0}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    Only include dependencies with at least this many bytes
                  </p>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-700">
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setShowGenerateModal(false);
                    setGenerateForm(defaultGenerateForm);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  type="submit"
                  disabled={generateMutation.isPending || !generateForm.application_id}
                >
                  {generateMutation.isPending ? 'Generating...' : 'Generate Policy'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}
