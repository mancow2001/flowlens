import axios from 'axios';
import type {
  Asset,
  Dependency,
  Alert,
  ChangeEvent,
  TopologyData,
  PaginatedResponse,
  AlertListResponse,
  ChangeEventListResponse,
  ImpactAnalysis,
  BlastRadius,
  AlertSummary,
  ChangeEventSummary,
  SavedView,
  SavedViewSummary,
  ViewConfig,
} from '../types';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Asset endpoints
export const assetApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    asset_type?: string;
    is_internal?: boolean;
    search?: string;
  }): Promise<PaginatedResponse<Asset>> => {
    // Convert to backend parameter names (camelCase aliases)
    const queryParams: Record<string, unknown> = {};
    if (params?.page) queryParams.page = params.page;
    if (params?.page_size) queryParams.page_size = params.page_size;
    if (params?.asset_type) queryParams.assetType = params.asset_type;
    if (params?.is_internal !== undefined) queryParams.isInternal = params.is_internal;
    if (params?.search) queryParams.search = params.search;

    const { data } = await api.get('/assets', { params: queryParams });
    return data;
  },

  get: async (id: string): Promise<Asset> => {
    const { data } = await api.get(`/assets/${id}`);
    return data;
  },

  getDependencies: async (
    id: string,
    direction: 'upstream' | 'downstream' | 'both' = 'both'
  ): Promise<Dependency[]> => {
    const { data } = await api.get(`/assets/${id}/dependencies`, {
      params: { direction },
    });
    return data;
  },

  update: async (id: string, updates: Partial<Asset>): Promise<Asset> => {
    const { data } = await api.patch(`/assets/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/assets/${id}`);
  },
};

// Dependency endpoints
export const dependencyApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    source_asset_id?: string;
    target_asset_id?: string;
    is_active?: boolean;
  }): Promise<PaginatedResponse<Dependency>> => {
    const { data } = await api.get('/dependencies', { params });
    return data;
  },

  get: async (id: string): Promise<Dependency> => {
    const { data } = await api.get(`/dependencies/${id}`);
    return data;
  },
};

// Topology endpoints
export const topologyApi = {
  getGraph: async (params?: {
    asset_id?: string;
    depth?: number;
    include_inactive?: boolean;
    as_of?: string;  // ISO timestamp for historical view
    asset_types?: string[];
    environments?: string[];
    datacenters?: string[];
    include_external?: boolean;
    min_bytes_24h?: number;
  }): Promise<TopologyData> => {
    // POST with filter body
    const { data } = await api.post('/topology/graph', {
      asset_id: params?.asset_id,
      depth: params?.depth,
      include_inactive: params?.include_inactive,
      as_of: params?.as_of,
      asset_types: params?.asset_types,
      environments: params?.environments,
      datacenters: params?.datacenters,
      include_external: params?.include_external,
      min_bytes_24h: params?.min_bytes_24h,
    });
    return data;
  },

  getSubgraph: async (
    assetId: string,
    depth: number = 2
  ): Promise<TopologyData> => {
    const { data } = await api.get(`/topology/subgraph/${assetId}`, {
      params: { depth },
    });
    return data;
  },
};

// Saved Views endpoints
export const savedViewsApi = {
  list: async (includePublic: boolean = true): Promise<SavedViewSummary[]> => {
    const { data } = await api.get('/saved-views', {
      params: { include_public: includePublic },
    });
    return data;
  },

  get: async (id: string): Promise<SavedView> => {
    const { data } = await api.get(`/saved-views/${id}`);
    return data;
  },

  getDefault: async (): Promise<SavedView | null> => {
    const { data } = await api.get('/saved-views/default');
    return data;
  },

  create: async (view: {
    name: string;
    description?: string;
    is_public?: boolean;
    is_default?: boolean;
    config: ViewConfig;
  }): Promise<SavedView> => {
    const { data } = await api.post('/saved-views', view);
    return data;
  },

  update: async (
    id: string,
    updates: Partial<{
      name: string;
      description: string;
      is_public: boolean;
      is_default: boolean;
      config: ViewConfig;
    }>
  ): Promise<SavedView> => {
    const { data } = await api.patch(`/saved-views/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/saved-views/${id}`);
  },
};

