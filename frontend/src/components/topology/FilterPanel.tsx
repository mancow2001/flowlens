import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import Card from '../common/Card';
import Button from '../common/Button';
import { classificationApi } from '../../services/api';
import type { TopologyFilters } from '../../hooks/useTopologyFilters';

// Standard asset types
const ASSET_TYPES = [
  { value: 'server', label: 'Server' },
  { value: 'workstation', label: 'Workstation' },
  { value: 'network_device', label: 'Network Device' },
  { value: 'load_balancer', label: 'Load Balancer' },
  { value: 'database', label: 'Database' },
  { value: 'storage', label: 'Storage' },
  { value: 'virtual_machine', label: 'Virtual Machine' },
  { value: 'container', label: 'Container' },
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

  // Sync local filters when external filters change
  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

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
    onReset();
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
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
