import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { analysisApi, assetApi } from '../services/api';
import type { BlastRadius, AffectedAsset } from '../types';
import Card from '../components/common/Card';
import Loading from '../components/common/Loading';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';

type TabType = 'spof' | 'blast-radius' | 'path-finder';

export default function Analysis() {
  const [activeTab, setActiveTab] = useState<TabType>('spof');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dependency Analysis</h1>
        <p className="text-slate-400 mt-1">
          Analyze dependencies, find critical paths, and assess impact
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-700">
        <nav className="flex gap-4" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('spof')}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'spof'
                ? 'border-primary-500 text-primary-400'
                : 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-300'
            }`}
          >
            Single Points of Failure
          </button>
          <button
            onClick={() => setActiveTab('blast-radius')}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'blast-radius'
                ? 'border-primary-500 text-primary-400'
                : 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-300'
            }`}
          >
            Blast Radius
          </button>
          <button
            onClick={() => setActiveTab('path-finder')}
            className={`py-3 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'path-finder'
                ? 'border-primary-500 text-primary-400'
                : 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-300'
            }`}
          >
            Path Finder
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'spof' && <SPOFAnalysis />}
      {activeTab === 'blast-radius' && <BlastRadiusAnalysis />}
      {activeTab === 'path-finder' && <PathFinder />}
    </div>
  );
}

