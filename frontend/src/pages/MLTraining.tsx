import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  SparklesIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  PlayIcon,
  CpuChipIcon,
  ChartBarIcon,
  BeakerIcon,
} from '@heroicons/react/24/outline';
import { mlApi, tasksApi } from '../services/api';
import type { MLAlgorithm, ModelInfo, Task, TaskStatus } from '../types';
import clsx from 'clsx';
import { formatDistanceToNow, format } from 'date-fns';
import { toast } from '../components/common/Toast';
import Card from '../components/common/Card';
import Button from '../components/common/Button';

const ALGORITHMS: { value: MLAlgorithm; label: string; description: string }[] = [
  { value: 'random_forest', label: 'Random Forest', description: 'Balanced accuracy and speed' },
  { value: 'xgboost', label: 'XGBoost', description: 'High accuracy, slower training' },
  { value: 'gradient_boosting', label: 'Gradient Boosting', description: 'Good for imbalanced data' },
];

const statusConfig: Record<TaskStatus, { icon: React.ElementType; color: string; bgColor: string; label: string }> = {
  pending: { icon: ClockIcon, color: 'text-yellow-400', bgColor: 'bg-yellow-900/50', label: 'Pending' },
  running: { icon: ArrowPathIcon, color: 'text-blue-400', bgColor: 'bg-blue-900/50', label: 'Training' },
  completed: { icon: CheckCircleIcon, color: 'text-green-400', bgColor: 'bg-green-900/50', label: 'Completed' },
  failed: { icon: XCircleIcon, color: 'text-red-400', bgColor: 'bg-red-900/50', label: 'Failed' },
  cancelled: { icon: XCircleIcon, color: 'text-slate-400', bgColor: 'bg-slate-700', label: 'Cancelled' },
};

function ProgressBar({ percent, status }: { percent: number; status: TaskStatus }) {
  const colorClass = status === 'failed' ? 'bg-red-500' :
    status === 'completed' ? 'bg-green-500' :
    status === 'cancelled' ? 'bg-slate-500' :
    'bg-blue-500';

  return (
    <div className="w-full bg-slate-700 rounded-full h-3">
      <div
        className={clsx('h-3 rounded-full transition-all duration-300', colorClass)}
        style={{ width: `${Math.min(100, percent)}%` }}
      />
    </div>
  );
}

function ClassDistributionChart({ distribution }: { distribution: Record<string, number> }) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...Object.values(distribution), 1);

  if (entries.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400">
        No training data available
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {entries.map(([assetType, count]) => (
        <div key={assetType} className="flex items-center gap-3">
          <span className="w-28 text-sm text-slate-400 text-right truncate" title={assetType}>
            {assetType}
          </span>
          <div className="flex-1 h-6 bg-slate-700 rounded overflow-hidden">
            <div
              className="h-full bg-primary-600 rounded transition-all duration-300"
              style={{ width: `${(count / maxCount) * 100}%` }}
            />
          </div>
          <span className="w-12 text-sm text-slate-300 text-right">{count}</span>
        </div>
      ))}
    </div>
  );
}

function SummaryCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColor = 'text-primary-400'
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  iconColor?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
        </div>
        <Icon className={clsx('w-8 h-8', iconColor)} />
      </div>
    </Card>
  );
}

