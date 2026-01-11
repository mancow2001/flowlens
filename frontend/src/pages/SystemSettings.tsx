import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { settingsApi, FieldMetadata } from '../services/api';
import {
  Cog6ToothIcon,
  CircleStackIcon,
  BoltIcon,
  ArrowsRightLeftIcon,
  ArrowDownTrayIcon,
  SparklesIcon,
  ShareIcon,
  GlobeAltIcon,
  LockClosedIcon,
  DocumentTextIcon,
  EnvelopeIcon,
  LinkIcon,
  ChatBubbleLeftRightIcon,
  ChatBubbleOvalLeftIcon,
  BellAlertIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ArrowPathIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline';

// Icon mapping
const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  Cog6ToothIcon,
  CircleStackIcon,
  BoltIcon,
  ArrowsRightLeftIcon,
  ArrowDownTrayIcon,
  SparklesIcon,
  ShareIcon,
  GlobeAltIcon,
  LockClosedIcon,
  DocumentTextIcon,
  EnvelopeIcon,
  LinkIcon,
  ChatBubbleLeftRightIcon,
  ChatBubbleOvalLeftIcon,
  BellAlertIcon,
};

interface FormData {
  [key: string]: string | number | boolean | null;
}

export default function SystemSettings() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>('application');
  const [formData, setFormData] = useState<FormData>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const [testingConnection, setTestingConnection] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [dockerMode, setDockerMode] = useState(false);

  // Fetch all sections metadata
  const { data: settingsData, isLoading: loadingSections } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.getAll(),
  });

  // Fetch current section data
  const { data: sectionData, isLoading: loadingSection, refetch: refetchSection } = useQuery({
    queryKey: ['settings', activeTab],
    queryFn: () => settingsApi.getSection(activeTab),
    enabled: !!activeTab,
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ section, values }: { section: string; values: FormData }) =>
      settingsApi.updateSection(section, values),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['settings', activeTab] });
      setHasChanges(false);
      // Track Docker mode for download button
      if (result.docker_mode) {
        setDockerMode(true);
      }
      // Show success message
      alert(result.message);
    },
    onError: (error: Error) => {
      alert(`Failed to save: ${error.message}`);
    },
  });

  // Restart mutation
  const restartMutation = useMutation({
    mutationFn: () => settingsApi.restart(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      alert(result.message);
    },
  });

  // Load form data when section changes
  useEffect(() => {
    if (sectionData?.data) {
      const values: FormData = {};
      sectionData.data.values.forEach((v) => {
        // Cast unknown to our expected type
        values[v.name] = v.value as string | number | boolean | null;
      });
      setFormData(values);
      setHasChanges(false);
    }
  }, [sectionData]);

  const handleFieldChange = (name: string, value: string | number | boolean | null) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
    setHasChanges(true);
  };

  const handleSave = () => {
    updateMutation.mutate({ section: activeTab, values: formData });
  };

  const handleTestConnection = async (service: string) => {
    setTestingConnection(service);
    setTestResult(null);
    try {
      const result = await settingsApi.testConnection(service);
      setTestResult({ success: result.success, message: result.message });
    } catch (error) {
      setTestResult({ success: false, message: (error as Error).message });
    } finally {
      setTestingConnection(null);
    }
  };

  const toggleSecretVisibility = (fieldName: string) => {
    setShowSecrets((prev) => ({ ...prev, [fieldName]: !prev[fieldName] }));
  };

  const handleDownloadDockerCompose = async () => {
    try {
      const blob = await settingsApi.downloadDockerCompose();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'docker-compose.yml';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download docker-compose.yml:', error);
    }
  };

  const renderField = (field: FieldMetadata) => {
    const value = formData[field.name];
    const showSecret = showSecrets[field.name];

    const baseInputClass = "w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500";

    switch (field.field_type) {
      case 'boolean':
        return (
          <div className="flex items-center">
            <input
              type="checkbox"
              id={field.name}
              checked={value === true || value === 'true'}
              onChange={(e) => handleFieldChange(field.name, e.target.checked)}
              className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
            />
            <label htmlFor={field.name} className="ml-2 text-slate-300">
              {field.label}
            </label>
          </div>
        );

      case 'select':
        return (
          <select
            value={String(value ?? '')}
            onChange={(e) => handleFieldChange(field.name, e.target.value)}
            className={baseInputClass}
          >
            {!field.required && <option value="">-- Select --</option>}
            {field.options?.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        );

      case 'integer':
        return (
          <input
            type="number"
            value={typeof value === 'number' || typeof value === 'string' ? value : ''}
            onChange={(e) => handleFieldChange(field.name, e.target.value ? parseInt(e.target.value, 10) : null)}
            min={field.min_value ?? undefined}
            max={field.max_value ?? undefined}
            className={baseInputClass}
            placeholder={field.description ?? ''}
          />
        );

      case 'float':
        return (
          <input
            type="number"
            step="0.1"
            value={typeof value === 'number' || typeof value === 'string' ? value : ''}
            onChange={(e) => handleFieldChange(field.name, e.target.value ? parseFloat(e.target.value) : null)}
            min={field.min_value ?? undefined}
            max={field.max_value ?? undefined}
            className={baseInputClass}
            placeholder={field.description ?? ''}
          />
        );

      case 'secret':
        return (
          <div className="relative">
            <input
              type={showSecret ? 'text' : 'password'}
              value={String(value ?? '')}
              onChange={(e) => handleFieldChange(field.name, e.target.value)}
              className={`${baseInputClass} pr-10`}
              placeholder={value ? '••••••••' : 'Enter value...'}
            />
            <button
              type="button"
              onClick={() => toggleSecretVisibility(field.name)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
            >
              {showSecret ? (
                <EyeSlashIcon className="w-5 h-5" />
              ) : (
                <EyeIcon className="w-5 h-5" />
              )}
            </button>
          </div>
        );

      default: // string, path, ip_address
        return (
          <input
            type="text"
            value={String(value ?? '')}
            onChange={(e) => handleFieldChange(field.name, e.target.value)}
            className={baseInputClass}
            placeholder={field.description ?? ''}
          />
        );
    }
  };

  if (loadingSections) {
    return <LoadingPage />;
  }

  const sections = settingsData?.sections ?? [];
  const currentSection = sections.find((s) => s.key === activeTab);
  const restartRequired = settingsData?.restart_required ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-white">System Settings</h1>
          <p className="text-slate-400 mt-1">Configure FlowLens application settings</p>
        </div>
        {restartRequired && (
          <Button
            onClick={() => restartMutation.mutate()}
            loading={restartMutation.isPending}
            className="flex items-center gap-2"
          >
            <ArrowPathIcon className="w-4 h-4" />
            Restart Services
          </Button>
        )}
      </div>

      {/* Restart Required Banner */}
      {restartRequired && (
        <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-lg p-4 flex items-center gap-3">
          <ExclamationTriangleIcon className="w-6 h-6 text-yellow-400 flex-shrink-0" />
          <div>
            <p className="text-yellow-400 font-medium">Service restart required</p>
            <p className="text-yellow-400/80 text-sm">
              Some settings have been changed that require a service restart to take effect.
            </p>
          </div>
        </div>
      )}

      {/* Docker Mode Banner */}
      {dockerMode && (
        <div className="bg-blue-500/20 border border-blue-500/50 rounded-lg p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <ArrowDownTrayIcon className="w-6 h-6 text-blue-400 flex-shrink-0" />
            <div>
              <p className="text-blue-400 font-medium">Running in Docker mode</p>
              <p className="text-blue-400/80 text-sm">
                Settings have been applied to this session. Download the updated docker-compose.yml to persist changes.
              </p>
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={handleDownloadDockerCompose}
            className="flex items-center gap-2 whitespace-nowrap"
          >
            <ArrowDownTrayIcon className="w-4 h-4" />
            Download docker-compose.yml
          </Button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-700 pb-2">
        {sections.map((section) => {
          const Icon = ICONS[section.icon] || Cog6ToothIcon;
          return (
            <button
              key={section.key}
              onClick={() => setActiveTab(section.key)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                activeTab === section.key
                  ? 'bg-primary-600 text-white'
                  : 'text-slate-400 hover:bg-slate-700 hover:text-white'
              }`}
            >
              <Icon className="w-4 h-4" />
              {section.name}
            </button>
          );
        })}
      </div>

      {/* Section Content */}
      {currentSection && (
        <Card>
          <div className="p-6">
            {/* Section Header */}
            <div className="flex justify-between items-center mb-6">
              <div>
                <h2 className="text-xl font-semibold text-white">{currentSection.name} Settings</h2>
                <p className="text-slate-400 text-sm mt-1">{currentSection.description}</p>
              </div>
              {currentSection.has_connection_test && (
                <Button
                  variant="secondary"
                  onClick={() => handleTestConnection(activeTab)}
                  loading={testingConnection === activeTab}
                >
                  Test Connection
                </Button>
              )}
            </div>

            {/* Test Result */}
            {testResult && (
              <div
                className={`mb-6 p-4 rounded-lg flex items-center gap-3 ${
                  testResult.success
                    ? 'bg-green-500/20 border border-green-500/50'
                    : 'bg-red-500/20 border border-red-500/50'
                }`}
              >
                {testResult.success ? (
                  <CheckCircleIcon className="w-5 h-5 text-green-400" />
                ) : (
                  <ExclamationTriangleIcon className="w-5 h-5 text-red-400" />
                )}
                <span className={testResult.success ? 'text-green-400' : 'text-red-400'}>
                  {testResult.message}
                </span>
              </div>
            )}

            {/* Loading */}
            {loadingSection ? (
              <div className="text-center py-8 text-slate-400">Loading settings...</div>
            ) : (
              /* Form Fields */
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {currentSection.fields.map((field) => (
                  <div
                    key={field.name}
                    className={field.field_type === 'boolean' ? 'md:col-span-2' : ''}
                  >
                    {field.field_type !== 'boolean' && (
                      <label className="block text-sm font-medium text-slate-300 mb-2">
                        {field.label}
                        {field.required && <span className="text-red-400 ml-1">*</span>}
                        {field.min_value !== null && field.max_value !== null && (
                          <span className="text-slate-500 ml-2">
                            ({field.min_value} - {field.max_value})
                          </span>
                        )}
                      </label>
                    )}
                    {renderField(field)}
                    {field.description && field.field_type !== 'boolean' && (
                      <p className="text-slate-500 text-xs mt-1">{field.description}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Save Button */}
            <div className="mt-8 flex justify-end gap-4">
              {hasChanges && (
                <Button
                  variant="secondary"
                  onClick={() => refetchSection()}
                >
                  Discard Changes
                </Button>
              )}
              <Button
                onClick={handleSave}
                loading={updateMutation.isPending}
                disabled={!hasChanges}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