function SPOFAnalysis() {
  const { data: spofAssets, isLoading, error, refetch } = useQuery({
    queryKey: ['spof-analysis'],
    queryFn: () => analysisApi.getSPOF(),
  });

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <Card>
        <div className="text-center py-8">
          <ExclamationTriangleIcon className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-slate-400">Failed to load SPOF analysis</p>
          <Button onClick={() => refetch()} className="mt-4">
            Retry
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-start gap-4 p-4">
          <div className="p-3 bg-yellow-500/10 rounded-lg">
            <ExclamationTriangleIcon className="w-6 h-6 text-yellow-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">What is a Single Point of Failure?</h3>
            <p className="text-slate-400 text-sm mt-1">
              A Single Point of Failure (SPOF) is an asset that, if it fails, would cause a
              significant number of other assets or services to become unavailable. These are
              typically high-value targets for redundancy planning.
            </p>
          </div>
        </div>
      </Card>

      {spofAssets && spofAssets.length > 0 ? (
        <Card>
          <div className="p-4 border-b border-slate-700">
            <h3 className="font-semibold text-white">
              Detected SPOFs ({spofAssets.length})
            </h3>
          </div>
          <div className="divide-y divide-slate-700">
            {spofAssets.map((asset) => (
              <div key={asset.id} className="p-4 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{asset.name}</span>
                    {asset.is_critical && (
                      <Badge variant="error" size="sm">Critical</Badge>
                    )}
                  </div>
                  <p className="text-sm text-slate-400 mt-1">
                    {asset.ip_address} - {asset.asset_type}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-slate-400">
                    {asset.connections_in + asset.connections_out} connections
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <Card>
          <div className="text-center py-12">
            <p className="text-slate-400">No single points of failure detected.</p>
            <p className="text-slate-500 text-sm mt-2">
              This is a good sign! Your infrastructure appears to have adequate redundancy.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

function BlastRadiusAnalysis() {
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Search for assets
  const { data: searchResults } = useQuery({
    queryKey: ['asset-search', searchQuery],
    queryFn: () => assetApi.list({ search: searchQuery, page_size: 10 }),
    enabled: searchQuery.length >= 2,
  });

  // Get blast radius for selected asset
  const { data: blastRadius, isLoading, error } = useQuery({
    queryKey: ['blast-radius', selectedAssetId],
    queryFn: () => analysisApi.getBlastRadius(selectedAssetId!, 5),
    enabled: !!selectedAssetId,
  });

  return (
    <div className="space-y-4">
      <Card>
        <div className="p-4">
          <h3 className="font-semibold text-white mb-4">Select an Asset</h3>
          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name, IP, or hostname..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {searchResults?.items && searchResults.items.length > 0 && (
            <div className="mt-2 border border-slate-600 rounded-lg overflow-hidden">
              {searchResults.items.map((asset) => (
                <button
                  key={asset.id}
                  onClick={() => {
                    setSelectedAssetId(asset.id);
                    setSearchQuery('');
                  }}
                  className="w-full px-4 py-2 text-left hover:bg-slate-700 transition-colors border-b border-slate-600 last:border-b-0"
                >
                  <p className="text-white">{asset.name}</p>
                  <p className="text-sm text-slate-400">{asset.ip_address}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      </Card>

      {selectedAssetId && (
        <Card>
          {isLoading ? (
            <div className="p-8">
              <Loading />
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-400">
              Failed to load blast radius analysis
            </div>
          ) : blastRadius ? (
            <BlastRadiusResult blastRadius={blastRadius} />
          ) : null}
        </Card>
      )}
    </div>
  );
}

function BlastRadiusResult({ blastRadius }: { blastRadius: BlastRadius }) {
  return (
    <div>
      <div className="p-4 border-b border-slate-700">
        <h3 className="font-semibold text-white">
          Blast Radius: {blastRadius.center_asset_name}
        </h3>
        <p className="text-sm text-slate-400 mt-1">
          {blastRadius.total_affected} assets would be affected if this asset fails
        </p>
      </div>

      {/* Depth breakdown */}
      <div className="p-4 border-b border-slate-700">
        <h4 className="text-sm font-medium text-slate-300 mb-3">Impact by Distance</h4>
        <div className="grid grid-cols-5 gap-2">
          {Object.entries(blastRadius.by_depth).map(([depth, count]) => (
            <div key={depth} className="text-center p-2 bg-slate-700 rounded-lg">
              <p className="text-lg font-semibold text-white">{count}</p>
              <p className="text-xs text-slate-400">Hop {depth}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Affected assets list */}
      <div className="divide-y divide-slate-700">
        {blastRadius.affected_assets.map((asset: AffectedAsset) => (
          <div key={asset.id} className="p-4 flex items-center justify-between">
            <div>
              <span className="text-white">{asset.name}</span>
              <p className="text-sm text-slate-400">{asset.type}</p>
            </div>
            <Badge variant={asset.depth === 1 ? 'error' : asset.depth === 2 ? 'warning' : 'info'} size="sm">
              {asset.depth} hop{asset.depth !== 1 ? 's' : ''} away
            </Badge>
          </div>
        ))}
      </div>
    </div>
  );
}

function PathFinder() {
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [targetId, setTargetId] = useState<string | null>(null);
  const [sourceSearch, setSourceSearch] = useState('');
  const [targetSearch, setTargetSearch] = useState('');
  const [activeField, setActiveField] = useState<'source' | 'target' | null>(null);

  // Search for source assets
  const { data: sourceResults } = useQuery({
    queryKey: ['asset-search', 'source', sourceSearch],
    queryFn: () => assetApi.list({ search: sourceSearch, page_size: 5 }),
    enabled: sourceSearch.length >= 2 && activeField === 'source',
  });

  // Search for target assets
  const { data: targetResults } = useQuery({
    queryKey: ['asset-search', 'target', targetSearch],
    queryFn: () => assetApi.list({ search: targetSearch, page_size: 5 }),
    enabled: targetSearch.length >= 2 && activeField === 'target',
  });

  // Find path
  const { data: pathResult, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['path-finder', sourceId, targetId],
    queryFn: () => analysisApi.getPath(sourceId!, targetId!),
    enabled: false,
  });

  const handleFindPath = () => {
    if (sourceId && targetId) {
      refetch();
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="p-4 space-y-4">
          <h3 className="font-semibold text-white">Find Path Between Assets</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Source Asset */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Source Asset
              </label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="Search source..."
                  value={sourceSearch}
                  onChange={(e) => setSourceSearch(e.target.value)}
                  onFocus={() => setActiveField('source')}
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                {sourceResults?.items && sourceResults.items.length > 0 && activeField === 'source' && (
                  <div className="absolute z-10 w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg overflow-hidden shadow-lg">
                    {sourceResults.items.map((asset) => (
                      <button
                        key={asset.id}
                        onClick={() => {
                          setSourceId(asset.id);
                          setSourceSearch(asset.name);
                          setActiveField(null);
                        }}
                        className="w-full px-4 py-2 text-left hover:bg-slate-700 border-b border-slate-600 last:border-b-0"
                      >
                        <p className="text-white">{asset.name}</p>
                        <p className="text-sm text-slate-400">{asset.ip_address}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Target Asset */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Target Asset
              </label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="Search target..."
                  value={targetSearch}
                  onChange={(e) => setTargetSearch(e.target.value)}
                  onFocus={() => setActiveField('target')}
                  className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                {targetResults?.items && targetResults.items.length > 0 && activeField === 'target' && (
                  <div className="absolute z-10 w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg overflow-hidden shadow-lg">
                    {targetResults.items.map((asset) => (
                      <button
                        key={asset.id}
                        onClick={() => {
                          setTargetId(asset.id);
                          setTargetSearch(asset.name);
                          setActiveField(null);
                        }}
                        className="w-full px-4 py-2 text-left hover:bg-slate-700 border-b border-slate-600 last:border-b-0"
                      >
                        <p className="text-white">{asset.name}</p>
                        <p className="text-sm text-slate-400">{asset.ip_address}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          <Button
            onClick={handleFindPath}
            disabled={!sourceId || !targetId || isLoading || isRefetching}
            className="w-full"
          >
            {isLoading || isRefetching ? (
              <>
                <ArrowPathIcon className="w-4 h-4 mr-2 animate-spin" />
                Finding Path...
              </>
            ) : (
              'Find Path'
            )}
          </Button>
        </div>
      </Card>

      {error && (
        <Card>
          <div className="p-6 text-center">
            <p className="text-red-400">No path found between these assets</p>
            <p className="text-slate-500 text-sm mt-2">
              The assets may not be connected, or the path may exceed the maximum depth.
            </p>
          </div>
        </Card>
      )}

      {pathResult && pathResult.path && (
        <Card>
          <div className="p-4 border-b border-slate-700">
            <h3 className="font-semibold text-white">
              Path Found ({pathResult.total_hops} hops)
            </h3>
          </div>
          <div className="p-4">
            <div className="flex items-center gap-2 flex-wrap">
              {pathResult.path.map((asset, index) => (
                <div key={asset.id} className="flex items-center gap-2">
                  <div className="px-3 py-2 bg-slate-700 rounded-lg">
                    <p className="font-medium text-white">{asset.name}</p>
                    <p className="text-xs text-slate-400">{asset.ip_address}</p>
                  </div>
                  {index < pathResult.path.length - 1 && (
                    <span className="text-slate-500">→</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
