import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { analysisApi, assetApi } from '../services/api';
import type { SPOFCandidate, Asset } from '../types';
import Card from '../components/common/Card';
import Loading from '../components/common/Loading';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import BlastRadiusTopology from '../components/analysis/BlastRadiusTopology';

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
  const { data: spofResult, isLoading, error, refetch } = useQuery({
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

  const getRiskBadgeVariant = (level: string): 'error' | 'warning' | 'info' | 'success' => {
    switch (level) {
      case 'critical': return 'error';
      case 'high': return 'error';
      case 'medium': return 'warning';
      default: return 'info';
    }
  };

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

      {spofResult && spofResult.candidates.length > 0 ? (
        <Card>
          <div className="p-4 border-b border-slate-700 flex justify-between items-center">
            <div>
              <h3 className="font-semibold text-white">
                SPOF Candidates ({spofResult.candidates.length})
              </h3>
              <p className="text-sm text-slate-400 mt-1">
                Analyzed {spofResult.total_analyzed} assets, {spofResult.high_risk_count} high risk
              </p>
            </div>
          </div>
          <div className="divide-y divide-slate-700">
            {spofResult.candidates.map((candidate: SPOFCandidate) => (
              <div key={candidate.asset_id} className="p-4 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{candidate.asset_name}</span>
                    {candidate.is_critical && (
                      <Badge variant="error" size="sm">Critical Asset</Badge>
                    )}
                    <Badge variant={getRiskBadgeVariant(candidate.risk_level)} size="sm">
                      {candidate.risk_level} risk
                    </Badge>
                  </div>
                  <p className="text-sm text-slate-400 mt-1">
                    {candidate.ip_address}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-white font-medium">
                    {candidate.dependents_count} dependents
                  </p>
                  <p className="text-xs text-slate-400">
                    {candidate.critical_dependents} critical
                  </p>
                  <p className="text-xs text-slate-500">
                    Risk score: {candidate.risk_score}
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
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [maxHops, setMaxHops] = useState(3);

  // Search for assets
  const { data: searchResults } = useQuery({
    queryKey: ['asset-search', searchQuery],
    queryFn: () => assetApi.list({ search: searchQuery, page_size: 10 }),
    enabled: searchQuery.length >= 2,
  });

  return (
    <div className="space-y-4">
      {/* Asset search */}
      <Card>
        <div className="p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-white">Select an Asset to Analyze</h3>
            {selectedAsset && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-400">Selected:</span>
                <Badge>{selectedAsset.name}</Badge>
                <button
                  onClick={() => setSelectedAsset(null)}
                  className="text-slate-400 hover:text-white text-sm"
                >
                  Clear
                </button>
              </div>
            )}
          </div>
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

          {searchResults?.items && searchResults.items.length > 0 && searchQuery.length >= 2 && (
            <div className="mt-2 border border-slate-600 rounded-lg overflow-hidden max-h-60 overflow-y-auto">
              {searchResults.items.map((asset) => (
                <button
                  key={asset.id}
                  onClick={() => {
                    setSelectedAsset(asset);
                    setSearchQuery('');
                  }}
                  className={`w-full px-4 py-2 text-left hover:bg-slate-700 transition-colors border-b border-slate-600 last:border-b-0 ${
                    selectedAsset?.id === asset.id ? 'bg-slate-700' : ''
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-white">{asset.name}</p>
                      <p className="text-sm text-slate-400">{asset.ip_address}</p>
                    </div>
                    {asset.is_critical && (
                      <Badge variant="error" size="sm">Critical</Badge>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Topology visualization */}
      {selectedAsset ? (
        <Card>
          <div className="p-4 border-b border-slate-700">
            <h3 className="font-semibold text-white">
              Blast Radius Topology: {selectedAsset.name}
            </h3>
            <p className="text-sm text-slate-400 mt-1">
              Visualizing assets within {maxHops} hop{maxHops > 1 ? 's' : ''} of the selected asset.
              Drag nodes to rearrange. Scroll to zoom.
            </p>
          </div>
          <div className="p-4">
            <BlastRadiusTopology
              centerId={selectedAsset.id}
              maxHops={maxHops}
              onHopsChange={setMaxHops}
            />
          </div>
        </Card>
      ) : (
        <Card>
          <div className="p-12 text-center">
            <MagnifyingGlassIcon className="w-12 h-12 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400">
              Search and select an asset above to visualize its blast radius topology
            </p>
            <p className="text-sm text-slate-500 mt-2">
              The blast radius shows all assets that could be affected if the selected asset fails
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

interface PathResultData {
  source_id: string;
  target_id: string;
  path_exists: boolean;
  path?: string[];
  path_length?: number;
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

  // Find path - returns UUIDs, not full assets
  const { data: pathResult, isLoading, error, refetch, isRefetching } = useQuery<PathResultData>({
    queryKey: ['path-finder', sourceId, targetId],
    queryFn: async () => {
      const result = await analysisApi.getPath(sourceId!, targetId!);
      return result as unknown as PathResultData;
    },
    enabled: false,
  });

  // Fetch asset details for the path
  const { data: pathAssets } = useQuery({
    queryKey: ['path-assets', pathResult?.path],
    queryFn: async () => {
      if (!pathResult?.path) return [];
      // Fetch each asset in the path
      const assets = await Promise.all(
        pathResult.path.map(id => assetApi.get(id))
      );
      return assets;
    },
    enabled: !!pathResult?.path && pathResult.path.length > 0,
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

      {/* Show error for API failures */}
      {error && (
        <Card>
          <div className="p-6 text-center">
            <p className="text-red-400">Failed to search for path</p>
            <p className="text-slate-500 text-sm mt-2">
              An error occurred while searching. Please try again.
            </p>
          </div>
        </Card>
      )}

      {/* Show "no path" message when path_exists is false */}
      {pathResult && !pathResult.path_exists && (
        <Card>
          <div className="p-6 text-center">
            <p className="text-yellow-400">No path found between these assets</p>
            <p className="text-slate-500 text-sm mt-2">
              The assets may not be connected, or the path may exceed the maximum depth (5 hops).
            </p>
          </div>
        </Card>
      )}

      {/* Show path when found */}
      {pathResult && pathResult.path_exists && pathAssets && pathAssets.length > 0 && (
        <Card>
          <div className="p-4 border-b border-slate-700">
            <h3 className="font-semibold text-white">
              Path Found ({pathResult.path_length} hop{pathResult.path_length !== 1 ? 's' : ''})
            </h3>
          </div>
          <div className="p-4">
            <div className="flex items-center gap-2 flex-wrap">
              {pathAssets.map((asset, index) => (
                <div key={asset.id} className="flex items-center gap-2">
                  <div className="px-3 py-2 bg-slate-700 rounded-lg">
                    <p className="font-medium text-white">{asset.name}</p>
                    <p className="text-xs text-slate-400">{asset.ip_address}</p>
                  </div>
                  {index < pathAssets.length - 1 && (
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
