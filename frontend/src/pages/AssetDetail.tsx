import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  ArrowUpIcon,
  ArrowDownIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Table from '../components/common/Table';
import { LoadingPage } from '../components/common/Loading';
import { assetApi, analysisApi } from '../services/api';
import { formatDateTime, formatRelativeTime, formatBytes, formatPort, formatProtocol } from '../utils/format';
import type { Dependency } from '../types';

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: asset, isLoading: assetLoading } = useQuery({
    queryKey: ['assets', id],
    queryFn: () => assetApi.get(id!),
    enabled: !!id,
  });

  const { data: dependencies } = useQuery({
    queryKey: ['assets', id, 'dependencies'],
    queryFn: () => assetApi.getDependencies(id!, 'both'),
    enabled: !!id,
  });

  const { data: blastRadius } = useQuery({
    queryKey: ['analysis', 'blast-radius', id],
    queryFn: () => analysisApi.getBlastRadius(id!, 3),
    enabled: !!id,
  });

  if (assetLoading) {
    return <LoadingPage />;
  }

  if (!asset) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-slate-400">Asset not found</p>
      </div>
    );
  }

  const upstreamDeps = dependencies?.filter(
    (d) => d.target_asset_id === asset.id
  ) ?? [];
  const downstreamDeps = dependencies?.filter(
    (d) => d.source_asset_id === asset.id
  ) ?? [];

  const depColumns = [
    {
      key: 'asset',
      header: 'Connected Asset',
      render: (dep: Dependency) => {
        const connectedAsset =
          dep.source_asset_id === asset.id
            ? dep.target_asset
            : dep.source_asset;
        return (
          <div>
            <div className="font-medium text-white">
              {connectedAsset?.name ?? 'Unknown'}
            </div>
            <div className="text-sm text-slate-400">
              {connectedAsset?.ip_address}
            </div>
          </div>
        );
      },
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
      header: 'Traffic',
      render: (dep: Dependency) => (
        <span className="text-slate-300">{formatBytes(dep.bytes_total)}</span>
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/assets')}>
          <ArrowLeftIcon className="w-4 h-4 mr-2" />
          Back
        </Button>
      </div>

      {/* Asset Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-xl bg-primary-600 flex items-center justify-center text-white text-2xl font-bold">
            {asset.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">{asset.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <Badge>{asset.asset_type?.replace('_', ' ') ?? 'Unknown'}</Badge>
              {asset.is_critical && <Badge variant="error">Critical</Badge>}
              {!asset.is_internal && <Badge variant="warning">External</Badge>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => navigate('/topology')}>
            View in Topology
          </Button>
          <Button
            variant="primary"
            onClick={() => document.getElementById('blast-radius')?.scrollIntoView({ behavior: 'smooth' })}
          >
            Run Impact Analysis
          </Button>
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Basic Info */}
        <Card title="Basic Information">
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-slate-400">IP Address</dt>
              <dd className="font-mono text-white">
                {asset.ip_address || '-'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Hostname</dt>
              <dd className="text-white">{asset.hostname || '-'}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">FQDN</dt>
              <dd className="text-white">{asset.fqdn || '-'}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">MAC Address</dt>
              <dd className="font-mono text-white">
                {asset.mac_address || '-'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Environment</dt>
              <dd className="text-white">{asset.environment || '-'}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Datacenter</dt>
              <dd className="text-white">{asset.datacenter || '-'}</dd>
            </div>
          </dl>
        </Card>

        {/* Timestamps */}
        <Card title="Activity">
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-slate-400">First Seen</dt>
              <dd className="text-white">
                {formatDateTime(asset.first_seen)}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Last Seen</dt>
              <dd className="text-white">{formatDateTime(asset.last_seen)}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Created</dt>
              <dd className="text-white">{formatDateTime(asset.created_at)}</dd>
            </div>
            <div>
              <dt className="text-sm text-slate-400">Updated</dt>
              <dd className="text-white">{formatDateTime(asset.updated_at)}</dd>
            </div>
          </dl>
        </Card>

        {/* Blast Radius */}
        <div id="blast-radius">
        <Card title="Blast Radius">
          {blastRadius ? (
            <div className="space-y-3">
              <div className="text-center p-4 bg-slate-700/50 rounded-lg">
                <div className="text-3xl font-bold text-white">
                  {blastRadius.total_affected}
                </div>
                <div className="text-sm text-slate-400">
                  Potentially affected assets
                </div>
              </div>
              {blastRadius.by_depth && Object.keys(blastRadius.by_depth).length > 0 && (
                <div className="space-y-2">
                  {Object.entries(blastRadius.by_depth).map(([depth, count]) => (
                    <div key={depth} className="flex justify-between">
                      <span className="text-slate-400">Depth {depth}</span>
                      <span className="text-white">{count} assets</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="text-slate-400 text-center py-4">
              No blast radius data
            </div>
          )}
        </Card>
        </div>
      </div>

      {/* Services */}
      {asset.services.length > 0 && (
        <Card title="Services">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {asset.services.map((service) => (
              <div
                key={service.id}
                className="p-3 bg-slate-700/50 rounded-lg text-center"
              >
                <div className="font-medium text-white">{service.name || 'Unknown'}</div>
                <div className="text-sm text-slate-400">
                  {service.port}/{service.protocol}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Upstream Dependencies */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <ArrowUpIcon className="w-5 h-5 text-green-500" />
            Upstream Dependencies ({upstreamDeps.length})
          </div>
        }
      >
        <Table
          columns={depColumns}
          data={upstreamDeps}
          keyExtractor={(d) => d.id}
          onRowClick={(dep) =>
            navigate(`/assets/${dep.source_asset_id}`)
          }
          emptyMessage="No upstream dependencies"
        />
      </Card>

      {/* Downstream Dependencies */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <ArrowDownIcon className="w-5 h-5 text-blue-500" />
            Downstream Dependencies ({downstreamDeps.length})
          </div>
        }
      >
        <Table
          columns={depColumns}
          data={downstreamDeps}
          keyExtractor={(d) => d.id}
          onRowClick={(dep) =>
            navigate(`/assets/${dep.target_asset_id}`)
          }
          emptyMessage="No downstream dependencies"
        />
      </Card>

      {/* Tags and Metadata */}
      {((asset.tags && Object.keys(asset.tags).length > 0) ||
        (asset.metadata && Object.keys(asset.metadata).length > 0)) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {asset.tags && Object.keys(asset.tags).length > 0 && (
            <Card title="Tags">
              <div className="flex flex-wrap gap-2">
                {Object.entries(asset.tags).map(([key, value]) => (
                  <Badge key={key}>
                    {key}: {value}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          {asset.metadata && Object.keys(asset.metadata).length > 0 && (
            <Card title="Metadata">
              <pre className="text-sm text-slate-300 overflow-x-auto">
                {JSON.stringify(asset.metadata, null, 2)}
              </pre>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
