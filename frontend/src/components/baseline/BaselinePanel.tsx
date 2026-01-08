import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ClockIcon,
  PlusIcon,
  TrashIcon,
  ArrowsRightLeftIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { baselineApi } from '../../services/api';
import { formatDistanceToNow } from '../../utils/date';
import type { ApplicationBaseline, BaselineComparisonResult } from '../../types';
import CreateBaselineModal from './CreateBaselineModal';
import ComparisonResultsPanel from './ComparisonResultsPanel';

interface BaselinePanelProps {
  applicationId: string;
  hopDepth: number;
  onCompare?: (result: BaselineComparisonResult) => void;
}

export default function BaselinePanel({
  applicationId,
  hopDepth,
  onCompare,
}: BaselinePanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedBaseline, setSelectedBaseline] = useState<string | null>(null);
  const [comparisonResult, setComparisonResult] = useState<BaselineComparisonResult | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const queryClient = useQueryClient();

  // Fetch baselines
  const { data: baselines = [], isLoading } = useQuery({
    queryKey: ['baselines', applicationId],
    queryFn: () => baselineApi.list(applicationId),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (baselineId: string) => baselineApi.delete(applicationId, baselineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines', applicationId] });
      if (selectedBaseline) {
        setSelectedBaseline(null);
        setComparisonResult(null);
      }
    },
  });

  // Compare mutation
  const compareMutation = useMutation({
    mutationFn: (baselineId: string) =>
      baselineApi.compareToCurrent(applicationId, baselineId, { hop_depth: hopDepth }),
    onSuccess: (result) => {
      setComparisonResult(result);
      onCompare?.(result);
    },
  });

  const handleCompare = async (baselineId: string) => {
    setSelectedBaseline(baselineId);
    setIsComparing(true);
    try {
      await compareMutation.mutateAsync(baselineId);
    } finally {
      setIsComparing(false);
    }
  };

  const handleDelete = (baseline: ApplicationBaseline) => {
    if (confirm(`Delete baseline "${baseline.name}"? This cannot be undone.`)) {
      deleteMutation.mutate(baseline.id);
    }
  };

  const clearComparison = () => {
    setSelectedBaseline(null);
    setComparisonResult(null);
    onCompare?.(null as unknown as BaselineComparisonResult);
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high':
        return 'text-red-400';
      case 'medium':
        return 'text-amber-400';
      case 'low':
        return 'text-yellow-400';
      default:
        return 'text-green-400';
    }
  };

  const getSeverityIcon = (severity: string) => {
    if (severity === 'none') {
      return <CheckCircleIcon className="h-4 w-4 text-green-400" />;
    }
    return <ExclamationTriangleIcon className={`h-4 w-4 ${getSeverityColor(severity)}`} />;
  };

  return (
    <div className="bg-slate-800 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-700/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <ClockIcon className="h-5 w-5 text-slate-400" />
          <span className="font-medium text-white">Baselines</span>
          <span className="text-sm text-slate-500">({baselines.length})</span>
        </div>
        {isExpanded ? (
          <ChevronUpIcon className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDownIcon className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Create button */}
          <button
            onClick={() => setShowCreateModal(true)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
          >
            <PlusIcon className="h-4 w-4" />
            Create Baseline
          </button>

          {/* Baselines list */}
          {isLoading ? (
            <div className="text-center py-4 text-slate-400 text-sm">Loading...</div>
          ) : baselines.length === 0 ? (
            <div className="text-center py-4 text-slate-400 text-sm">
              No baselines yet. Create one to track changes.
            </div>
          ) : (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {baselines.map((baseline) => (
                <div
                  key={baseline.id}
                  className={`p-3 rounded border transition-colors ${
                    selectedBaseline === baseline.id
                      ? 'border-blue-500 bg-blue-500/10'
                      : 'border-slate-700 bg-slate-900/50 hover:border-slate-600'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h4 className="font-medium text-white text-sm truncate">
                        {baseline.name}
                      </h4>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {formatDistanceToNow(baseline.captured_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleCompare(baseline.id)}
                        disabled={isComparing && selectedBaseline === baseline.id}
                        className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-slate-700 rounded transition-colors disabled:opacity-50"
                        title="Compare to current"
                      >
                        <ArrowsRightLeftIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(baseline)}
                        disabled={deleteMutation.isPending}
                        className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded transition-colors disabled:opacity-50"
                        title="Delete baseline"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                    <span>{baseline.member_count} members</span>
                    <span>{baseline.dependency_count} deps</span>
                    <span>{baseline.entry_point_count} entry pts</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Comparison result summary */}
          {comparisonResult && (
            <div className="mt-4 pt-4 border-t border-slate-700">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {getSeverityIcon(comparisonResult.change_severity)}
                  <span className="text-sm font-medium text-white">
                    Comparison Result
                  </span>
                </div>
                <button
                  onClick={clearComparison}
                  className="text-xs text-slate-400 hover:text-white"
                >
                  Clear
                </button>
              </div>

              <div className={`text-sm ${getSeverityColor(comparisonResult.change_severity)}`}>
                {comparisonResult.total_changes === 0 ? (
                  'No changes detected'
                ) : (
                  `${comparisonResult.total_changes} changes (${comparisonResult.change_severity} severity)`
                )}
              </div>

              {comparisonResult.total_changes > 0 && (
                <ComparisonResultsPanel result={comparisonResult} />
              )}
            </div>
          )}
        </div>
      )}

      {/* Create Modal */}
      <CreateBaselineModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        applicationId={applicationId}
        hopDepth={hopDepth}
      />
    </div>
  );
}