// Analysis endpoints
export const analysisApi = {
  getImpact: async (assetId: string, depth?: number): Promise<ImpactAnalysis> => {
    const { data } = await api.get(`/analysis/impact/${assetId}`, {
      params: { depth },
    });
    return data;
  },

  getBlastRadius: async (
    assetId: string,
    maxDepth?: number
  ): Promise<BlastRadius> => {
    const { data } = await api.get(`/analysis/blast-radius/${assetId}`, {
      params: { max_depth: maxDepth },
    });
    return data;
  },

  getPath: async (
    sourceId: string,
    targetId: string
  ): Promise<{ path: Asset[]; total_hops: number }> => {
    const { data } = await api.get('/analysis/path', {
      params: { source_id: sourceId, target_id: targetId },
    });
    return data;
  },

  getSPOF: async (): Promise<Asset[]> => {
    const { data } = await api.get('/analysis/spof');
    return data;
  },
};

// Alert endpoints
export const alertApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    severity?: string;
    is_acknowledged?: boolean;
    is_resolved?: boolean;
    asset_id?: string;
  }): Promise<AlertListResponse> => {
    const { data } = await api.get('/alerts', { params });
    return data;
  },

  get: async (id: string): Promise<Alert> => {
    const { data } = await api.get(`/alerts/${id}`);
    return data;
  },

  getSummary: async (): Promise<AlertSummary> => {
    const { data } = await api.get('/alerts/summary');
    return data;
  },

  acknowledge: async (id: string, by: string): Promise<Alert> => {
    const { data } = await api.post(`/alerts/${id}/acknowledge`, {
      acknowledged_by: by,
    });
    return data;
  },

  resolve: async (
    id: string,
    by: string,
    notes?: string
  ): Promise<Alert> => {
    const { data } = await api.post(`/alerts/${id}/resolve`, {
      resolved_by: by,
      resolution_notes: notes,
    });
    return data;
  },

  bulkAcknowledge: async (
    ids: string[],
    by: string
  ): Promise<{ acknowledged_count: number }> => {
    const { data } = await api.post('/alerts/bulk/acknowledge', ids, {
      params: { acknowledged_by: by },
    });
    return data;
  },

  bulkResolve: async (
    ids: string[],
    by: string,
    notes?: string
  ): Promise<{ resolved_count: number }> => {
    const { data } = await api.post('/alerts/bulk/resolve', ids, {
      params: { resolved_by: by, resolution_notes: notes },
    });
    return data;
  },
};

// Change event endpoints
export const changeApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    change_type?: string;
    asset_id?: string;
    is_processed?: boolean;
    since?: string;
    until?: string;
  }): Promise<ChangeEventListResponse> => {
    const { data } = await api.get('/changes', { params });
    return data;
  },

  get: async (id: string): Promise<ChangeEvent> => {
    const { data } = await api.get(`/changes/${id}`);
    return data;
  },

  getSummary: async (): Promise<ChangeEventSummary> => {
    const { data } = await api.get('/changes/summary');
    return data;
  },

  getTimeline: async (
    period: 'hour' | 'day' | 'week' = 'day',
    days: number = 7
  ): Promise<{ period: string; data: Record<string, unknown>[] }> => {
    const { data } = await api.get('/changes/timeline', {
      params: { period, days },
    });
    return data;
  },

  getTypes: async (): Promise<{ change_type: string; count: number }[]> => {
    const { data } = await api.get('/changes/types');
    return data;
  },

  markProcessed: async (id: string): Promise<ChangeEvent> => {
    const { data } = await api.post(`/changes/${id}/process`);
    return data;
  },
};

// Admin endpoints
export const adminApi = {
  getHealth: async (): Promise<{ status: string; details: Record<string, unknown> }> => {
    const { data } = await api.get('/health');
    return data;
  },

  getStats: async (): Promise<Record<string, unknown>> => {
    const { data } = await api.get('/stats');
    return data;
  },
};

export default api;
