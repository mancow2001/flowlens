import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Table from '../components/common/Table';
import { LoadingPage } from '../components/common/Loading';
import { assetApi, analysisApi, classificationApi } from '../services/api';
import { formatDateTime, formatRelativeTime, formatBytes, formatPort, formatProtocol } from '../utils/format';
import type { Dependency, Asset } from '../types';

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

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<Partial<Asset>>({});

  const { data: asset, isLoading: assetLoading } = useQuery({
    queryKey: ['assets', id],
    queryFn: () => assetApi.get(id!),
    enabled: !!id,
  });

  // Get CIDR classification for this asset
  const { data: cidrClassification } = useQuery({
    queryKey: ['classification', asset?.ip_address],
    queryFn: () => classificationApi.classifyIp(asset!.ip_address),
    enabled: !!asset?.ip_address,
  });

  const updateMutation = useMutation({
    mutationFn: (updates: Partial<Asset>) => assetApi.update(id!, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assets', id] });
      setIsEditing(false);
      setEditForm({});
    },
  });

  const handleStartEdit = () => {
    if (asset) {
      setEditForm({
        name: asset.name,
        hostname: asset.hostname,
        asset_type: asset.asset_type,
        owner: asset.owner,
        team: asset.team,
        description: asset.description,
        is_critical: asset.is_critical,
      });
      setIsEditing(true);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditForm({});
  };

  const handleSaveEdit = () => {
    updateMutation.mutate(editForm);
  };

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
            {isEditing ? (
              <input
                type="text"
                value={editForm.name || ''}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                className="text-2xl font-bold bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            ) : (
              <h1 className="text-2xl font-bold text-white">{asset.name}</h1>
            )}
            <div className="flex items-center gap-2 mt-1">
              {isEditing ? (
                <select
                  value={editForm.asset_type || ''}
                  onChange={(e) => setEditForm({ ...editForm, asset_type: e.target.value as Asset['asset_type'] })}
                  className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {ASSET_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              ) : (
                <Badge>{asset.asset_type?.replace('_', ' ') ?? 'Unknown'}</Badge>
              )}
              {isEditing ? (
                <label className="flex items-center gap-1 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={editForm.is_critical || false}
                    onChange={(e) => setEditForm({ ...editForm, is_critical: e.target.checked })}
                    className="rounded border-slate-600 bg-slate-700 text-primary-500"
                  />
                  Critical
                </label>
              ) : (
                asset.is_critical && <Badge variant="error">Critical</Badge>
              )}
              {!asset.is_internal && <Badge variant="warning">External</Badge>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isEditing ? (
            <>
              <Button variant="ghost" onClick={handleCancelEdit}>
                <XMarkIcon className="w-4 h-4 mr-1" />
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSaveEdit}
                disabled={updateMutation.isPending}
              >
                <CheckIcon className="w-4 h-4 mr-1" />
                {updateMutation.isPending ? 'Saving...' : 'Save'}
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={handleStartEdit}>
                <PencilIcon className="w-4 h-4 mr-1" />
                Edit
              </Button>
              <Button variant="secondary" onClick={() => navigate('/topology')}>
                View in Topology
              </Button>
              <Button
                variant="primary"
                onClick={() => document.getElementById('blast-radius')?.scrollIntoView({ behavior: 'smooth' })}
              >
                Run Impact Analysis
              </Button>
            </>
          )}
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

        {/* Ownership & Classification */}
        <Card title="Ownership & Classification">
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-slate-400">Owner</dt>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.owner || ''}
                  onChange={(e) => setEditForm({ ...editForm, owner: e.target.value })}
                  placeholder="e.g., john.doe@example.com"
                  className="w-full mt-1 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              ) : (
                <dd className="text-white">{asset.owner || '-'}</dd>
              )}
            </div>
            <div>
              <dt className="text-sm text-slate-400">Team</dt>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.team || ''}
                  onChange={(e) => setEditForm({ ...editForm, team: e.target.value })}
                  placeholder="e.g., Platform Team"
                  className="w-full mt-1 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              ) : (
                <dd className="text-white">{asset.team || '-'}</dd>
              )}
            </div>
            <div>
              <dt className="text-sm text-slate-400">Description</dt>
              {isEditing ? (
                <textarea
                  value={editForm.description || ''}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  placeholder="Asset description..."
                  rows={2}
                  className="w-full mt-1 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              ) : (
                <dd className="text-white">{asset.description || '-'}</dd>
              )}
            </div>
            {/* CIDR Classification */}
            {cidrClassification?.matched && (
              <div className="pt-3 mt-3 border-t border-slate-700">
                <dt className="text-sm text-slate-400 mb-2">
                  CIDR Classification
                  <span className="ml-2 text-xs text-slate-500">
                    (from rule: {cidrClassification.rule_name})
                  </span>
                </dt>
                <div className="flex flex-wrap gap-2">
                  {cidrClassification.environment && (
                    <Badge>Env: {cidrClassification.environment}</Badge>
                  )}
                  {cidrClassification.datacenter && (
                    <Badge>DC: {cidrClassification.datacenter}</Badge>
                  )}
                  {cidrClassification.location && (
                    <Badge>Loc: {cidrClassification.location}</Badge>
                  )}
                </div>
              </div>
            )}
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
