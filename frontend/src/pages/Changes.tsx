import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Card from '../components/common/Card';
import Table from '../components/common/Table';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { changeApi } from '../services/api';
import { formatRelativeTime } from '../utils/format';
import type { ChangeEvent } from '../types';

export default function Changes() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [changeType, setChangeType] = useState<string>('');
  const [isProcessed, setIsProcessed] = useState<boolean | undefined>(
    undefined
  );

  const { data, isLoading } = useQuery({
    queryKey: ['changes', page, changeType, isProcessed],
    queryFn: () =>
      changeApi.list({
        page,
        page_size: 20,
        change_type: changeType || undefined,
        is_processed: isProcessed,
      }),
    placeholderData: (prev) => prev,
  });

  const { data: changeTypes } = useQuery({
    queryKey: ['changes', 'types'],
    queryFn: changeApi.getTypes,
  });

  const markProcessedMutation = useMutation({
    mutationFn: changeApi.markProcessed,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['changes'] });
    },
  });

  const getChangeTypeColor = (type: string): 'default' | 'success' | 'warning' | 'error' | 'info' => {
    if (type.includes('new') || type.includes('created')) return 'success';
    if (type.includes('removed') || type.includes('deleted')) return 'error';
    if (type.includes('update') || type.includes('changed')) return 'warning';
    return 'info';
  };

  const columns = [
    {
      key: 'type',
      header: 'Type',
      render: (change: ChangeEvent) => (
        <Badge variant={getChangeTypeColor(change.change_type)}>
          {change.change_type}
        </Badge>
      ),
    },
    {
      key: 'summary',
      header: 'Summary',
      render: (change: ChangeEvent) => (
        <div>
          <div className="font-medium text-white">{change.summary}</div>
          {change.description && (
            <div className="text-sm text-slate-400 truncate max-w-md">
              {change.description}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'impact',
      header: 'Impact',
      render: (change: ChangeEvent) => (
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full ${
              change.impact_score >= 70
                ? 'bg-red-500'
                : change.impact_score >= 40
                ? 'bg-yellow-500'
                : 'bg-green-500'
            }`}
          />
          <span className="text-slate-300">{change.impact_score}</span>
          {change.affected_assets_count > 0 && (
            <span className="text-slate-400 text-sm">
              ({change.affected_assets_count} assets)
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'alerts',
      header: 'Alerts',
      render: (change: ChangeEvent) => (
        <span className="text-slate-300">{change.alerts_count}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (change: ChangeEvent) => (
        <Badge variant={change.is_processed ? 'success' : 'warning'}>
          {change.is_processed ? 'Processed' : 'Pending'}
        </Badge>
      ),
    },
    {
      key: 'detected_at',
      header: 'Detected',
      render: (change: ChangeEvent) => (
        <span className="text-slate-400">
          {formatRelativeTime(change.detected_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (change: ChangeEvent) => (
        <div onClick={(e) => e.stopPropagation()}>
          {!change.is_processed && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => markProcessedMutation.mutate(change.id)}
              disabled={markProcessedMutation.isPending}
            >
              Mark Processed
            </Button>
          )}
        </div>
      ),
    },
  ];

  if (isLoading) {
    return <LoadingPage />;
  }

  const totalPages = Math.ceil((data?.total ?? 0) / 20);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Change Events</h1>
          <p className="text-slate-400 mt-1">
            {data?.total ?? 0} change events detected
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      {data?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {data.summary.total}
            </div>
            <div className="text-sm text-slate-400">Total</div>
          </div>
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-yellow-500">
              {data.summary.unprocessed}
            </div>
            <div className="text-sm text-slate-400">Unprocessed</div>
          </div>
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {data.summary.last_24h}
            </div>
            <div className="text-sm text-slate-400">Last 24h</div>
          </div>
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {data.summary.last_7d}
            </div>
            <div className="text-sm text-slate-400">Last 7 Days</div>
          </div>
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {Object.keys(data.summary.by_type).length}
            </div>
            <div className="text-sm text-slate-400">Change Types</div>
          </div>
        </div>
      )}

      {/* Change Types Breakdown */}
      {changeTypes && changeTypes.length > 0 && (
        <Card title="Changes by Type">
          <div className="flex flex-wrap gap-3">
            {changeTypes.map((ct) => (
              <button
                key={ct.change_type}
                onClick={() => {
                  setChangeType(
                    changeType === ct.change_type ? '' : ct.change_type
                  );
                  setPage(1);
                }}
                className={`px-4 py-2 rounded-lg border transition-colors ${
                  changeType === ct.change_type
                    ? 'bg-primary-600 border-primary-500 text-white'
                    : 'bg-slate-700/50 border-slate-600 text-slate-300 hover:bg-slate-700'
                }`}
              >
                <span className="font-medium">{ct.change_type}</span>
                <span className="ml-2 text-slate-400">({ct.count})</span>
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <div className="flex items-center gap-4">
          <select
            value={isProcessed === undefined ? '' : isProcessed.toString()}
            onChange={(e) => {
              const val = e.target.value;
              setIsProcessed(val === '' ? undefined : val === 'true');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Status</option>
            <option value="true">Processed</option>
            <option value="false">Pending</option>
          </select>

          {(changeType || isProcessed !== undefined) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setChangeType('');
                setIsProcessed(undefined);
                setPage(1);
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      </Card>

      {/* Changes Table */}
      <Card>
        <Table
          columns={columns}
          data={data?.items ?? []}
          keyExtractor={(item) => item.id}
          emptyMessage="No change events found"
        />

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-700">
            <div className="text-sm text-slate-400">
              Page {page} of {totalPages}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
