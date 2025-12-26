import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { alertRulesApi, AlertRule, AlertRuleSummary, ChangeTypeInfo } from '../services/api';

interface RuleFormData {
  name: string;
  description: string;
  is_active: boolean;
  change_types: string[];
  asset_filter: Record<string, unknown> | null;
  severity: string;
  title_template: string;
  description_template: string;
  notify_channels: string[];
  cooldown_minutes: number;
  priority: number;
}

const emptyFormData: RuleFormData = {
  name: '',
  description: '',
  is_active: true,
  change_types: [],
  asset_filter: null,
  severity: 'warning',
  title_template: '{change_type} detected',
  description_template: '{summary}',
  notify_channels: [],
  cooldown_minutes: 60,
  priority: 100,
};

const SEVERITIES = [
  { value: 'critical', label: 'Critical', color: 'bg-red-500/20 text-red-400' },
  { value: 'error', label: 'Error', color: 'bg-orange-500/20 text-orange-400' },
  { value: 'warning', label: 'Warning', color: 'bg-yellow-500/20 text-yellow-400' },
  { value: 'info', label: 'Info', color: 'bg-blue-500/20 text-blue-400' },
];

const NOTIFICATION_CHANNELS = [
  { value: 'email', label: 'Email' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'slack', label: 'Slack' },
  { value: 'teams', label: 'Microsoft Teams' },
  { value: 'pagerduty', label: 'PagerDuty' },
];

function getSeverityClass(severity: string): string {
  const found = SEVERITIES.find(s => s.value === severity);
  return found?.color || 'bg-slate-500/20 text-slate-400';
}

