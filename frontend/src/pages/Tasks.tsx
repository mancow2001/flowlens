import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  QueueListIcon,
  PlayIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  StopIcon,
  TrashIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { tasksApi } from '../services/api';
import type { TaskSummary, TaskStatus } from '../types';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';

const statusConfig: Record<TaskStatus, { icon: React.ElementType; color: string; bgColor: string; label: string }> = {
  pending: { icon: ClockIcon, color: 'text-yellow-400', bgColor: 'bg-yellow-900/50', label: 'Pending' },
  running: { icon: ArrowPathIcon, color: 'text-blue-400', bgColor: 'bg-blue-900/50', label: 'Running' },
  completed: { icon: CheckCircleIcon, color: 'text-green-400', bgColor: 'bg-green-900/50', label: 'Completed' },
  failed: { icon: XCircleIcon, color: 'text-red-400', bgColor: 'bg-red-900/50', label: 'Failed' },
  cancelled: { icon: StopIcon, color: 'text-slate-400', bgColor: 'bg-slate-700', label: 'Cancelled' },
};

function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium', config.bgColor, config.color)}>
      <Icon className={clsx('w-3.5 h-3.5', status === 'running' && 'animate-spin')} />
      {config.label}
    </span>
  );
}

function ProgressBar({ percent, status }: { percent: number; status: TaskStatus }) {
  const colorClass = status === 'failed' ? 'bg-red-500' :
    status === 'completed' ? 'bg-green-500' :
    status === 'cancelled' ? 'bg-slate-500' :
    'bg-blue-500';

  return (
    <div className="w-full bg-slate-700 rounded-full h-2">
      <div
        className={clsx('h-2 rounded-full transition-all duration-300', colorClass)}
        style={{ width: `${Math.min(100, percent)}%` }}
      />
    </div>
  );
}

function TaskRow({ task, onCancel, onDelete }: {
  task: TaskSummary;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const isRunning = task.status === 'running' || task.status === 'pending';
  const isComplete = task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled';

  return (
    <tr className="border-b border-slate-700 hover:bg-slate-800/50">
      <td className="px-4 py-3">
        <div className="flex flex-col gap-1">
          <span className="font-medium text-white">{task.name}</span>
          <span className="text-xs text-slate-400">
            {formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}
          </span>
        </div>
      </td>
      <td className="px-4 py-3">
        <TaskStatusBadge status={task.status} />
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col gap-1">
          <ProgressBar percent={task.progress_percent} status={task.status} />
          <div className="flex justify-between text-xs text-slate-400">
            <span>{task.processed_items} / {task.total_items}</span>
            <span>{task.progress_percent.toFixed(1)}%</span>
          </div>
        </div>
      </td>
      <td className="px-4 py-3 text-sm">
        <div className="flex flex-col gap-0.5">
          <span className="text-green-400">{task.successful_items} successful</span>
          {task.failed_items > 0 && <span className="text-red-400">{task.failed_items} failed</span>}
          {task.skipped_items > 0 && <span className="text-slate-400">{task.skipped_items} skipped</span>}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {isRunning && (
            <button
              onClick={() => onCancel(task.id)}
              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-900/30 rounded transition-colors"
              title="Cancel task"
            >
              <StopIcon className="w-4 h-4" />
            </button>
          )}
          {isComplete && (
            <button
              onClick={() => onDelete(task.id)}
              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-900/30 rounded transition-colors"
              title="Delete task"
            >
              <TrashIcon className="w-4 h-4" />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function Tasks() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Poll for running tasks
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['tasks', statusFilter],
    queryFn: () => tasksApi.list({ page: 1, page_size: 50, status: statusFilter || undefined }),
    refetchInterval: 3000, // Poll every 3 seconds for progress updates
  });

  const cancelMutation = useMutation({
    mutationFn: tasksApi.cancel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: tasksApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const applyRulesMutation = useMutation({
    mutationFn: () => tasksApi.applyClassificationRules({ force: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  const tasks = data?.items || [];
  const runningCount = tasks.filter(t => t.status === 'running' || t.status === 'pending').length;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <QueueListIcon className="w-8 h-8 text-primary-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">Background Tasks</h1>
            <p className="text-slate-400">
              {runningCount > 0 ? `${runningCount} task${runningCount > 1 ? 's' : ''} running` : 'No tasks running'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Status</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>

          <button
            onClick={() => refetch()}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            title="Refresh"
          >
            <ArrowPathIcon className="w-5 h-5" />
          </button>

          <button
            onClick={() => applyRulesMutation.mutate()}
            disabled={applyRulesMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <PlayIcon className="w-4 h-4" />
            Apply Classification Rules
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <ArrowPathIcon className="w-8 h-8 text-slate-400 animate-spin" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12 bg-slate-800/50 rounded-lg border border-slate-700">
          <QueueListIcon className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No background tasks</p>
          <p className="text-slate-500 text-sm mt-1">
            Tasks will appear here when classification rules are applied
          </p>
        </div>
      ) : (
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-800 text-left text-sm text-slate-400">
                <th className="px-4 py-3 font-medium">Task</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium w-48">Progress</th>
                <th className="px-4 py-3 font-medium">Results</th>
                <th className="px-4 py-3 font-medium w-20">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onCancel={(id) => cancelMutation.mutate(id)}
                  onDelete={(id) => deleteMutation.mutate(id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
