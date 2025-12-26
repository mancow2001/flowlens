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
  AlertSummary,
  ChangeEventSummary,
  SavedView,
  SavedViewSummary,
  ViewConfig,
  SPOFAnalysisResult,
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
    // POST with SubgraphRequest body
    const { data } = await api.post('/topology/subgraph', {
      center_asset_id: assetId,
      depth: depth,
      direction: 'both',
      include_external: true,
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
  ): Promise<{
    asset_id: string;
    asset_name: string;
    total_affected: number;
    critical_affected: number;
    affected_assets: Array<{ id: string; name: string; depth: number; is_critical: boolean }>;
    max_depth: number;
    calculated_at: string;
  }> => {
    const { data } = await api.get(`/analysis/blast-radius/${assetId}`, {
      params: { maxDepth },
    });
    return data;
  },

  getPath: async (
    sourceId: string,
    targetId: string
  ): Promise<{ path: Asset[]; total_hops: number; path_exists: boolean }> => {
    // Path endpoint is under /topology, not /analysis
    const { data } = await api.get('/topology/path', {
      params: { sourceId, targetId },
    });
    return data;
  },

  getSPOF: async (params?: {
    environment?: string;
    minDependents?: number;
    limit?: number;
  }): Promise<SPOFAnalysisResult> => {
    const { data } = await api.get('/analysis/spof', { params });
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

// Classification Rules endpoints
export interface ClassificationRule {
  id: string;
  name: string;
  description: string | null;
  cidr: string;
  priority: number;
  environment: string | null;
  datacenter: string | null;
  location: string | null;
  asset_type: string | null;
  is_internal: boolean | null;
  default_owner: string | null;
  default_team: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ClassificationRuleSummary {
  id: string;
  name: string;
  cidr: string;
  environment: string | null;
  datacenter: string | null;
  location: string | null;
  is_active: boolean;
}

export interface IPClassificationResult {
  ip_address: string;
  matched: boolean;
  rule_id: string | null;
  rule_name: string | null;
  environment: string | null;
  datacenter: string | null;
  location: string | null;
  asset_type: string | null;
  is_internal: boolean | null;
}

export interface AssetImportPreview {
  total_rows: number;
  to_create: number;
  to_update: number;
  to_skip: number;
  errors: number;
  validations: Array<{
    row_number: number;
    ip_address: string;
    status: 'create' | 'update' | 'skip' | 'error';
    message: string | null;
    changes: Record<string, { old: unknown; new: unknown }> | null;
  }>;
}

export interface AssetImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  error_details: string[] | null;
}

export const classificationApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    is_active?: boolean;
    environment?: string;
    datacenter?: string;
  }): Promise<{ items: ClassificationRuleSummary[]; total: number; page: number; page_size: number }> => {
    const { data } = await api.get('/classification-rules', { params });
    return data;
  },

  get: async (id: string): Promise<ClassificationRule> => {
    const { data } = await api.get(`/classification-rules/${id}`);
    return data;
  },

  create: async (rule: Omit<ClassificationRule, 'id' | 'created_at' | 'updated_at'>): Promise<ClassificationRule> => {
    const { data } = await api.post('/classification-rules', rule);
    return data;
  },

  update: async (id: string, updates: Partial<ClassificationRule>): Promise<ClassificationRule> => {
    const { data } = await api.patch(`/classification-rules/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/classification-rules/${id}`);
  },

  classifyIp: async (ip: string): Promise<IPClassificationResult> => {
    const { data } = await api.get(`/classification-rules/classify/${ip}`);
    return data;
  },

  listEnvironments: async (): Promise<string[]> => {
    const { data } = await api.get('/classification-rules/environments/list');
    return data;
  },

  listDatacenters: async (): Promise<string[]> => {
    const { data } = await api.get('/classification-rules/datacenters/list');
    return data;
  },

  listLocations: async (): Promise<string[]> => {
    const { data } = await api.get('/classification-rules/locations/list');
    return data;
  },
};

// Asset bulk operations
export const assetBulkApi = {
  exportUrl: (format: 'csv' | 'json' = 'csv', params?: {
    assetType?: string;
    environment?: string;
    datacenter?: string;
    isInternal?: boolean;
  }): string => {
    const queryParams = new URLSearchParams();
    queryParams.set('format', format);
    if (params?.assetType) queryParams.set('assetType', params.assetType);
    if (params?.environment) queryParams.set('environment', params.environment);
    if (params?.datacenter) queryParams.set('datacenter', params.datacenter);
    if (params?.isInternal !== undefined) queryParams.set('isInternal', String(params.isInternal));
    return `/api/v1/assets/export?${queryParams.toString()}`;
  },

  previewImport: async (file: File): Promise<AssetImportPreview> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/assets/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  import: async (file: File, skipErrors: boolean = false): Promise<AssetImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/assets/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { skipErrors },
    });
    return data;
  },
};

export default api;
