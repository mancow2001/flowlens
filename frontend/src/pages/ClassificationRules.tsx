import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowDownTrayIcon, ArrowUpTrayIcon, XMarkIcon } from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import {
  classificationApi,
  ClassificationRule,
  ClassificationRuleSummary,
  ClassificationRuleImportPreview,
  downloadWithAuth,
} from '../services/api';
import { ENVIRONMENT_OPTIONS } from '../types';

interface RuleFormData {
  name: string;
  description: string;
  cidr: string;
  priority: number;
  environment: string;
  datacenter: string;
  location: string;
  asset_type: string;
  is_internal: boolean | null;
  default_owner: string;
  default_team: string;
  is_active: boolean;
}

const emptyFormData: RuleFormData = {
  name: '',
  description: '',
  cidr: '',
  priority: 100,
  environment: '',
  datacenter: '',
  location: '',
  asset_type: '',
  is_internal: null,
  default_owner: '',
  default_team: '',
  is_active: true,
};

const ASSET_TYPES = [
  'server',
  'workstation',
  'database',
  'load_balancer',
  'firewall',
  'router',
  'switch',
  'storage',
  'container',
  'virtual_machine',
  'cloud_service',
  'unknown',
];

export default function ClassificationRules() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<ClassificationRule | null>(null);
  const [formData, setFormData] = useState<RuleFormData>(emptyFormData);
  const [testIp, setTestIp] = useState('');
  const [testResult, setTestResult] = useState<{
    matched: boolean;
    rule_name: string | null;
    environment: string | null;
    datacenter: string | null;
    location: string | null;
  } | null>(null);

  // Import modal state
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<ClassificationRuleImportPreview | null>(null);
  const [skipErrors, setSkipErrors] = useState(false);
  const [autoApply, setAutoApply] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch rules
  const { data: rulesData, isLoading } = useQuery({
    queryKey: ['classification-rules'],
    queryFn: () => classificationApi.list({ page_size: 100 }),
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: RuleFormData) => classificationApi.create({
      name: data.name,
      description: data.description || null,
      cidr: data.cidr,
      priority: data.priority,
      environment: data.environment || null,
      datacenter: data.datacenter || null,
      location: data.location || null,
      asset_type: data.asset_type || null,
      is_internal: data.is_internal,
      default_owner: data.default_owner || null,
      default_team: data.default_team || null,
      is_active: data.is_active,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classification-rules'] });
      setShowModal(false);
      setFormData(emptyFormData);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RuleFormData }) => classificationApi.update(id, {
      name: data.name,
      description: data.description || null,
      cidr: data.cidr,
      priority: data.priority,
      environment: data.environment || null,
      datacenter: data.datacenter || null,
      location: data.location || null,
      asset_type: data.asset_type || null,
      is_internal: data.is_internal,
      default_owner: data.default_owner || null,
      default_team: data.default_team || null,
      is_active: data.is_active,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classification-rules'] });
      setShowModal(false);
      setEditingRule(null);
      setFormData(emptyFormData);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => classificationApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classification-rules'] });
    },
  });

  // Import preview mutation
  const previewImportMutation = useMutation({
    mutationFn: (file: File) => classificationApi.previewImport(file),
    onSuccess: (data) => {
      setImportPreview(data);
    },
  });

  // Import mutation
  const importMutation = useMutation({
    mutationFn: ({ file, skipErrors, autoApply }: { file: File; skipErrors: boolean; autoApply: boolean }) =>
      classificationApi.import(file, skipErrors, autoApply),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classification-rules'] });
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
      importMutation.mutate({ file: importFile, skipErrors, autoApply });
    }
  };

  const handleExport = async (format: 'csv' | 'json') => {
    await downloadWithAuth(classificationApi.exportUrl(format), `classification-rules.${format}`);
  };

  const closeImportModal = () => {
    setShowImportModal(false);
    setImportFile(null);
    setImportPreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleEdit = (rule: ClassificationRuleSummary) => {
    classificationApi.get(rule.id).then((fullRule) => {
      setEditingRule(fullRule);
      setFormData({
        name: fullRule.name,
        description: fullRule.description || '',
        cidr: fullRule.cidr,
        priority: fullRule.priority,
        environment: fullRule.environment || '',
        datacenter: fullRule.datacenter || '',
        location: fullRule.location || '',
        asset_type: fullRule.asset_type || '',
        is_internal: fullRule.is_internal,
        default_owner: fullRule.default_owner || '',
        default_team: fullRule.default_team || '',
        is_active: fullRule.is_active,
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

  const handleTestIp = async () => {
    if (!testIp) return;
    try {
      const result = await classificationApi.classifyIp(testIp);
      setTestResult({
        matched: result.matched,
        rule_name: result.rule_name,
        environment: result.environment,
        datacenter: result.datacenter,
        location: result.location,
      });
    } catch {
      setTestResult({
        matched: false,
        rule_name: null,
        environment: null,
        datacenter: null,
        location: null,
      });
    }
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  const rules = rulesData?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Classification Rules</h1>
          <p className="text-slate-400 mt-1">
            Define CIDR-based rules to automatically classify assets by environment, datacenter, and location
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Export Dropdown */}
          <div className="relative group">
            <Button variant="secondary">
              <ArrowDownTrayIcon className="w-4 h-4 mr-2" />
              Export
            </Button>
            <div className="absolute right-0 mt-1 w-40 bg-slate-800 border border-slate-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              <button
                onClick={() => handleExport('json')}
                className="w-full px-4 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 rounded-t-lg"
              >
                Export as JSON
              </button>
              <button
                onClick={() => handleExport('csv')}
                className="w-full px-4 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 rounded-b-lg"
              >
                Export as CSV
              </button>
            </div>
          </div>
          {/* Import Button */}
          <Button variant="secondary" onClick={() => setShowImportModal(true)}>
            <ArrowUpTrayIcon className="w-4 h-4 mr-2" />
            Import
          </Button>
          {/* Add Rule Button */}
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
      </div>

      {/* Test IP Tool */}
      <Card title="Test IP Classification">
        <div className="flex items-center gap-4">
          <input
            type="text"
            value={testIp}
            onChange={(e) => setTestIp(e.target.value)}
            placeholder="Enter IP address (e.g., 10.1.2.3)"
            className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <Button variant="secondary" onClick={handleTestIp}>
            Test
          </Button>
        </div>
        {testResult && (
          <div className="mt-4 p-3 bg-slate-700/50 rounded-lg">
            {testResult.matched ? (
              <div className="space-y-1">
                <p className="text-green-400">
                  Matched rule: <span className="font-semibold">{testResult.rule_name}</span>
                </p>
                <div className="flex gap-4 text-sm text-slate-300">
                  {testResult.environment && <span>Environment: {testResult.environment}</span>}
                  {testResult.datacenter && <span>Datacenter: {testResult.datacenter}</span>}
                  {testResult.location && <span>Location: {testResult.location}</span>}
                </div>
              </div>
            ) : (
              <p className="text-yellow-400">No matching classification rule found</p>
            )}
          </div>
        )}
      </Card>

      {/* Rules Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                <th className="pb-3 font-medium">Name</th>
                <th className="pb-3 font-medium">CIDR</th>
                <th className="pb-3 font-medium">Priority</th>
                <th className="pb-3 font-medium">Environment</th>
                <th className="pb-3 font-medium">Datacenter</th>
                <th className="pb-3 font-medium">Location</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rules.map((rule) => (
                <tr key={rule.id} className="text-slate-200">
                  <td className="py-3 font-medium">{rule.name}</td>
                  <td className="py-3 font-mono text-sm">{rule.cidr}</td>
                  <td className="py-3">{/* Priority not in summary, show dash */}-</td>
                  <td className="py-3">{rule.environment || '-'}</td>
                  <td className="py-3">{rule.datacenter || '-'}</td>
                  <td className="py-3">{rule.location || '-'}</td>
                  <td className="py-3">
                    <span
                      className={`px-2 py-1 text-xs rounded-full ${
                        rule.is_active
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-slate-500/20 text-slate-400'
                      }`}
                    >
                      {rule.is_active ? 'Active' : 'Inactive'}
                    </span>
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
                          if (confirm('Delete this classification rule?')) {
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
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    No classification rules defined. Add a rule to start classifying assets.
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
              {editingRule ? 'Edit Classification Rule' : 'Add Classification Rule'}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm text-slate-400 mb-1">Rule Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    placeholder="e.g., Production Servers"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">CIDR Range *</label>
                  <input
                    type="text"
                    value={formData.cidr}
                    onChange={(e) => setFormData({ ...formData, cidr: e.target.value })}
                    required
                    placeholder="e.g., 10.0.0.0/8"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Priority</label>
                  <input
                    type="number"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) || 100 })}
                    min={0}
                    max={1000}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <p className="text-xs text-slate-500 mt-1">Lower priority wins for equal prefix lengths</p>
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Environment</label>
                  <select
                    value={formData.environment}
                    onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Not specified</option>
                    {ENVIRONMENT_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Datacenter</label>
                  <input
                    type="text"
                    value={formData.datacenter}
                    onChange={(e) => setFormData({ ...formData, datacenter: e.target.value })}
                    placeholder="e.g., US-East-1"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Location</label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                    placeholder="e.g., New York"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Asset Type</label>
                  <select
                    value={formData.asset_type}
                    onChange={(e) => setFormData({ ...formData, asset_type: e.target.value })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Not specified</option>
                    {ASSET_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Is Internal</label>
                  <select
                    value={formData.is_internal === null ? '' : String(formData.is_internal)}
                    onChange={(e) => setFormData({
                      ...formData,
                      is_internal: e.target.value === '' ? null : e.target.value === 'true',
                    })}
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Not specified</option>
                    <option value="true">Internal</option>
                    <option value="false">External</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Default Owner</label>
                  <input
                    type="text"
                    value={formData.default_owner}
                    onChange={(e) => setFormData({ ...formData, default_owner: e.target.value })}
                    placeholder="e.g., john.doe@example.com"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-slate-400 mb-1">Default Team</label>
                  <input
                    type="text"
                    value={formData.default_team}
                    onChange={(e) => setFormData({ ...formData, default_team: e.target.value })}
                    placeholder="e.g., Platform Team"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div className="col-span-2">
                  <label className="block text-sm text-slate-400 mb-1">Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    rows={2}
                    placeholder="Optional description for this rule"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div className="col-span-2 flex items-center gap-2">
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
                  disabled={createMutation.isPending || updateMutation.isPending}
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

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Import Classification Rules</h2>
              <button onClick={closeImportModal} className="text-slate-400 hover:text-white">
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            {/* File Input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.json"
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
                <p className="text-sm text-slate-500">Supports CSV and JSON formats</p>
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
                        <div className="text-xs text-slate-400">Total Rows</div>
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
                          checked={autoApply}
                          onChange={(e) => setAutoApply(e.target.checked)}
                          className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                        />
                        Auto-apply rules to assets after import
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
                {importMutation.isPending ? 'Importing...' : 'Import Rules'}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
