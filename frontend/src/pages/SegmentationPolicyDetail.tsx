import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  ShieldCheckIcon,
  ArrowPathIcon,
  ArrowDownTrayIcon,
  CheckIcon,
  ClockIcon,
  ArchiveBoxIcon,
  PlusIcon,
  TrashIcon,
  PencilIcon,
  DocumentDuplicateIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { segmentationApi, applicationsApi, downloadWithAuth } from '../services/api';
import type {
  SegmentationPolicyRule,
  SegmentationPolicyVersion,
  PolicyStatus,
  RuleType,
  RuleAction,
  SourceDestType,
  PolicyRuleCreate,
  PolicyRuleUpdate,
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

const RULE_TYPE_COLORS: Record<RuleType, { bg: string; text: string }> = {
  inbound: { bg: 'bg-green-500/20', text: 'text-green-400' },
  outbound: { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  internal: { bg: 'bg-purple-500/20', text: 'text-purple-400' },
};

const ACTION_COLORS: Record<RuleAction, { bg: string; text: string }> = {
  allow: { bg: 'bg-green-500/20', text: 'text-green-400' },
  deny: { bg: 'bg-red-500/20', text: 'text-red-400' },
};

const PROTOCOL_NAMES: Record<number, string> = {
  6: 'TCP',
  17: 'UDP',
  1: 'ICMP',
};

type TabType = 'rules' | 'versions' | 'export';

interface RuleFormData {
  rule_type: RuleType;
  source_type: SourceDestType;
  source_cidr: string;
  source_label: string;
  dest_type: SourceDestType;
  dest_cidr: string;
  dest_label: string;
  port: string;
  port_range_end: string;
  protocol: number;
  service_label: string;
  action: RuleAction;
  description: string;
  is_enabled: boolean;
  priority: number;
}

const emptyRuleForm: RuleFormData = {
  rule_type: 'inbound',
  source_type: 'any',
  source_cidr: '',
  source_label: '',
  dest_type: 'app_member',
  dest_cidr: '',
  dest_label: '',
  port: '',
  port_range_end: '',
  protocol: 6,
  service_label: '',
  action: 'allow',
  description: '',
  is_enabled: true,
  priority: 100,
};

export default function SegmentationPolicyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('rules');
  const [ruleTypeFilter, setRuleTypeFilter] = useState<RuleType | ''>('');
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [editingRule, setEditingRule] = useState<SegmentationPolicyRule | null>(null);
  const [ruleForm, setRuleForm] = useState<RuleFormData>(emptyRuleForm);
  const [compareVersions, setCompareVersions] = useState<{ a: number; b: number } | null>(null);

  // Fetch policy with rules
  const { data: policy, isLoading, error } = useQuery({
    queryKey: ['segmentation-policy', id],
    queryFn: () => segmentationApi.get(id!),
    enabled: !!id,
  });

  // Fetch application for display
  const { data: application } = useQuery({
    queryKey: ['application', policy?.application_id],
    queryFn: () => applicationsApi.get(policy!.application_id),
    enabled: !!policy?.application_id,
  });

  // Fetch versions
  const { data: versions } = useQuery({
    queryKey: ['segmentation-policy-versions', id],
    queryFn: () => segmentationApi.listVersions(id!),
    enabled: !!id && activeTab === 'versions',
  });

  // Fetch comparison
  const { data: comparison } = useQuery({
    queryKey: ['segmentation-policy-compare', id, compareVersions?.a, compareVersions?.b],
    queryFn: () => segmentationApi.compare(id!, compareVersions!.a, compareVersions!.b),
    enabled: !!id && !!compareVersions,
  });

  // Mutations
  const regenerateMutation = useMutation({
    mutationFn: () => segmentationApi.regenerate(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
    },
  });

  const submitForReviewMutation = useMutation({
    mutationFn: () => segmentationApi.submitForReview(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => segmentationApi.approve(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
    },
  });

  const activateMutation = useMutation({
    mutationFn: () => segmentationApi.activate(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => segmentationApi.archive(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
    },
  });

  const publishVersionMutation = useMutation({
    mutationFn: () => segmentationApi.publishVersion(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy-versions', id] });
    },
  });

  const addRuleMutation = useMutation({
    mutationFn: (rule: PolicyRuleCreate) => segmentationApi.addRule(id!, rule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
      setShowRuleModal(false);
      setRuleForm(emptyRuleForm);
    },
  });

  const updateRuleMutation = useMutation({
    mutationFn: ({ ruleId, updates }: { ruleId: string; updates: PolicyRuleUpdate }) =>
      segmentationApi.updateRule(id!, ruleId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
      setShowRuleModal(false);
      setEditingRule(null);
      setRuleForm(emptyRuleForm);
    },
  });

  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => segmentationApi.deleteRule(id!, ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segmentation-policy', id] });
    },
  });

  const deletePolicyMutation = useMutation({
    mutationFn: () => segmentationApi.delete(id!),
    onSuccess: () => {
      navigate('/segmentation-policies');
    },
  });

  const handleEditRule = (rule: SegmentationPolicyRule) => {
    setEditingRule(rule);
    setRuleForm({
      rule_type: rule.rule_type,
      source_type: rule.source_type,
      source_cidr: rule.source_cidr || '',
      source_label: rule.source_label || '',
      dest_type: rule.dest_type,
      dest_cidr: rule.dest_cidr || '',
      dest_label: rule.dest_label || '',
      port: rule.port?.toString() || '',
      port_range_end: rule.port_range_end?.toString() || '',
      protocol: rule.protocol,
      service_label: rule.service_label || '',
      action: rule.action,
      description: rule.description || '',
      is_enabled: rule.is_enabled,
      priority: rule.priority,
    });
    setShowRuleModal(true);
  };

  const handleSubmitRule = (e: React.FormEvent) => {
    e.preventDefault();
    const ruleData: PolicyRuleCreate = {
      rule_type: ruleForm.rule_type,
      source_type: ruleForm.source_type,
      source_cidr: ruleForm.source_cidr || null,
      source_label: ruleForm.source_label || null,
      dest_type: ruleForm.dest_type,
      dest_cidr: ruleForm.dest_cidr || null,
      dest_label: ruleForm.dest_label || null,
      port: ruleForm.port ? parseInt(ruleForm.port) : null,
      port_range_end: ruleForm.port_range_end ? parseInt(ruleForm.port_range_end) : null,
      protocol: ruleForm.protocol,
      service_label: ruleForm.service_label || null,
      action: ruleForm.action,
      description: ruleForm.description || null,
      is_enabled: ruleForm.is_enabled,
      priority: ruleForm.priority,
    };

    if (editingRule) {
      updateRuleMutation.mutate({
        ruleId: editingRule.id,
        updates: {
          priority: ruleData.priority,
          is_enabled: ruleData.is_enabled,
          description: ruleData.description,
          action: ruleData.action,
          source_label: ruleData.source_label,
          dest_label: ruleData.dest_label,
          service_label: ruleData.service_label,
        },
      });
    } else {
      addRuleMutation.mutate(ruleData);
    }
  };

  const handleExport = async (format: 'json' | 'csv') => {
    await downloadWithAuth(
      segmentationApi.exportUrl(id!, format),
      `policy-${policy?.name || id}.${format}`
    );
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  if (error || !policy) {
    return (
      <div className="flex items-center justify-center h-96">
        <p className="text-red-500">Failed to load policy</p>
      </div>
    );
  }

  // Filter rules by type
  const filteredRules = ruleTypeFilter
    ? policy.rules.filter((r) => r.rule_type === ruleTypeFilter)
    : policy.rules;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/segmentation-policies" className="text-slate-400 hover:text-white">
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <ShieldCheckIcon className="w-6 h-6 text-primary-400" />
              <h1 className="text-2xl font-semibold text-white">{policy.name}</h1>
              <span
                className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[policy.status].bg} ${STATUS_COLORS[policy.status].text}`}
              >
                {STATUS_LABELS[policy.status]}
              </span>
            </div>
            <p className="text-slate-400 mt-1">
              Application: {application?.name || policy.application_id.slice(0, 8)} | Version{' '}
              {policy.version} |{' '}
              {policy.stance === 'allow_list' ? 'Allow List' : 'Deny List'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Workflow Actions */}
          {policy.status === 'draft' && (
            <Button
              variant="secondary"
              onClick={() => submitForReviewMutation.mutate()}
              disabled={submitForReviewMutation.isPending}
            >
              <ClockIcon className="w-4 h-4 mr-2" />
              Submit for Review
            </Button>
          )}
          {policy.status === 'pending_review' && (
            <Button
              variant="secondary"
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending}
            >
              <CheckIcon className="w-4 h-4 mr-2" />
              Approve
            </Button>
          )}
          {policy.status === 'approved' && (
            <Button
              variant="primary"
              onClick={() => activateMutation.mutate()}
              disabled={activateMutation.isPending}
            >
              <CheckIcon className="w-4 h-4 mr-2" />
              Activate
            </Button>
          )}
          {policy.status !== 'archived' && (
            <Button
              variant="ghost"
              onClick={() => {
                if (confirm('Archive this policy?')) {
                  archiveMutation.mutate();
                }
              }}
            >
              <ArchiveBoxIcon className="w-4 h-4 mr-2" />
              Archive
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => regenerateMutation.mutate()}
            disabled={regenerateMutation.isPending}
          >
            <ArrowPathIcon className="w-4 h-4 mr-2" />
            Regenerate
          </Button>
          <Button
            variant="ghost"
            className="text-red-400 hover:text-red-300"
            onClick={() => {
              if (confirm('Delete this policy? This cannot be undone.')) {
                deletePolicyMutation.mutate();
              }
            }}
          >
            <TrashIcon className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="!p-4">
          <div className="text-2xl font-bold text-white">{policy.rule_count}</div>
          <div className="text-sm text-slate-400">Total Rules</div>
        </Card>
        <Card className="!p-4">
          <div className="text-2xl font-bold text-green-400">{policy.inbound_rule_count}</div>
          <div className="text-sm text-slate-400">Inbound</div>
        </Card>
        <Card className="!p-4">
          <div className="text-2xl font-bold text-purple-400">{policy.internal_rule_count}</div>
          <div className="text-sm text-slate-400">Internal</div>
        </Card>
        <Card className="!p-4">
          <div className="text-2xl font-bold text-blue-400">{policy.outbound_rule_count}</div>
          <div className="text-sm text-slate-400">Outbound</div>
        </Card>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-700">
        <nav className="flex gap-4">
          {(['rules', 'versions', 'export'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-primary-500 text-primary-400'
                  : 'border-transparent text-slate-400 hover:text-white'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'rules' && (
        <div className="space-y-4">
          {/* Rules Filter & Actions */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <select
                value={ruleTypeFilter}
                onChange={(e) => setRuleTypeFilter(e.target.value as RuleType | '')}
                className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">All Rule Types</option>
                <option value="inbound">Inbound</option>
                <option value="internal">Internal</option>
                <option value="outbound">Outbound</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                onClick={() => publishVersionMutation.mutate()}
                disabled={publishVersionMutation.isPending}
              >
                <DocumentDuplicateIcon className="w-4 h-4 mr-2" />
                Publish Version
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  setEditingRule(null);
                  setRuleForm(emptyRuleForm);
                  setShowRuleModal(true);
                }}
              >
                <PlusIcon className="w-4 h-4 mr-2" />
                Add Rule
              </Button>
            </div>
          </div>

          {/* Rules Table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                    <th className="pb-3 font-medium">Type</th>
                    <th className="pb-3 font-medium">Source</th>
                    <th className="pb-3 font-medium">Destination</th>
                    <th className="pb-3 font-medium">Port/Protocol</th>
                    <th className="pb-3 font-medium">Action</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {filteredRules.map((rule) => (
                    <tr key={rule.id} className="text-slate-200">
                      <td className="py-3">
                        <span
                          className={`px-2 py-1 text-xs rounded-full ${RULE_TYPE_COLORS[rule.rule_type].bg} ${RULE_TYPE_COLORS[rule.rule_type].text}`}
                        >
                          {rule.rule_type}
                        </span>
                      </td>
                      <td className="py-3">
                        <div className="text-sm">
                          {rule.source_label || rule.source_cidr || 'Any'}
                        </div>
                        <div className="text-xs text-slate-500">{rule.source_type}</div>
                      </td>
                      <td className="py-3">
                        <div className="text-sm">
                          {rule.dest_label || rule.dest_cidr || 'App Member'}
                        </div>
                        <div className="text-xs text-slate-500">{rule.dest_type}</div>
                      </td>
                      <td className="py-3 font-mono text-sm">
                        {rule.port
                          ? rule.port_range_end
                            ? `${rule.port}-${rule.port_range_end}`
                            : rule.port
                          : 'Any'}
                        /{PROTOCOL_NAMES[rule.protocol] || rule.protocol}
                      </td>
                      <td className="py-3">
                        <span
                          className={`px-2 py-1 text-xs rounded-full ${ACTION_COLORS[rule.action].bg} ${ACTION_COLORS[rule.action].text}`}
                        >
                          {rule.action}
                        </span>
                      </td>
                      <td className="py-3">
                        <span
                          className={`px-2 py-1 text-xs rounded-full ${
                            rule.is_enabled
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-slate-500/20 text-slate-400'
                          }`}
                        >
                          {rule.is_enabled ? 'Enabled' : 'Disabled'}
                        </span>
                        {rule.is_auto_generated && (
                          <span className="ml-1 px-2 py-1 text-xs rounded-full bg-slate-600/20 text-slate-500">
                            Auto
                          </span>
                        )}
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleEditRule(rule)}
                          >
                            <PencilIcon className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-400 hover:text-red-300"
                            onClick={() => {
                              if (confirm('Delete this rule?')) {
                                deleteRuleMutation.mutate(rule.id);
                              }
                            }}
                          >
                            <TrashIcon className="w-4 h-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filteredRules.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        No rules found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'versions' && (
        <div className="space-y-4">
          <Card title="Version History">
            {versions && versions.length > 0 ? (
              <div className="space-y-3">
                {versions.map((version: SegmentationPolicyVersion) => (
                  <div
                    key={version.id}
                    className="flex items-center justify-between p-3 bg-slate-700/50 rounded-lg"
                  >
                    <div>
                      <div className="font-medium text-white">
                        Version {version.version_number}
                        {version.version_label && (
                          <span className="ml-2 text-slate-400">({version.version_label})</span>
                        )}
                      </div>
                      <div className="text-sm text-slate-400">
                        {new Date(version.created_at).toLocaleString()}
                        {version.created_by && ` by ${version.created_by}`}
                      </div>
                      <div className="text-xs text-slate-500 mt-1">
                        +{version.rules_added} added, -{version.rules_removed} removed, ~
                        {version.rules_modified} modified
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setCompareVersions({
                            a: version.version_number - 1,
                            b: version.version_number,
                          })
                        }
                        disabled={version.version_number === 1}
                      >
                        Compare
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400">No versions published yet</p>
            )}
          </Card>

          {/* Comparison View */}
          {comparison && (
            <Card title={`Comparison: v${compareVersions?.a} → v${compareVersions?.b}`}>
              <div className="space-y-4">
                <p className="text-slate-300">{comparison.summary}</p>
                {comparison.rules_added.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-green-400 mb-2">
                      Added ({comparison.rules_added.length})
                    </h4>
                    <div className="space-y-1">
                      {comparison.rules_added.map((diff, i) => (
                        <div key={i} className="text-sm text-slate-300 p-2 bg-green-500/10 rounded">
                          {JSON.stringify(diff.rule_data)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {comparison.rules_removed.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-red-400 mb-2">
                      Removed ({comparison.rules_removed.length})
                    </h4>
                    <div className="space-y-1">
                      {comparison.rules_removed.map((diff, i) => (
                        <div key={i} className="text-sm text-slate-300 p-2 bg-red-500/10 rounded">
                          {JSON.stringify(diff.rule_data)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {comparison.rules_modified.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-yellow-400 mb-2">
                      Modified ({comparison.rules_modified.length})
                    </h4>
                    <div className="space-y-1">
                      {comparison.rules_modified.map((diff, i) => (
                        <div
                          key={i}
                          className="text-sm text-slate-300 p-2 bg-yellow-500/10 rounded"
                        >
                          Changed fields: {diff.changed_fields?.join(', ')}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <Button variant="ghost" onClick={() => setCompareVersions(null)}>
                  Close Comparison
                </Button>
              </div>
            </Card>
          )}
        </div>
      )}

      {activeTab === 'export' && (
        <div className="space-y-4">
          <Card title="Export Policy">
            <p className="text-slate-400 mb-4">
              Export this policy as generic firewall rules that can be imported into your firewall
              management system.
            </p>
            <div className="flex items-center gap-4">
              <Button variant="secondary" onClick={() => handleExport('json')}>
                <ArrowDownTrayIcon className="w-4 h-4 mr-2" />
                Export as JSON
              </Button>
              <Button variant="secondary" onClick={() => handleExport('csv')}>
                <ArrowDownTrayIcon className="w-4 h-4 mr-2" />
                Export as CSV
              </Button>
            </div>
          </Card>

          <Card title="Export Format">
            <div className="text-sm text-slate-400 space-y-2">
              <p>The export includes the following fields for each rule:</p>
              <ul className="list-disc list-inside space-y-1 text-slate-300">
                <li>rule_id - Unique identifier</li>
                <li>priority - Rule priority (lower is higher priority)</li>
                <li>action - allow or deny</li>
                <li>source_cidr - Source IP/CIDR</li>
                <li>dest_cidr - Destination IP/CIDR</li>
                <li>port - Port number or range</li>
                <li>protocol - tcp, udp, or any</li>
                <li>description - Rule description</li>
                <li>application_name - Parent application</li>
                <li>rule_type - inbound, outbound, or internal</li>
              </ul>
            </div>
          </Card>
        </div>
      )}

      {/* Add/Edit Rule Modal */}
      {showRuleModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">
                {editingRule ? 'Edit Rule' : 'Add Rule'}
              </h2>
              <button
                onClick={() => {
                  setShowRuleModal(false);
                  setEditingRule(null);
                  setRuleForm(emptyRuleForm);
                }}
                className="text-slate-400 hover:text-white"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleSubmitRule} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Rule Type</label>
                  <select
                    value={ruleForm.rule_type}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, rule_type: e.target.value as RuleType })
                    }
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  >
                    <option value="inbound">Inbound</option>
                    <option value="internal">Internal</option>
                    <option value="outbound">Outbound</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Action</label>
                  <select
                    value={ruleForm.action}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, action: e.target.value as RuleAction })
                    }
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="allow">Allow</option>
                    <option value="deny">Deny</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Source Type</label>
                  <select
                    value={ruleForm.source_type}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, source_type: e.target.value as SourceDestType })
                    }
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  >
                    <option value="any">Any</option>
                    <option value="cidr">CIDR</option>
                    <option value="app_member">App Member</option>
                    <option value="asset">Asset</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Source CIDR</label>
                  <input
                    type="text"
                    value={ruleForm.source_cidr}
                    onChange={(e) => setRuleForm({ ...ruleForm, source_cidr: e.target.value })}
                    placeholder="0.0.0.0/0"
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Source Label</label>
                <input
                  type="text"
                  value={ruleForm.source_label}
                  onChange={(e) => setRuleForm({ ...ruleForm, source_label: e.target.value })}
                  placeholder="e.g., External Clients"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Destination Type</label>
                  <select
                    value={ruleForm.dest_type}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, dest_type: e.target.value as SourceDestType })
                    }
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  >
                    <option value="app_member">App Member</option>
                    <option value="cidr">CIDR</option>
                    <option value="asset">Asset</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Destination CIDR</label>
                  <input
                    type="text"
                    value={ruleForm.dest_cidr}
                    onChange={(e) => setRuleForm({ ...ruleForm, dest_cidr: e.target.value })}
                    placeholder="10.0.0.1/32"
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Destination Label</label>
                <input
                  type="text"
                  value={ruleForm.dest_label}
                  onChange={(e) => setRuleForm({ ...ruleForm, dest_label: e.target.value })}
                  placeholder="e.g., Web Server"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Port</label>
                  <input
                    type="number"
                    value={ruleForm.port}
                    onChange={(e) => setRuleForm({ ...ruleForm, port: e.target.value })}
                    placeholder="Any"
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Port Range End</label>
                  <input
                    type="number"
                    value={ruleForm.port_range_end}
                    onChange={(e) => setRuleForm({ ...ruleForm, port_range_end: e.target.value })}
                    placeholder="Optional"
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Protocol</label>
                  <select
                    value={ruleForm.protocol}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, protocol: parseInt(e.target.value) })
                    }
                    disabled={!!editingRule}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                  >
                    <option value={6}>TCP</option>
                    <option value={17}>UDP</option>
                    <option value={1}>ICMP</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Service Label</label>
                  <input
                    type="text"
                    value={ruleForm.service_label}
                    onChange={(e) => setRuleForm({ ...ruleForm, service_label: e.target.value })}
                    placeholder="e.g., HTTPS"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Priority</label>
                  <input
                    type="number"
                    value={ruleForm.priority}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, priority: parseInt(e.target.value) || 100 })
                    }
                    min={0}
                    max={10000}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Description</label>
                <textarea
                  value={ruleForm.description}
                  onChange={(e) => setRuleForm({ ...ruleForm, description: e.target.value })}
                  rows={2}
                  placeholder="Optional description"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is-enabled"
                  checked={ruleForm.is_enabled}
                  onChange={(e) => setRuleForm({ ...ruleForm, is_enabled: e.target.checked })}
                  className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                />
                <label htmlFor="is-enabled" className="text-sm text-slate-300">
                  Rule is enabled
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-700">
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setShowRuleModal(false);
                    setEditingRule(null);
                    setRuleForm(emptyRuleForm);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  type="submit"
                  disabled={addRuleMutation.isPending || updateRuleMutation.isPending}
                >
                  {addRuleMutation.isPending || updateRuleMutation.isPending
                    ? 'Saving...'
                    : editingRule
                      ? 'Update Rule'
                      : 'Add Rule'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}
