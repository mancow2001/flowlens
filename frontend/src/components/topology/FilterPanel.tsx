import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import Card from '../common/Card';
import Button from '../common/Button';
import { classificationApi, assetApi } from '../../services/api';
import type { TopologyFilters } from '../../hooks/useTopologyFilters';
import type { Asset } from '../../types';

// Standard asset types - must match backend AssetType enum in models/asset.py
const ASSET_TYPES = [
  { value: 'server', label: 'Server' },
  { value: 'workstation', label: 'Workstation' },
  { value: 'database', label: 'Database' },
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

interface FilterPanelProps {
  filters: TopologyFilters;
  onFiltersChange: (filters: Partial<TopologyFilters>) => void;
  onReset: () => void;
  hasActiveFilters: boolean;
}

export default function FilterPanel({
  filters,
  onFiltersChange,
  onReset,
  hasActiveFilters,
}: FilterPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [localFilters, setLocalFilters] = useState(filters);

  // Focused endpoint search state
  const [endpointSearchQuery, setEndpointSearchQuery] = useState('');
  const [showEndpointDropdown, setShowEndpointDropdown] = useState(false);
  const endpointSearchRef = useRef<HTMLDivElement>(null);

  // Sync local filters when external filters change
  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (endpointSearchRef.current && !endpointSearchRef.current.contains(event.target as Node)) {
        setShowEndpointDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Search for assets
  const { data: assetSearchResults, isLoading: isSearchingAssets } = useQuery({
    queryKey: ['asset-search', endpointSearchQuery],
    queryFn: () => assetApi.list({ search: endpointSearchQuery, page_size: 10 }),
    enabled: endpointSearchQuery.length >= 2,
    staleTime: 30 * 1000, // 30 seconds
  });

  // Fetch available environments and datacenters
  const { data: environments = [] } = useQuery({
    queryKey: ['classification-environments'],
    queryFn: () => classificationApi.listEnvironments(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const { data: datacenters = [] } = useQuery({
    queryKey: ['classification-datacenters'],
    queryFn: () => classificationApi.listDatacenters(),
    staleTime: 5 * 60 * 1000,
  });

  const handleApply = () => {
    onFiltersChange(localFilters);
  };

  const handleReset = () => {
    setEndpointSearchQuery('');
    onReset();
  };

  const handleSelectEndpoint = (asset: Asset) => {
    setLocalFilters(prev => ({
      ...prev,
      focusedEndpoint: asset.id,
      focusedEndpointName: asset.name || asset.ip_address || asset.id,
    }));
    setEndpointSearchQuery('');
    setShowEndpointDropdown(false);
  };

  const handleClearEndpoint = () => {
    setLocalFilters(prev => ({
      ...prev,
      focusedEndpoint: null,
      focusedEndpointName: null,
      hopLevel: 1,
    }));
    setEndpointSearchQuery('');
  };

  const toggleArrayValue = (
    key: 'environments' | 'datacenters' | 'assetTypes',
    value: string
  ) => {
    setLocalFilters(prev => {
      const current = prev[key];
      const newValues = current.includes(value)
        ? current.filter(v => v !== value)
        : [...current, value];
      return { ...prev, [key]: newValues };
    });
  };

  // Format bytes for display
  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (isCollapsed) {
    return (
      <div className="w-12">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-12 h-12 flex items-center justify-center bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
          title="Show filters"
        >
          <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          {hasActiveFilters && (
            <span className="absolute top-1 right-1 w-2 h-2 bg-primary-500 rounded-full" />
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="w-64 flex-shrink-0">
      <Card className="h-full overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
            Filters
          </h3>
          <button
            onClick={() => setIsCollapsed(true)}
            className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
            title="Collapse filters"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        </div>

        <div className="space-y-5">
          {/* Focused Endpoint */}
          <div>
            <label className="block text-xs text-slate-400 uppercase tracking-wider mb-2">
              Focused Endpoint
            </label>
            {localFilters.focusedEndpoint ? (
              <div className="flex items-center gap-2 bg-primary-500/20 border border-primary-500/30 rounded-lg px-3 py-2">
                <svg className="w-4 h-4 text-primary-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-sm text-primary-300 truncate flex-1" title={localFilters.focusedEndpointName || localFilters.focusedEndpoint}>
                  {localFilters.focusedEndpointName || localFilters.focusedEndpoint}
                </span>
                <button
                  onClick={handleClearEndpoint}
                  className="p-0.5 rounded hover:bg-primary-500/30 text-primary-400 hover:text-primary-200 transition-colors"
                  title="Clear focused endpoint"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ) : (
              <div ref={endpointSearchRef} className="relative">
                <div className="relative">
                  <input
                    type="text"
                    value={endpointSearchQuery}
                    onChange={(e) => {
                      setEndpointSearchQuery(e.target.value);
                      setShowEndpointDropdown(e.target.value.length >= 2);
                    }}
                    onFocus={() => endpointSearchQuery.length >= 2 && setShowEndpointDropdown(true)}
                    placeholder="Search by name or IP..."
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  {isSearchingAssets && (
                    <div className="absolute right-2 top-1/2 -translate-y-1/2">
                      <svg className="w-4 h-4 text-slate-400 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    </div>
                  )}
                </div>
                {showEndpointDropdown && assetSearchResults && (
                  <div className="absolute z-50 w-full mt-1 bg-slate-800 border border-slate-600 rounded-lg shadow-xl max-h-48 overflow-y-auto">
                    {assetSearchResults.items.length > 0 ? (
                      assetSearchResults.items.map((asset) => (
                        <button
                          key={asset.id}
                          onClick={() => handleSelectEndpoint(asset)}
                          className="w-full px-3 py-2 text-left hover:bg-slate-700 transition-colors first:rounded-t-lg last:rounded-b-lg"
                        >
                          <div className="text-sm text-slate-200 truncate">
                            {asset.name || asset.ip_address || asset.id}
                          </div>
                          <div className="text-xs text-slate-500 flex items-center gap-2">
                            <span>{asset.ip_address}</span>
                            {asset.asset_type && (
                              <>
                                <span>•</span>
                                <span className="capitalize">{asset.asset_type.replace('_', ' ')}</span>
                              </>
                            )}
                          </div>
                        </button>
                      ))
                    ) : (
                      <div className="px-3 py-2 text-sm text-slate-500 italic">
                        No assets found
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            <p className="mt-1 text-xs text-slate-500">
              Focus on a specific endpoint and its connections
            </p>
          </div>

          {/* Hop Level (only shown when endpoint is focused) */}
          {localFilters.focusedEndpoint && (
            <div>
              <label className="block text-xs text-slate-400 uppercase tracking-wider mb-2">
                Connection Depth (Hops)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="1"
                  max="5"
                  value={localFilters.hopLevel}
                  onChange={(e) => setLocalFilters(prev => ({
                    ...prev,
                    hopLevel: parseInt(e.target.value, 10),
                  }))}
                  className="flex-1 h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-primary-500"
                />
                <span className="text-sm text-slate-300 w-6 text-center font-medium">
                  {localFilters.hopLevel}
                </span>
              </div>
              <div className="flex justify-between text-xs text-slate-500 mt-1">
                <span>1 hop</span>
                <span>5 hops</span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                How many connection levels to show from the focused endpoint
              </p>
            </div>
          )}

          {/* Environments */}
          <div>
            <label className="block text-xs text-slate-400 uppercase tracking-wider mb-2">
              Environments
            </label>
            {environments.length > 0 ? (
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {environments.map(env => (
                  <label
                    key={env}
                    className="flex items-center gap-2 cursor-pointer hover:bg-slate-700/50 px-2 py-1 rounded -mx-2"
                  >
                    <input
                      type="checkbox"
                      checked={localFilters.environments.includes(env)}
                      onChange={() => toggleArrayValue('environments', env)}
                      className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                    />
                    <span className="text-sm text-slate-300">{env}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">No environments defined</p>
            )}
          </div>

          {/* Datacenters */}
          <div>
            <label className="block text-xs text-slate-400 uppercase tracking-wider mb-2">
              Datacenters
            </label>
            {datacenters.length > 0 ? (
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {datacenters.map(dc => (
                  <label
                    key={dc}
                    className="flex items-center gap-2 cursor-pointer hover:bg-slate-700/50 px-2 py-1 rounded -mx-2"
                  >
                    <input
                      type="checkbox"
                      checked={localFilters.datacenters.includes(dc)}
                      onChange={() => toggleArrayValue('datacenters', dc)}
                      className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                    />
                    <span className="text-sm text-slate-300">{dc}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500 italic">No datacenters defined</p>
            )}
          </div>

          {/* Asset Types */}
          <div>
            <label className="block text-xs text-slate-400 uppercase tracking-wider mb-2">
              Asset Types
            </label>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {ASSET_TYPES.map(type => (
                <label
                  key={type.value}
                  className="flex items-center gap-2 cursor-pointer hover:bg-slate-700/50 px-2 py-1 rounded -mx-2"
                >
                  <input
                    type="checkbox"
                    checked={localFilters.assetTypes.includes(type.value)}
                    onChange={() => toggleArrayValue('assetTypes', type.value)}
                    className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                  />
                  <span className="text-sm text-slate-300">{type.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Include External */}
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={localFilters.includeExternal}
                onChange={(e) => setLocalFilters(prev => ({
                  ...prev,
                  includeExternal: e.target.checked,
                }))}
                className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
              />
              <span className="text-sm text-slate-300">Include External Assets</span>
            </label>
          </div>

          {/* Min Bytes 24h */}
          <div>
            <label className="block text-xs text-slate-400 uppercase tracking-wider mb-2">
              Min Traffic (24h)
            </label>
            <div className="space-y-2">
              <input
                type="range"
                min="0"
                max="10000000" // 10 MB
                step="10000"
                value={localFilters.minBytes24h}
                onChange={(e) => setLocalFilters(prev => ({
                  ...prev,
                  minBytes24h: parseInt(e.target.value, 10),
                }))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-primary-500"
              />
              <div className="flex justify-between text-xs text-slate-500">
                <span>0</span>
                <span className="text-slate-300">{formatBytes(localFilters.minBytes24h)}</span>
                <span>10 MB</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2 border-t border-slate-700">
            <Button
              variant="primary"
              size="sm"
              className="flex-1"
              onClick={handleApply}
            >
              Apply
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReset}
              disabled={!hasActiveFilters}
            >
              Reset
            </Button>
          </div>

          {/* Active Filters Summary */}
          {hasActiveFilters && (
            <div className="pt-2 border-t border-slate-700">
              <p className="text-xs text-slate-400 mb-2">Active Filters:</p>
              <div className="flex flex-wrap gap-1">
                {localFilters.environments.map(env => (
                  <span
                    key={`env-${env}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/20 text-blue-300 text-xs rounded"
                  >
                    {env}
                    <button
                      onClick={() => toggleArrayValue('environments', env)}
                      className="hover:text-blue-100"
                    >
                      x
                    </button>
                  </span>
                ))}
                {localFilters.datacenters.map(dc => (
                  <span
                    key={`dc-${dc}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-500/20 text-green-300 text-xs rounded"
                  >
                    {dc}
                    <button
                      onClick={() => toggleArrayValue('datacenters', dc)}
                      className="hover:text-green-100"
                    >
                      x
                    </button>
                  </span>
                ))}
                {localFilters.assetTypes.map(type => (
                  <span
                    key={`type-${type}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded"
                  >
                    {type.replace('_', ' ')}
                    <button
                      onClick={() => toggleArrayValue('assetTypes', type)}
                      className="hover:text-purple-100"
                    >
                      x
                    </button>
                  </span>
                ))}
                {!localFilters.includeExternal && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-orange-500/20 text-orange-300 text-xs rounded">
                    Internal Only
                  </span>
                )}
                {localFilters.minBytes24h > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-yellow-500/20 text-yellow-300 text-xs rounded">
                    &gt;{formatBytes(localFilters.minBytes24h)}
                  </span>
                )}
                {localFilters.focusedEndpoint && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-500/20 text-primary-300 text-xs rounded">
                    Focus: {localFilters.focusedEndpointName || localFilters.focusedEndpoint}
                    <button
                      onClick={handleClearEndpoint}
                      className="hover:text-primary-100"
                    >
                      x
                    </button>
                  </span>
                )}
                {localFilters.focusedEndpoint && localFilters.hopLevel > 1 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-cyan-500/20 text-cyan-300 text-xs rounded">
                    {localFilters.hopLevel} hops
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