export default function AlertRules() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [formData, setFormData] = useState<RuleFormData>(emptyFormData);

  // Fetch rules
  const { data: rulesData, isLoading } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: () => alertRulesApi.list({ page_size: 100 }),
  });

  // Fetch change types
  const { data: changeTypes } = useQuery({
    queryKey: ['alert-rules', 'change-types'],
    queryFn: () => alertRulesApi.listChangeTypes(),
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: RuleFormData) => alertRulesApi.create({
      name: data.name,
      description: data.description || null,
      is_active: data.is_active,
      change_types: data.change_types,
      asset_filter: data.asset_filter,
      severity: data.severity,
      title_template: data.title_template,
      description_template: data.description_template,
      notify_channels: data.notify_channels.length > 0 ? data.notify_channels : null,
      cooldown_minutes: data.cooldown_minutes,
      priority: data.priority,
      schedule: null,
      tags: null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] });
      setShowModal(false);
      setFormData(emptyFormData);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RuleFormData }) => alertRulesApi.update(id, {
      name: data.name,
      description: data.description || null,
      is_active: data.is_active,
      change_types: data.change_types,
      asset_filter: data.asset_filter,
      severity: data.severity,
      title_template: data.title_template,
      description_template: data.description_template,
      notify_channels: data.notify_channels.length > 0 ? data.notify_channels : null,
      cooldown_minutes: data.cooldown_minutes,
      priority: data.priority,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] });
      setShowModal(false);
      setEditingRule(null);
      setFormData(emptyFormData);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => alertRulesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] });
    },
  });

  // Toggle mutation
  const toggleMutation = useMutation({
    mutationFn: (id: string) => alertRulesApi.toggle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] });
    },
  });

  const handleEdit = (rule: AlertRuleSummary) => {
    alertRulesApi.get(rule.id).then((fullRule) => {
      setEditingRule(fullRule);
      setFormData({
        name: fullRule.name,
        description: fullRule.description || '',
        is_active: fullRule.is_active,
        change_types: fullRule.change_types,
        asset_filter: fullRule.asset_filter,
        severity: fullRule.severity,
        title_template: fullRule.title_template,
        description_template: fullRule.description_template,
        notify_channels: fullRule.notify_channels || [],
        cooldown_minutes: fullRule.cooldown_minutes,
        priority: fullRule.priority,
      });
      setShowModal(true);
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingRule) {
      updateMutation.mutate({ id: editingRule.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
  };

  const toggleChangeType = (value: string) => {
    setFormData(prev => ({
      ...prev,
      change_types: prev.change_types.includes(value)
        ? prev.change_types.filter(t => t !== value)
        : [...prev.change_types, value],
    }));
  };

  const toggleChannel = (value: string) => {
    setFormData(prev => ({
      ...prev,
      notify_channels: prev.notify_channels.includes(value)
        ? prev.notify_channels.filter(c => c !== value)
        : [...prev.notify_channels, value],
    }));
  };

  // Group change types by category
  const groupedChangeTypes = (changeTypes || []).reduce((acc, ct) => {
    if (!acc[ct.category]) {
      acc[ct.category] = [];
    }
    acc[ct.category].push(ct);
    return acc;
  }, {} as Record<string, ChangeTypeInfo[]>);

  if (isLoading) {
    return <LoadingPage />;
  }

  const rules = rulesData?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Alert Rules</h1>
          <p className="text-slate-400 mt-1">
            Configure rules to automatically generate alerts from change events
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditingRule(null);
            setFormData(emptyFormData);
            setShowModal(true);
          }}
        >
          Add Rule
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <div className="text-sm text-slate-400">Total Rules</div>
          <div className="text-2xl font-bold text-white">{rules.length}</div>
        </Card>
        <Card>
          <div className="text-sm text-slate-400">Active Rules</div>
          <div className="text-2xl font-bold text-green-400">
            {rules.filter(r => r.is_active).length}
          </div>
        </Card>
        <Card>
          <div className="text-sm text-slate-400">Critical Rules</div>
          <div className="text-2xl font-bold text-red-400">
            {rules.filter(r => r.severity === 'critical').length}
          </div>
        </Card>
        <Card>
          <div className="text-sm text-slate-400">Total Triggers</div>
          <div className="text-2xl font-bold text-white">
            {rules.reduce((sum, r) => sum + r.trigger_count, 0)}
          </div>
        </Card>
      </div>

      {/* Rules Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                <th className="pb-3 font-medium">Name</th>
                <th className="pb-3 font-medium">Change Types</th>
                <th className="pb-3 font-medium">Severity</th>
                <th className="pb-3 font-medium">Cooldown</th>
                <th className="pb-3 font-medium">Triggers</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rules.map((rule) => (
                <tr key={rule.id} className="text-slate-200">
                  <td className="py-3">
                    <div className="font-medium">{rule.name}</div>
                    <div className="text-sm text-slate-500">Priority: {rule.priority}</div>
                  </td>
                  <td className="py-3">
                    <div className="flex flex-wrap gap-1 max-w-xs">
                      {rule.change_types.slice(0, 3).map(ct => (
                        <span
                          key={ct}
                          className="px-2 py-0.5 bg-slate-700 text-slate-300 text-xs rounded"
                        >
                          {ct.replace(/_/g, ' ')}
                        </span>
                      ))}
                      {rule.change_types.length > 3 && (
                        <span className="px-2 py-0.5 bg-slate-700 text-slate-400 text-xs rounded">
                          +{rule.change_types.length - 3} more
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3">
                    <span className={`px-2 py-1 text-xs rounded-full ${getSeverityClass(rule.severity)}`}>
                      {rule.severity}
                    </span>
                  </td>
                  <td className="py-3">{rule.cooldown_minutes}m</td>
                  <td className="py-3">
                    <div>{rule.trigger_count}</div>
                    {rule.last_triggered_at && (
                      <div className="text-xs text-slate-500">
                        Last: {new Date(rule.last_triggered_at).toLocaleDateString()}
                      </div>
                    )}
                  </td>
                  <td className="py-3">
                    <button
                      onClick={() => toggleMutation.mutate(rule.id)}
                      className={`px-2 py-1 text-xs rounded-full transition-colors ${
                        rule.is_active
                          ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                          : 'bg-slate-500/20 text-slate-400 hover:bg-slate-500/30'
                      }`}
                    >
                      {rule.is_active ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td className="py-3">
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEdit(rule)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 hover:text-red-300"
                        onClick={() => {
                          if (confirm('Delete this alert rule?')) {
                            deleteMutation.mutate(rule.id);
                          }
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    No alert rules defined. Add a rule to start generating alerts.
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
          <Card className="w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold text-white mb-4">
              {editingRule ? 'Edit Alert Rule' : 'Add Alert Rule'}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm text-slate-400 mb-1">Rule Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    placeholder="e.g., Critical Asset Changes"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Severity *</label>
                  <select
                    value={formData.severity}
                    onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    {SEVERITIES.map(s => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Priority</label>
                  <input
                    type="number"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 100 })}
                    min={0}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <p className="text-xs text-slate-500 mt-1">Lower priority = higher precedence</p>
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Cooldown (minutes)</label>
                  <input
                    type="number"
                    value={formData.cooldown_minutes}
                    onChange={(e) => setFormData({ ...formData, cooldown_minutes: parseInt(e.target.value) || 0 })}
                    min={0}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <p className="text-xs text-slate-500 mt-1">Don't re-alert within this period</p>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is-active"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  <label htmlFor="is-active" className="text-sm text-slate-300">
                    Rule is active
                  </label>
                </div>
              </div>

              {/* Change Types */}
              <div>
                <label className="block text-sm text-slate-400 mb-2">Change Types *</label>
                <div className="space-y-4">
                  {Object.entries(groupedChangeTypes).map(([category, types]) => (
                    <div key={category}>
                      <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">
                        {category}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {types.map(ct => (
                          <button
                            key={ct.value}
                            type="button"
                            onClick={() => toggleChangeType(ct.value)}
                            className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                              formData.change_types.includes(ct.value)
                                ? 'bg-primary-500 text-white'
                                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                            }`}
                          >
                            {ct.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                {formData.change_types.length === 0 && (
                  <p className="text-xs text-red-400 mt-1">Select at least one change type</p>
                )}
              </div>

              {/* Notification Channels */}
              <div>
                <label className="block text-sm text-slate-400 mb-2">Notification Channels</label>
                <div className="flex flex-wrap gap-2">
                  {NOTIFICATION_CHANNELS.map(ch => (
                    <button
                      key={ch.value}
                      type="button"
                      onClick={() => toggleChannel(ch.value)}
                      className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                        formData.notify_channels.includes(ch.value)
                          ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600 border border-transparent'
                      }`}
                    >
                      {ch.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Leave empty to only create alerts without sending notifications
                </p>
              </div>

              {/* Templates */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Title Template</label>
                  <input
                    type="text"
                    value={formData.title_template}
                    onChange={(e) => setFormData({ ...formData, title_template: e.target.value })}
                    placeholder="{change_type} detected"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Description Template</label>
                  <input
                    type="text"
                    value={formData.description_template}
                    onChange={(e) => setFormData({ ...formData, description_template: e.target.value })}
                    placeholder="{summary}"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                <div className="col-span-2 text-xs text-slate-500">
                  Available placeholders: {'{change_type}'}, {'{summary}'}, {'{asset_name}'}, {'{asset_ip}'}
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={2}
                  placeholder="Optional description for this rule"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-700">
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditingRule(null);
                    setFormData(emptyFormData);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending || formData.change_types.length === 0}
                >
                  {createMutation.isPending || updateMutation.isPending
                    ? 'Saving...'
                    : editingRule
                    ? 'Update Rule'
                    : 'Create Rule'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}
