import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Card from '../components/common/Card';
import Table from '../components/common/Table';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import AlertDetailSlideOver from '../components/alerts/AlertDetailSlideOver';
import { alertApi } from '../services/api';
import { formatRelativeTime } from '../utils/format';
import type { Alert, AlertSeverity } from '../types';

const SEVERITY_OPTIONS: { value: AlertSeverity | ''; label: string }[] = [
  { value: '', label: 'All Severities' },
  { value: 'critical', label: 'Critical' },
  { value: 'error', label: 'Error' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
];

export default function Alerts() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState<AlertSeverity | ''>('');
  const [isAcknowledged, setIsAcknowledged] = useState<boolean | undefined>(
    undefined
  );
  const [isResolved, setIsResolved] = useState<boolean | undefined>(undefined);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [isSlideOverOpen, setIsSlideOverOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['alerts', page, severity, isAcknowledged, isResolved],
    queryFn: () =>
      alertApi.list({
        page,
        page_size: 20,
        severity: severity || undefined,
        is_acknowledged: isAcknowledged,
        is_resolved: isResolved,
      }),
    placeholderData: (prev) => prev,
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) => alertApi.acknowledge(id, 'admin'),
    onSuccess: (updatedAlert) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      // Update selected alert if it's the one we just acknowledged
      if (selectedAlert?.id === updatedAlert.id) {
        setSelectedAlert(updatedAlert);
      }
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (id: string) => alertApi.resolve(id, 'admin'),
    onSuccess: (updatedAlert) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      // Update selected alert if it's the one we just resolved
      if (selectedAlert?.id === updatedAlert.id) {
        setSelectedAlert(updatedAlert);
      }
    },
  });

  const bulkAcknowledgeMutation = useMutation({
    mutationFn: (ids: string[]) => alertApi.bulkAcknowledge(ids, 'admin'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      setSelectedIds(new Set());
    },
  });

  const bulkResolveMutation = useMutation({
    mutationFn: (ids: string[]) => alertApi.bulkResolve(ids, 'admin'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      setSelectedIds(new Set());
    },
  });

  const bulkAcknowledgeFilteredMutation = useMutation({
    mutationFn: () =>
      alertApi.bulkAcknowledgeFiltered('admin', {
        severity: severity || undefined,
        is_resolved: isResolved,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });

  const bulkResolveFilteredMutation = useMutation({
    mutationFn: () =>
      alertApi.bulkResolveFiltered('admin', undefined, {
        severity: severity || undefined,
        is_acknowledged: isAcknowledged,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
    },
  });

  const toggleSelect = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedIds(newSet);
  };

  const selectAll = () => {
    if (selectedIds.size === (data?.items.length ?? 0)) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data?.items.map((a) => a.id) ?? []));
    }
  };

  const handleRowClick = (alert: Alert) => {
    setSelectedAlert(alert);
    setIsSlideOverOpen(true);
  };

  const handleCloseSlideOver = () => {
    setIsSlideOverOpen(false);
    // Keep selectedAlert for transition animation
    setTimeout(() => setSelectedAlert(null), 300);
  };

  const columns = [
    {
      key: 'select',
      header: (
        <input
          type="checkbox"
          checked={
            selectedIds.size > 0 &&
            selectedIds.size === (data?.items.length ?? 0)
          }
          onChange={selectAll}
          className="rounded border-slate-600 bg-slate-700 text-primary-600 focus:ring-primary-500"
        />
      ),
      render: (alert: Alert) => (
        <input
          type="checkbox"
          checked={selectedIds.has(alert.id)}
          onChange={() => toggleSelect(alert.id)}
          onClick={(e) => e.stopPropagation()}
          className="rounded border-slate-600 bg-slate-700 text-primary-600 focus:ring-primary-500"
        />
      ),
      className: 'w-10',
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (alert: Alert) => (
        <Badge
          variant={
            alert.severity === 'critical' || alert.severity === 'error'
              ? 'error'
              : alert.severity === 'warning'
              ? 'warning'
              : 'info'
          }
        >
          {alert.severity}
        </Badge>
      ),
      className: 'w-24',
    },
    {
      key: 'title',
      header: 'Alert',
      render: (alert: Alert) => (
        <div>
          <div className="font-medium text-white">{alert.title}</div>
          <div className="text-sm text-slate-400 truncate max-w-md">
            {alert.message}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (alert: Alert) => (
        <div className="flex items-center gap-2">
          {alert.is_resolved ? (
            <Badge variant="success">Resolved</Badge>
          ) : alert.is_acknowledged ? (
            <Badge variant="warning">Acknowledged</Badge>
          ) : (
            <Badge variant="error">Open</Badge>
          )}
        </div>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (alert: Alert) => (
        <span className="text-slate-400">
          {formatRelativeTime(alert.created_at)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (alert: Alert) => (
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {!alert.is_acknowledged && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => acknowledgeMutation.mutate(alert.id)}
              disabled={acknowledgeMutation.isPending}
            >
              Ack
            </Button>
          )}
          {!alert.is_resolved && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => resolveMutation.mutate(alert.id)}
              disabled={resolveMutation.isPending}
            >
              Resolve
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

  // Calculate counts for bulk action buttons
  const unacknowledgedCount = data?.summary?.unacknowledged ?? 0;
  const unresolvedCount = data?.summary?.unresolved ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Alerts</h1>
          <p className="text-slate-400 mt-1">{data?.total ?? 0} total alerts</p>
        </div>
      </div>

      {/* Summary Cards */}
      {data?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {data.summary.total}
            </div>
            <div className="text-sm text-slate-400">Total</div>
          </div>
          <div className="p-4 bg-red-600/20 border border-red-600/30 rounded-lg text-center">
            <div className="text-2xl font-bold text-red-500">
              {data.summary.critical}
            </div>
            <div className="text-sm text-slate-400">Critical</div>
          </div>
          <div className="p-4 bg-orange-500/20 border border-orange-500/30 rounded-lg text-center">
            <div className="text-2xl font-bold text-orange-500">
              {data.summary.error}
            </div>
            <div className="text-sm text-slate-400">Error</div>
          </div>
          <div className="p-4 bg-yellow-500/20 border border-yellow-500/30 rounded-lg text-center">
            <div className="text-2xl font-bold text-yellow-500">
              {data.summary.warning}
            </div>
            <div className="text-sm text-slate-400">Warning</div>
          </div>
          <div className="p-4 bg-blue-500/20 border border-blue-500/30 rounded-lg text-center">
            <div className="text-2xl font-bold text-blue-500">
              {data.summary.info}
            </div>
            <div className="text-sm text-slate-400">Info</div>
          </div>
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {data.summary.unacknowledged}
            </div>
            <div className="text-sm text-slate-400">Unack'd</div>
          </div>
          <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg text-center">
            <div className="text-2xl font-bold text-white">
              {data.summary.unresolved}
            </div>
            <div className="text-sm text-slate-400">Unresolved</div>
          </div>
        </div>
      )}

      {/* Filters and Bulk Actions */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value as AlertSeverity | '');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <select
            value={isAcknowledged === undefined ? '' : isAcknowledged.toString()}
            onChange={(e) => {
              const val = e.target.value;
              setIsAcknowledged(val === '' ? undefined : val === 'true');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Acknowledgment</option>
            <option value="true">Acknowledged</option>
            <option value="false">Not Acknowledged</option>
          </select>

          <select
            value={isResolved === undefined ? '' : isResolved.toString()}
            onChange={(e) => {
              const val = e.target.value;
              setIsResolved(val === '' ? undefined : val === 'true');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Resolution</option>
            <option value="true">Resolved</option>
            <option value="false">Unresolved</option>
          </select>

          {(severity || isAcknowledged !== undefined || isResolved !== undefined) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSeverity('');
                setIsAcknowledged(undefined);
                setIsResolved(undefined);
                setPage(1);
              }}
            >
              Clear Filters
            </Button>
          )}

          {/* Selected items bulk actions */}
          {selectedIds.size > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-sm text-slate-400">
                {selectedIds.size} selected
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  bulkAcknowledgeMutation.mutate(Array.from(selectedIds))
                }
                disabled={bulkAcknowledgeMutation.isPending}
              >
                Acknowledge Selected
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  bulkResolveMutation.mutate(Array.from(selectedIds))
                }
                disabled={bulkResolveMutation.isPending}
              >
                Resolve Selected
              </Button>
            </div>
          )}
        </div>

        {/* Bulk All Actions */}
        {(unacknowledgedCount > 0 || unresolvedCount > 0) && selectedIds.size === 0 && (
          <div className="mt-4 pt-4 border-t border-slate-700 flex items-center gap-4">
            <span className="text-sm text-slate-400">Bulk actions:</span>
            {unacknowledgedCount > 0 && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => bulkAcknowledgeFilteredMutation.mutate()}
                disabled={bulkAcknowledgeFilteredMutation.isPending}
              >
                {bulkAcknowledgeFilteredMutation.isPending
                  ? 'Acknowledging...'
                  : `Acknowledge All (${unacknowledgedCount})`}
              </Button>
            )}
            {unresolvedCount > 0 && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => bulkResolveFilteredMutation.mutate()}
                disabled={bulkResolveFilteredMutation.isPending}
              >
                {bulkResolveFilteredMutation.isPending
                  ? 'Resolving...'
                  : `Resolve All (${unresolvedCount})`}
              </Button>
            )}
          </div>
        )}
      </Card>

      {/* Alerts Table */}
      <Card>
        <Table
          columns={columns}
          data={data?.items ?? []}
          keyExtractor={(item) => item.id}
          emptyMessage="No alerts found"
          onRowClick={handleRowClick}
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

      {/* Alert Detail Slide-over */}
      <AlertDetailSlideOver
        alert={selectedAlert}
        isOpen={isSlideOverOpen}
        onClose={handleCloseSlideOver}
        onAcknowledge={(id) => acknowledgeMutation.mutate(id)}
        onResolve={(id) => resolveMutation.mutate(id)}
        isAcknowledging={acknowledgeMutation.isPending}
        isResolving={resolveMutation.isPending}
      />
    </div>
  );
}