export default function MLTraining() {
  const queryClient = useQueryClient();
  const [selectedAlgorithm, setSelectedAlgorithm] = useState<MLAlgorithm>('random_forest');
  const [trainingNotes, setTrainingNotes] = useState('');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  // Fetch ML status
  const { data: mlStatus, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['ml', 'status'],
    queryFn: () => mlApi.getStatus(),
  });

  // Fetch models
  const { data: modelsData, isLoading: isLoadingModels } = useQuery({
    queryKey: ['ml', 'models'],
    queryFn: () => mlApi.listModels(),
  });

  // Fetch training stats
  const { data: trainingStats, isLoading: isLoadingStats } = useQuery({
    queryKey: ['ml', 'training', 'stats'],
    queryFn: () => mlApi.getTrainingStats(),
  });

  // Poll for active training task
  const { data: activeTask } = useQuery({
    queryKey: ['tasks', activeTaskId],
    queryFn: () => tasksApi.get(activeTaskId!),
    enabled: !!activeTaskId,
    refetchInterval: (query) => {
      const data = query.state.data as Task | undefined;
      if (data && (data.status === 'running' || data.status === 'pending')) {
        return 2000; // Poll every 2 seconds while running
      }
      return false;
    },
  });

  // Check for any running ML training tasks on mount
  useEffect(() => {
    const checkRunningTasks = async () => {
      try {
        const { items } = await tasksApi.list({ taskType: 'train_ml_model', status: 'running' });
        if (items.length > 0) {
          setActiveTaskId(items[0].id);
        }
      } catch {
        // Ignore errors
      }
    };
    checkRunningTasks();
  }, []);

  // Handle task completion
  useEffect(() => {
    if (activeTask && (activeTask.status === 'completed' || activeTask.status === 'failed')) {
      queryClient.invalidateQueries({ queryKey: ['ml'] });
      if (activeTask.status === 'completed') {
        toast.success('Training completed', 'ML model has been trained and activated');
      } else if (activeTask.status === 'failed') {
        toast.error('Training failed', activeTask.error_message || 'Unknown error occurred');
      }
    }
  }, [activeTask, queryClient]);

  // Start training mutation
  const trainMutation = useMutation({
    mutationFn: mlApi.startTraining,
    onSuccess: (data) => {
      setActiveTaskId(data.task_id);
      toast.info('Training started', 'ML model training has started');
      setTrainingNotes('');
    },
    onError: (error: Error) => {
      toast.error('Failed to start training', error.message);
    },
  });

  // Activate model mutation
  const activateMutation = useMutation({
    mutationFn: mlApi.activateModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml'] });
      toast.success('Model activated');
    },
    onError: (error: Error) => {
      toast.error('Failed to activate model', error.message);
    },
  });

  // Reset to shipped mutation
  const resetMutation = useMutation({
    mutationFn: mlApi.resetToShipped,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml'] });
      toast.success('Reset to shipped model');
    },
    onError: (error: Error) => {
      toast.error('Failed to reset model', error.message);
    },
  });

  const handleStartTraining = () => {
    trainMutation.mutate({
      algorithm: selectedAlgorithm,
      notes: trainingNotes || undefined,
    });
  };

  const isTraining = activeTask && (activeTask.status === 'running' || activeTask.status === 'pending');
  const canTrain = trainingStats?.meets_minimum_requirements && !isTraining;

  const isLoading = isLoadingStatus || isLoadingModels || isLoadingStats;

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-96">
        <ArrowPathIcon className="w-8 h-8 text-slate-400 animate-spin" />
      </div>
    );
  }

  const activeModel = modelsData?.models.find(m => m.is_active);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <SparklesIcon className="w-8 h-8 text-primary-400" />
        <div>
          <h1 className="text-2xl font-bold text-white">ML Classification Training</h1>
          <p className="text-slate-400">Train and manage ML models for asset classification</p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          title="ML Status"
          value={mlStatus?.ml_enabled ? (mlStatus.ml_available ? 'Active' : 'No Model') : 'Disabled'}
          subtitle={mlStatus?.ml_enabled ? undefined : 'Enable in settings'}
          icon={CpuChipIcon}
          iconColor={mlStatus?.ml_enabled && mlStatus.ml_available ? 'text-green-400' : 'text-slate-500'}
        />
        <SummaryCard
          title="Active Model"
          value={mlStatus?.model_version || 'None'}
          subtitle={activeModel ? `${Math.round(activeModel.accuracy * 100)}% accuracy` : undefined}
          icon={BeakerIcon}
          iconColor="text-blue-400"
        />
        <SummaryCard
          title="Training Samples"
          value={trainingStats?.total_confirmed_assets || 0}
          subtitle={`${trainingStats?.minimum_samples_required || 50} minimum required`}
          icon={ChartBarIcon}
          iconColor="text-purple-400"
        />
        <SummaryCard
          title="Asset Classes"
          value={Object.keys(trainingStats?.class_distribution || {}).length}
          subtitle={trainingStats?.classes_below_minimum.length
            ? `${trainingStats.classes_below_minimum.length} below minimum`
            : 'All classes ready'}
          icon={SparklesIcon}
          iconColor={trainingStats?.meets_minimum_requirements ? 'text-green-400' : 'text-yellow-400'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Training Section */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Train New Model</h2>

          {/* Training Requirements */}
          {!trainingStats?.meets_minimum_requirements && (
            <div className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg">
              <p className="text-sm text-yellow-400">
                Minimum requirements not met for training:
              </p>
              <ul className="mt-2 text-sm text-slate-400 list-disc list-inside">
                <li>Need at least {trainingStats?.minimum_samples_required} confirmed classifications (have {trainingStats?.total_confirmed_assets})</li>
                {(trainingStats?.classes_below_minimum?.length ?? 0) > 0 && (
                  <li>These classes need more samples: {trainingStats?.classes_below_minimum.join(', ')}</li>
                )}
              </ul>
            </div>
          )}

          {/* Training Progress */}
          {isTraining && activeTask && (
            <div className="mb-4 p-4 bg-slate-700/50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <ArrowPathIcon className="w-5 h-5 text-blue-400 animate-spin" />
                  <span className="text-white font-medium">Training in progress...</span>
                </div>
                <span className={clsx(
                  'px-2 py-1 rounded text-xs font-medium',
                  statusConfig[activeTask.status].bgColor,
                  statusConfig[activeTask.status].color
                )}>
                  {statusConfig[activeTask.status].label}
                </span>
              </div>
              <ProgressBar percent={activeTask.progress_percent} status={activeTask.status} />
              <div className="flex justify-between text-xs text-slate-400 mt-2">
                <span>{activeTask.processed_items} / {activeTask.total_items} samples</span>
                <span>{activeTask.progress_percent.toFixed(1)}%</span>
              </div>
            </div>
          )}

          {/* Algorithm Selection */}
          <div className="mb-4">
            <label className="block text-sm text-slate-400 mb-2">Algorithm</label>
            <select
              value={selectedAlgorithm}
              onChange={(e) => setSelectedAlgorithm(e.target.value as MLAlgorithm)}
              disabled={isTraining}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
            >
              {ALGORITHMS.map((algo) => (
                <option key={algo.value} value={algo.value}>
                  {algo.label} - {algo.description}
                </option>
              ))}
            </select>
          </div>

          {/* Notes */}
          <div className="mb-4">
            <label className="block text-sm text-slate-400 mb-2">Notes (optional)</label>
            <input
              type="text"
              value={trainingNotes}
              onChange={(e) => setTrainingNotes(e.target.value)}
              disabled={isTraining}
              placeholder="e.g., Training with Q1 data"
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
            />
          </div>

          {/* Train Button */}
          <Button
            onClick={handleStartTraining}
            disabled={!canTrain || trainMutation.isPending}
            loading={trainMutation.isPending}
            className="w-full"
          >
            <PlayIcon className="w-4 h-4 mr-2" />
            {isTraining ? 'Training in Progress...' : 'Start Training'}
          </Button>
        </Card>

        {/* Class Distribution */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Training Data Distribution</h2>
          <p className="text-sm text-slate-400 mb-4">
            Confirmed asset classifications by type. Each class needs at least {trainingStats?.minimum_per_class_required || 5} samples.
          </p>
          <ClassDistributionChart distribution={trainingStats?.class_distribution || {}} />
        </Card>
      </div>

      {/* Models Table */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Available Models</h2>
          <Button
            variant="secondary"
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending || activeModel?.version === 'shipped'}
            loading={resetMutation.isPending}
          >
            Reset to Shipped Model
          </Button>
        </div>

        {modelsData?.models.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            No models available
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
                  <th className="pb-3 font-medium">Version</th>
                  <th className="pb-3 font-medium">Algorithm</th>
                  <th className="pb-3 font-medium">Type</th>
                  <th className="pb-3 font-medium">Samples</th>
                  <th className="pb-3 font-medium">Accuracy</th>
                  <th className="pb-3 font-medium">Created</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {modelsData?.models.map((model: ModelInfo) => (
                  <tr key={model.id} className="hover:bg-slate-800/50">
                    <td className="py-3">
                      <span className="font-medium text-white">{model.version}</span>
                    </td>
                    <td className="py-3 text-slate-400">{model.algorithm}</td>
                    <td className="py-3">
                      <span className={clsx(
                        'px-2 py-0.5 rounded text-xs font-medium',
                        model.model_type === 'shipped'
                          ? 'bg-blue-900/50 text-blue-400'
                          : 'bg-purple-900/50 text-purple-400'
                      )}>
                        {model.model_type}
                      </span>
                    </td>
                    <td className="py-3 text-slate-400">{model.training_samples}</td>
                    <td className="py-3">
                      <span className={clsx(
                        'font-medium',
                        model.accuracy >= 0.9 ? 'text-green-400' :
                        model.accuracy >= 0.7 ? 'text-yellow-400' : 'text-red-400'
                      )}>
                        {Math.round(model.accuracy * 100)}%
                      </span>
                    </td>
                    <td className="py-3 text-slate-400 text-sm">
                      <span title={format(new Date(model.created_at), 'PPpp')}>
                        {formatDistanceToNow(new Date(model.created_at), { addSuffix: true })}
                      </span>
                    </td>
                    <td className="py-3">
                      {model.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-900/50 text-green-400">
                          <CheckCircleIcon className="w-3 h-3" />
                          Active
                        </span>
                      ) : (
                        <span className="text-slate-500 text-sm">Inactive</span>
                      )}
                    </td>
                    <td className="py-3">
                      {!model.is_active && model.model_type !== 'shipped' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => activateMutation.mutate(model.version)}
                          disabled={activateMutation.isPending}
                        >
                          Activate
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
