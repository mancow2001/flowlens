import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

export interface TopologyFilters {
  environments: string[];
  datacenters: string[];
  assetTypes: string[];
  includeExternal: boolean;
  minBytes24h: number;
  asOf: string | null;
}

const DEFAULT_FILTERS: TopologyFilters = {
  environments: [],
  datacenters: [],
  assetTypes: [],
  includeExternal: true,
  minBytes24h: 0,
  asOf: null,
};

const STORAGE_KEY = 'flowlens-topology-filters';

export function useTopologyFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFiltersState] = useState<TopologyFilters>(() => {
    // Try to restore from URL first, then localStorage
    const envParam = searchParams.get('environments');
    const dcParam = searchParams.get('datacenters');
    const typesParam = searchParams.get('assetTypes');
    const externalParam = searchParams.get('includeExternal');
    const bytesParam = searchParams.get('minBytes24h');
    const asOfParam = searchParams.get('asOf');

    if (envParam || dcParam || typesParam || externalParam || bytesParam || asOfParam) {
      return {
        environments: envParam ? envParam.split(',').filter(Boolean) : [],
        datacenters: dcParam ? dcParam.split(',').filter(Boolean) : [],
        assetTypes: typesParam ? typesParam.split(',').filter(Boolean) : [],
        includeExternal: externalParam !== 'false',
        minBytes24h: bytesParam ? parseInt(bytesParam, 10) : 0,
        asOf: asOfParam || null,
      };
    }

    // Try localStorage
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        return { ...DEFAULT_FILTERS, ...parsed };
      }
    } catch {
      // Ignore parse errors
    }

    return DEFAULT_FILTERS;
  });

  // Sync filters to URL and localStorage
  useEffect(() => {
    const params = new URLSearchParams();

    if (filters.environments.length > 0) {
      params.set('environments', filters.environments.join(','));
    }
    if (filters.datacenters.length > 0) {
      params.set('datacenters', filters.datacenters.join(','));
    }
    if (filters.assetTypes.length > 0) {
      params.set('assetTypes', filters.assetTypes.join(','));
    }
    if (!filters.includeExternal) {
      params.set('includeExternal', 'false');
    }
    if (filters.minBytes24h > 0) {
      params.set('minBytes24h', filters.minBytes24h.toString());
    }
    if (filters.asOf) {
      params.set('asOf', filters.asOf);
    }

    setSearchParams(params, { replace: true });

    // Also save to localStorage
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
    } catch {
      // Ignore storage errors
    }
  }, [filters, setSearchParams]);

  const setFilters = useCallback((newFilters: Partial<TopologyFilters>) => {
    setFiltersState(prev => ({ ...prev, ...newFilters }));
  }, []);

  const resetFilters = useCallback(() => {
    setFiltersState(DEFAULT_FILTERS);
  }, []);

  const hasActiveFilters = useCallback(() => {
    return (
      filters.environments.length > 0 ||
      filters.datacenters.length > 0 ||
      filters.assetTypes.length > 0 ||
      !filters.includeExternal ||
      filters.minBytes24h > 0 ||
      filters.asOf !== null
    );
  }, [filters]);

  return {
    filters,
    setFilters,
    resetFilters,
    hasActiveFilters,
  };
}
