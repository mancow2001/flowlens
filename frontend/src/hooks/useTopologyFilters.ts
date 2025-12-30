import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

export interface TopologyFilters {
  environments: string[];
  datacenters: string[];
  assetTypes: string[];
  includeExternal: boolean;
  minBytes24h: number;
  asOf: string | null;
  focusedEndpoint: string | null;  // Asset ID to focus on
  focusedEndpointName: string | null;  // Display name for the focused endpoint
  hopLevel: number;  // Number of hops for outbound connections (1-5)
}

const DEFAULT_FILTERS: TopologyFilters = {
  environments: [],
  datacenters: [],
  assetTypes: [],
  includeExternal: true,
  minBytes24h: 0,
  asOf: null,
  focusedEndpoint: null,
  focusedEndpointName: null,
  hopLevel: 1,
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
    const focusedEndpointParam = searchParams.get('focusedEndpoint');
    const focusedEndpointNameParam = searchParams.get('focusedEndpointName');
    const hopLevelParam = searchParams.get('hopLevel');

    if (envParam || dcParam || typesParam || externalParam || bytesParam || asOfParam || focusedEndpointParam) {
      return {
        environments: envParam ? envParam.split(',').filter(Boolean) : [],
        datacenters: dcParam ? dcParam.split(',').filter(Boolean) : [],
        assetTypes: typesParam ? typesParam.split(',').filter(Boolean) : [],
        includeExternal: externalParam !== 'false',
        minBytes24h: bytesParam ? parseInt(bytesParam, 10) : 0,
        asOf: asOfParam || null,
        focusedEndpoint: focusedEndpointParam || null,
        focusedEndpointName: focusedEndpointNameParam || null,
        hopLevel: hopLevelParam ? parseInt(hopLevelParam, 10) : 1,
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
    // Use a function to get current params and preserve non-filter params (e.g., source, target from search)
    setSearchParams((currentParams) => {
      const params = new URLSearchParams(currentParams);

      // Clear filter-specific params first, then set them if they have values
      params.delete('environments');
      params.delete('datacenters');
      params.delete('assetTypes');
      params.delete('includeExternal');
      params.delete('minBytes24h');
      params.delete('asOf');
      params.delete('focusedEndpoint');
      params.delete('focusedEndpointName');
      params.delete('hopLevel');

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
      if (filters.focusedEndpoint) {
        params.set('focusedEndpoint', filters.focusedEndpoint);
      }
      if (filters.focusedEndpointName) {
        params.set('focusedEndpointName', filters.focusedEndpointName);
      }
      if (filters.focusedEndpoint && filters.hopLevel !== 1) {
        params.set('hopLevel', filters.hopLevel.toString());
      }

      return params;
    }, { replace: true });

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
      filters.asOf !== null ||
      filters.focusedEndpoint !== null
    );
  }, [filters]);

  return {
    filters,
    setFilters,
    resetFilters,
    hasActiveFilters,
  };
}
