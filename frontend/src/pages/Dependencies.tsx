import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import Card from '../components/common/Card';
import Table from '../components/common/Table';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { dependencyApi } from '../services/api';
import {
  formatRelativeTime,
  formatBytes,
  formatPort,
  formatProtocol,
} from '../utils/format';
import type { Dependency } from '../types';

export default function Dependencies() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [isActive, setIsActive] = useState<boolean | undefined>(undefined);

  const { data, isLoading } = useQuery({
    queryKey: ['dependencies', page, isActive],
    queryFn: () =>
      dependencyApi.list({
        page,
        page_size: 20,
        is_active: isActive,
      }),
    placeholderData: (prev) => prev,
  });

  const columns = [
    {
      key: 'source',
      header: 'Source',
      render: (dep: Dependency) => (
        <div>
          <div className="font-medium text-white">
            {dep.source_asset?.name ?? 'Unknown'}
          </div>
          <div className="text-sm text-slate-400 font-mono">
            {dep.source_asset?.ip_address}
          </div>
        </div>
      ),
    },
    {
      key: 'arrow',
      header: '',
      render: () => (
        <div className="text-slate-500">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
          </svg>
        </div>
      ),
      className: 'w-12',
    },
    {
      key: 'target',
      header: 'Target',
      render: (dep: Dependency) => (
        <div>
          <div className="font-medium text-white">
            {dep.target_asset?.name ?? 'Unknown'}
          </div>
          <div className="text-sm text-slate-400 font-mono">
            {dep.target_asset?.ip_address}
          </div>
        </div>
      ),
    },
    {
      key: 'port',
      header: 'Port',
      render: (dep: Dependency) => (
        <span className="font-mono text-slate-300">
          {formatPort(dep.target_port, dep.protocol)}
        </span>
      ),
    },
    {
      key: 'protocol',
      header: 'Protocol',
      render: (dep: Dependency) => (
        <Badge>{formatProtocol(dep.protocol)}</Badge>
      ),
    },
    {
      key: 'traffic',
      header: 'Total Traffic',
      render: (dep: Dependency) => (
        <span className="text-slate-300">{formatBytes(dep.bytes_total)}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (dep: Dependency) => (
        <Badge variant={dep.is_critical ? 'error' : dep.valid_to === null ? 'success' : 'default'}>
          {dep.is_critical ? 'Critical' : dep.valid_to === null ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      key: 'last_seen',
      header: 'Last Seen',
      render: (dep: Dependency) => (
        <span className="text-slate-400">
          {formatRelativeTime(dep.last_seen)}
        </span>
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
          <h1 className="text-2xl font-bold text-white">Dependencies</h1>
          <p className="text-slate-400 mt-1">
            {data?.total ?? 0} dependency relationships discovered
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex items-center gap-4">
          <select
            value={isActive === undefined ? '' : isActive.toString()}
            onChange={(e) => {
              const val = e.target.value;
              setIsActive(val === '' ? undefined : val === 'true');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Status</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>

          {isActive !== undefined && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setIsActive(undefined);
                setPage(1);
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      </Card>

      {/* Dependencies Table */}
      <Card>
        <Table
          columns={columns}
          data={data?.items ?? []}
          keyExtractor={(item) => item.id}
          onRowClick={(dep) => navigate(`/assets/${dep.source_asset_id}`)}
          emptyMessage="No dependencies found"
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
