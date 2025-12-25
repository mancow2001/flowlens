import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Table from '../components/common/Table';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { assetApi } from '../services/api';
import { formatRelativeTime } from '../utils/format';
import type { Asset, AssetType } from '../types';
import clsx from 'clsx';

const ASSET_TYPES: { value: AssetType | ''; label: string }[] = [
  { value: '', label: 'All Types' },
  { value: 'server', label: 'Server' },
  { value: 'database', label: 'Database' },
  { value: 'workstation', label: 'Workstation' },
  { value: 'load_balancer', label: 'Load Balancer' },
  { value: 'firewall', label: 'Firewall' },
  { value: 'router', label: 'Router' },
  { value: 'switch', label: 'Switch' },
  { value: 'storage', label: 'Storage' },
  { value: 'container', label: 'Container' },
  { value: 'virtual_machine', label: 'Virtual Machine' },
  { value: 'cloud_service', label: 'Cloud Service' },
  { value: 'unknown', label: 'Unknown' },
];

export default function Assets() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [assetType, setAssetType] = useState<AssetType | ''>('');
  const [isInternal, setIsInternal] = useState<boolean | undefined>(undefined);

  const { data, isLoading } = useQuery({
    queryKey: ['assets', page, search, assetType, isInternal],
    queryFn: () =>
      assetApi.list({
        page,
        page_size: 20,
        search: search || undefined,
        asset_type: assetType || undefined,
        is_internal: isInternal,
      }),
    placeholderData: (prev) => prev,
  });

  // Get a display character for the asset avatar
  // I = Internal, E = External
  const getAvatarChar = (asset: Asset): string => {
    return asset.is_internal ? 'I' : 'E';
  };

  const columns = [
    {
      key: 'name',
      header: 'Name',
      render: (asset: Asset) => (
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              'w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-medium',
              asset.is_internal ? 'bg-green-600' : 'bg-orange-600'
            )}
          >
            {getAvatarChar(asset)}
          </div>
          <div>
            <div className="font-medium text-white">{asset.name}</div>
            {asset.hostname && (
              <div className="text-sm text-slate-400">{asset.hostname}</div>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      render: (asset: Asset) => (
        <Badge>
          {asset.asset_type?.replace('_', ' ') ?? 'Unknown'}
        </Badge>
      ),
    },
    {
      key: 'ip_address',
      header: 'IP Address',
      render: (asset: Asset) => (
        <span className="font-mono text-slate-300">
          {asset.ip_address || '-'}
        </span>
      ),
    },
    {
      key: 'location',
      header: 'Location',
      render: (asset: Asset) => (
        <div className="flex items-center gap-2">
          <Badge variant={asset.is_internal ? 'success' : 'warning'}>
            {asset.is_internal ? 'Internal' : 'External'}
          </Badge>
          {asset.is_critical && <Badge variant="error">Critical</Badge>}
        </div>
      ),
    },
    {
      key: 'last_seen',
      header: 'Last Seen',
      render: (asset: Asset) => (
        <span className="text-slate-400">
          {formatRelativeTime(asset.last_seen)}
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
          <h1 className="text-2xl font-bold text-white">Assets</h1>
          <p className="text-slate-400 mt-1">
            {data?.total ?? 0} assets discovered
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="flex-1 min-w-[200px] max-w-md">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                placeholder="Search by name, IP, hostname..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>

          {/* Type filter */}
          <select
            value={assetType}
            onChange={(e) => {
              setAssetType(e.target.value as AssetType | '');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {ASSET_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>

          {/* Location filter */}
          <select
            value={isInternal === undefined ? '' : isInternal.toString()}
            onChange={(e) => {
              const val = e.target.value;
              setIsInternal(val === '' ? undefined : val === 'true');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Locations</option>
            <option value="true">Internal</option>
            <option value="false">External</option>
          </select>

          {/* Clear filters */}
          {(search || assetType || isInternal !== undefined) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch('');
                setAssetType('');
                setIsInternal(undefined);
                setPage(1);
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      </Card>

      {/* Assets Table */}
      <Card>
        <Table
          columns={columns}
          data={data?.items ?? []}
          keyExtractor={(item) => item.id}
          onRowClick={(asset) => navigate(`/assets/${asset.id}`)}
          emptyMessage="No assets found"
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
