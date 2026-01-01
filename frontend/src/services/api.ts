import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
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
  GatewayListResponse,
  GatewayForAssetResponse,
  GatewayClientsResponse,
  GatewayTopologyData,
  AssetGatewayResponse,
  Application,
  ApplicationWithMembers,
  ApplicationCreate,
  ApplicationUpdate,
  ApplicationMember,
  ApplicationMemberCreate,
  ApplicationMemberUpdate,
  ApplicationListResponse,
  ApplicationTopology,
  EntryPoint,
  EntryPointCreate,
  EntryPointUpdate,
  SearchResponse,
  User,
  TokenResponse,
  AuthStatus,
  UserListResponse,
  UserRole,
  SAMLProvider,
  AuthSession,
} from '../types';
import { useAuthStore } from '../stores/authStore';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Flag to prevent multiple refresh requests
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else {
      promise.resolve(token!);
    }
  });
  failedQueue = [];
};

// Request interceptor - add auth token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const { accessToken } = useAuthStore.getState();
    if (accessToken && config.headers) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle 401 and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // If error is not 401 or request already retried, reject
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Don't try to refresh for auth endpoints that don't require authentication
    if (
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/refresh') ||
      originalRequest.url?.includes('/auth/status') ||
      originalRequest.url?.includes('/auth/setup') ||
      originalRequest.url?.includes('/auth/saml/')
    ) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Queue the request while refresh is in progress
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
        }
        return api(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    const { refreshToken, clearAuth, setTokens } = useAuthStore.getState();

    if (!refreshToken) {
      isRefreshing = false;
      clearAuth();
      window.location.href = '/login';
      return Promise.reject(error);
    }

    try {
      const response = await axios.post<TokenResponse>('/api/v1/auth/refresh', {
        refresh_token: refreshToken,
      });

      const { access_token, refresh_token } = response.data;
      setTokens(access_token, refresh_token);

      processQueue(null, access_token);

      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
      }

      return api(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      clearAuth();
      window.location.href = '/login';
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

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

// Search endpoints
export const searchApi = {
  search: async (params: {
    q?: string;
    source?: string;
    destination?: string;
    port?: number;
    limit?: number;
  }): Promise<SearchResponse> => {
    const { data } = await api.get('/search', { params });
    return data;
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

// Topology config response type
export interface TopologyConfig {
  discard_external_flows: boolean;
}

// Topology endpoints
export const topologyApi = {
  getConfig: async (): Promise<TopologyConfig> => {
    const { data } = await api.get('/topology/config');
    return data;
  },

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

  bulkAcknowledgeFiltered: async (
    by: string,
    filters?: {
      severity?: string;
      is_resolved?: boolean;
      asset_id?: string;
    }
  ): Promise<{ acknowledged_count: number }> => {
    const { data } = await api.post(
      '/alerts/bulk/acknowledge-filtered',
      { acknowledged_by: by },
      { params: filters }
    );
    return data;
  },

  bulkResolveFiltered: async (
    by: string,
    notes?: string,
    filters?: {
      severity?: string;
      is_acknowledged?: boolean;
      asset_id?: string;
    }
  ): Promise<{ resolved_count: number }> => {
    const { data } = await api.post(
      '/alerts/bulk/resolve-filtered',
      { resolved_by: by, resolution_notes: notes },
      { params: filters }
    );
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

export interface ClassificationRuleImportPreview {
  total_rows: number;
  to_create: number;
  to_update: number;
  to_skip: number;
  errors: number;
  validations: Array<{
    row_number: number;
    name: string;
    status: 'create' | 'update' | 'skip' | 'error';
    message: string | null;
    changes: Record<string, { old: unknown; new: unknown }> | null;
  }>;
}

export interface ClassificationRuleImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  error_details: string[] | null;
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

  // Import/Export
  exportUrl: (format: 'csv' | 'json' = 'json', params?: {
    isActive?: boolean;
    environment?: string;
    datacenter?: string;
  }): string => {
    const queryParams = new URLSearchParams();
    queryParams.set('format', format);
    if (params?.isActive !== undefined) queryParams.set('isActive', String(params.isActive));
    if (params?.environment) queryParams.set('environment', params.environment);
    if (params?.datacenter) queryParams.set('datacenter', params.datacenter);
    return `/classification-rules/export?${queryParams.toString()}`;
  },

  previewImport: async (file: File): Promise<ClassificationRuleImportPreview> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/classification-rules/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  import: async (file: File, skipErrors: boolean = false, autoApply: boolean = true): Promise<ClassificationRuleImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/classification-rules/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { skipErrors, autoApply },
    });
    return data;
  },
};

// Asset bulk operations
export interface BulkUpdateResult {
  updated: number;
  skipped: number;
  errors: number;
  error_details: string[] | null;
}

export interface BulkDeleteResult {
  deleted: number;
  not_found: number;
}

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
    return `/assets/export?${queryParams.toString()}`;
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

  bulkUpdate: async (ids: string[], updates: Record<string, string | boolean | null>): Promise<BulkUpdateResult> => {
    const { data } = await api.patch('/assets/bulk', { ids, updates });
    return data;
  },

  bulkDelete: async (ids: string[]): Promise<BulkDeleteResult> => {
    const { data } = await api.delete('/assets/bulk', { data: ids });
    return data;
  },
};

// Alert Rules endpoints
export interface AlertRule {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  change_types: string[];
  asset_filter: Record<string, unknown> | null;
  severity: string;
  title_template: string;
  description_template: string;
  notify_channels: string[] | null;
  cooldown_minutes: number;
  priority: number;
  schedule: Record<string, unknown> | null;
  tags: Record<string, unknown> | null;
  last_triggered_at: string | null;
  trigger_count: number;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleSummary {
  id: string;
  name: string;
  is_active: boolean;
  change_types: string[];
  severity: string;
  cooldown_minutes: number;
  priority: number;
  trigger_count: number;
  last_triggered_at: string | null;
}

export interface ChangeTypeInfo {
  value: string;
  label: string;
  category: string;
}

export interface AlertRuleTestResult {
  would_trigger: boolean;
  reason: string | null;
  rendered_title: string | null;
  rendered_description: string | null;
}

// Maintenance Windows endpoints
export interface MaintenanceWindow {
  id: string;
  name: string;
  description: string | null;
  asset_ids: string[] | null;
  environments: string[] | null;
  datacenters: string[] | null;
  start_time: string;
  end_time: string;
  is_recurring: boolean;
  recurrence_rule: string | null;
  suppress_alerts: boolean;
  suppress_notifications: boolean;
  is_active: boolean;
  created_by: string;
  suppressed_alerts_count: number;
  tags: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface MaintenanceWindowSummary {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
  is_active: boolean;
  is_recurring: boolean;
  suppress_alerts: boolean;
  environments: string[] | null;
  datacenters: string[] | null;
  asset_count: number;
  suppressed_alerts_count: number;
}

export const maintenanceApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    isActive?: boolean;
    includePast?: boolean;
    environment?: string;
    datacenter?: string;
  }): Promise<{ items: MaintenanceWindowSummary[]; total: number; page: number; page_size: number }> => {
    const { data } = await api.get('/maintenance', { params });
    return data;
  },

  getActive: async (): Promise<MaintenanceWindowSummary[]> => {
    const { data } = await api.get('/maintenance/active');
    return data;
  },

  get: async (id: string): Promise<MaintenanceWindow> => {
    const { data } = await api.get(`/maintenance/${id}`);
    return data;
  },

  create: async (window: Omit<MaintenanceWindow, 'id' | 'created_at' | 'updated_at' | 'is_active' | 'suppressed_alerts_count'>): Promise<MaintenanceWindow> => {
    const { data } = await api.post('/maintenance', window);
    return data;
  },

  update: async (id: string, updates: Partial<MaintenanceWindow>): Promise<MaintenanceWindow> => {
    const { data } = await api.patch(`/maintenance/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/maintenance/${id}`);
  },

  cancel: async (id: string): Promise<MaintenanceWindow> => {
    const { data } = await api.post(`/maintenance/${id}/cancel`);
    return data;
  },

  checkAsset: async (assetId: string, environment?: string, datacenter?: string): Promise<{
    asset_id: string;
    in_maintenance: boolean;
    windows: MaintenanceWindowSummary[];
  }> => {
    const { data } = await api.get(`/maintenance/check/${assetId}`, {
      params: { environment, datacenter },
    });
    return data;
  },
};

export const alertRulesApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    isActive?: boolean;
    severity?: string;
    changeType?: string;
  }): Promise<{ items: AlertRuleSummary[]; total: number; page: number; page_size: number }> => {
    const { data } = await api.get('/alert-rules', { params });
    return data;
  },

  get: async (id: string): Promise<AlertRule> => {
    const { data } = await api.get(`/alert-rules/${id}`);
    return data;
  },

  create: async (rule: Omit<AlertRule, 'id' | 'created_at' | 'updated_at' | 'last_triggered_at' | 'trigger_count'>): Promise<AlertRule> => {
    const { data } = await api.post('/alert-rules', rule);
    return data;
  },

  update: async (id: string, updates: Partial<AlertRule>): Promise<AlertRule> => {
    const { data } = await api.patch(`/alert-rules/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/alert-rules/${id}`);
  },

  toggle: async (id: string): Promise<AlertRule> => {
    const { data } = await api.post(`/alert-rules/${id}/toggle`);
    return data;
  },

  test: async (id: string, changeType: string, assetData?: Record<string, unknown>): Promise<AlertRuleTestResult> => {
    const { data } = await api.post(`/alert-rules/${id}/test`, {
      change_type: changeType,
      asset_data: assetData,
    });
    return data;
  },

  listChangeTypes: async (): Promise<ChangeTypeInfo[]> => {
    const { data } = await api.get('/alert-rules/change-types');
    return data;
  },
};

// Settings types
export interface FieldMetadata {
  name: string;
  label: string;
  description: string | null;
  field_type: 'string' | 'integer' | 'float' | 'boolean' | 'secret' | 'select' | 'list' | 'path' | 'ip_address';
  required: boolean;
  default: unknown;
  min_value: number | null;
  max_value: number | null;
  options: string[] | null;
  env_var: string;
  restart_required: boolean;
  is_secret: boolean;
}

export interface SettingsSection {
  key: string;
  name: string;
  description: string;
  icon: string;
  fields: FieldMetadata[];
  restart_required: boolean;
  has_connection_test: boolean;
}

export interface SettingsValue {
  name: string;
  value: unknown;
  is_default: boolean;
}

export interface SettingsSectionData {
  key: string;
  values: SettingsValue[];
}

export interface SettingsResponse {
  sections: SettingsSection[];
  restart_required: boolean;
}

export interface SettingsSectionResponse {
  section: SettingsSection;
  data: SettingsSectionData;
  restart_required: boolean;
}

export interface SettingsUpdateResponse {
  success: boolean;
  message: string;
  restart_required: boolean;
  updated_fields: string[];
  docker_mode: boolean;
}

export interface ConnectionTestResponse {
  success: boolean;
  message: string;
  details: Record<string, unknown> | null;
}

export interface RestartResponse {
  success: boolean;
  message: string;
  method: 'docker' | 'manual' | null;
}

// Settings API endpoints
export const settingsApi = {
  getAll: async (): Promise<SettingsResponse> => {
    const { data } = await api.get('/settings');
    return data;
  },

  getSection: async (sectionKey: string): Promise<SettingsSectionResponse> => {
    const { data } = await api.get(`/settings/${sectionKey}`);
    return data;
  },

  updateSection: async (sectionKey: string, values: Record<string, unknown>): Promise<SettingsUpdateResponse> => {
    const { data } = await api.put(`/settings/${sectionKey}`, { values });
    return data;
  },

  testConnection: async (service: string, testValues?: Record<string, unknown>): Promise<ConnectionTestResponse> => {
    const { data } = await api.post(`/settings/test-connection/${service}`, {
      test_values: testValues,
    });
    return data;
  },

  restart: async (): Promise<RestartResponse> => {
    const { data } = await api.post('/settings/restart');
    return data;
  },

  checkRestartRequired: async (): Promise<{ restart_required: boolean }> => {
    const { data } = await api.get('/settings/restart-required');
    return data;
  },

  clearRestartFlag: async (): Promise<{ message: string }> => {
    const { data } = await api.post('/settings/clear-restart-flag');
    return data;
  },

  downloadDockerComposeUrl: (): string => {
    return '/api/v1/settings/export/docker-compose.yml';
  },
};

// Gateway endpoints
export const gatewayApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    asset_id?: string;
    role?: string;
    min_confidence?: number;
  }): Promise<GatewayListResponse> => {
    const { data } = await api.get('/gateways', { params });
    return data;
  },

  get: async (id: string): Promise<AssetGatewayResponse> => {
    const { data } = await api.get(`/gateways/${id}`);
    return data;
  },

  getForAsset: async (assetId: string): Promise<GatewayForAssetResponse> => {
    const { data } = await api.get(`/gateways/for-asset/${assetId}`);
    return data;
  },

  getClients: async (gatewayAssetId: string): Promise<GatewayClientsResponse> => {
    const { data } = await api.get(`/gateways/clients/${gatewayAssetId}`);
    return data;
  },

  getTopology: async (params?: {
    min_confidence?: number;
    as_of?: string;
  }): Promise<GatewayTopologyData> => {
    const { data } = await api.get('/gateways/topology', { params });
    return data;
  },
};

// Background Tasks endpoints
import type { Task, TaskListResponse } from '../types';

export const tasksApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    taskType?: string;
  }): Promise<TaskListResponse> => {
    const { data } = await api.get('/tasks', { params });
    return data;
  },

  get: async (id: string): Promise<Task> => {
    const { data } = await api.get(`/tasks/${id}`);
    return data;
  },

  cancel: async (id: string): Promise<Task> => {
    const { data } = await api.post(`/tasks/${id}/cancel`);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/tasks/${id}`);
  },

  applyClassificationRules: async (params?: {
    force?: boolean;
    ruleId?: string;
  }): Promise<Task> => {
    const { data } = await api.post('/tasks/apply-classification-rules', {
      force: params?.force ?? false,
      rule_id: params?.ruleId,
    });
    return data;
  },

  getRunningCount: async (): Promise<{ running: number }> => {
    const { data } = await api.get('/tasks/running/count');
    return data;
  },
};

// Application Import/Export types
export interface ApplicationImportPreview {
  total_rows: number;
  to_create: number;
  to_update: number;
  to_skip: number;
  errors: number;
  validations: Array<{
    row_number: number;
    name: string;
    status: 'create' | 'update' | 'skip' | 'error';
    message: string | null;
    changes: Record<string, { old: unknown; new: unknown }> | null;
    member_changes: Array<{
      action: 'add' | 'remove' | 'update';
      asset_ip: string;
      role?: string | null;
      entry_points?: number;
      role_changed?: boolean;
      entry_points_changed?: boolean;
    }> | null;
  }>;
}

export interface ApplicationImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  members_added: number;
  members_updated: number;
  members_removed: number;
  error_details: string[] | null;
}

// Applications endpoints
export const applicationsApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    search?: string;
    environment?: string;
    team?: string;
    criticality?: string;
  }): Promise<ApplicationListResponse> => {
    const { data } = await api.get('/applications', { params });
    return data;
  },

  get: async (id: string): Promise<ApplicationWithMembers> => {
    const { data } = await api.get(`/applications/${id}`);
    return data;
  },

  create: async (application: ApplicationCreate): Promise<ApplicationWithMembers> => {
    const { data } = await api.post('/applications', application);
    return data;
  },

  update: async (id: string, updates: ApplicationUpdate): Promise<Application> => {
    const { data } = await api.put(`/applications/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/applications/${id}`);
  },

  // Member management
  listMembers: async (id: string, entryPointsOnly?: boolean): Promise<ApplicationMember[]> => {
    const { data } = await api.get(`/applications/${id}/members`, {
      params: { entryPointsOnly },
    });
    return data;
  },

  addMember: async (id: string, member: ApplicationMemberCreate): Promise<ApplicationMember> => {
    const { data } = await api.post(`/applications/${id}/members`, member);
    return data;
  },

  updateMember: async (
    applicationId: string,
    assetId: string,
    updates: ApplicationMemberUpdate
  ): Promise<ApplicationMember> => {
    const { data } = await api.patch(`/applications/${applicationId}/members/${assetId}`, updates);
    return data;
  },

  removeMember: async (applicationId: string, assetId: string): Promise<void> => {
    await api.delete(`/applications/${applicationId}/members/${assetId}`);
  },

  // Entry point CRUD methods
  listEntryPoints: async (applicationId: string, assetId: string): Promise<EntryPoint[]> => {
    const { data } = await api.get(`/applications/${applicationId}/members/${assetId}/entry-points`);
    return data;
  },

  addEntryPoint: async (
    applicationId: string,
    assetId: string,
    entryPoint: EntryPointCreate
  ): Promise<EntryPoint> => {
    const { data } = await api.post(
      `/applications/${applicationId}/members/${assetId}/entry-points`,
      entryPoint
    );
    return data;
  },

  updateEntryPoint: async (
    applicationId: string,
    assetId: string,
    entryPointId: string,
    updates: EntryPointUpdate
  ): Promise<EntryPoint> => {
    const { data } = await api.patch(
      `/applications/${applicationId}/members/${assetId}/entry-points/${entryPointId}`,
      updates
    );
    return data;
  },

  deleteEntryPoint: async (
    applicationId: string,
    assetId: string,
    entryPointId: string
  ): Promise<void> => {
    await api.delete(
      `/applications/${applicationId}/members/${assetId}/entry-points/${entryPointId}`
    );
  },

  // Topology endpoint
  getTopology: async (id: string, includeExternal?: boolean, maxDepth?: number): Promise<ApplicationTopology> => {
    const { data } = await api.get(`/applications/${id}/topology`, {
      params: {
        include_external: includeExternal,
        max_depth: maxDepth,
      },
    });
    return data;
  },

  // Import/Export
  exportUrl: (params?: {
    environment?: string;
    team?: string;
    criticality?: string;
  }): string => {
    const queryParams = new URLSearchParams();
    if (params?.environment) queryParams.set('environment', params.environment);
    if (params?.team) queryParams.set('team', params.team);
    if (params?.criticality) queryParams.set('criticality', params.criticality);
    const query = queryParams.toString();
    return `/applications/export${query ? `?${query}` : ''}`;
  },

  previewImport: async (file: File): Promise<ApplicationImportPreview> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/applications/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  import: async (file: File, skipErrors: boolean = false, syncMembers: boolean = true): Promise<ApplicationImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post('/applications/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { skipErrors, syncMembers },
    });
    return data;
  },
};

// Auth API endpoints
export const authApi = {
  getStatus: async (): Promise<AuthStatus> => {
    const { data } = await api.get('/auth/status');
    return data;
  },

  login: async (email: string, password: string): Promise<TokenResponse> => {
    const { data } = await api.post('/auth/login', { email, password });
    return data;
  },

  refresh: async (refreshToken: string): Promise<TokenResponse> => {
    const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken });
    return data;
  },

  logout: async (refreshToken?: string): Promise<void> => {
    await api.post('/auth/logout', refreshToken ? { refresh_token: refreshToken } : undefined);
  },

  getCurrentUser: async (): Promise<User> => {
    const { data } = await api.get('/auth/me');
    return data;
  },

  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },

  getSessions: async (): Promise<{ items: AuthSession[]; total: number }> => {
    const { data } = await api.get('/auth/sessions');
    return data;
  },

  revokeSession: async (sessionId: string): Promise<void> => {
    await api.delete(`/auth/sessions/${sessionId}`);
  },

  setup: async (data: { email: string; name: string; password: string }): Promise<{
    success: boolean;
    message: string;
    user: User;
  }> => {
    const { data: response } = await api.post('/auth/setup', data);
    return response;
  },
};

// User Management API endpoints (admin only)
export const userApi = {
  list: async (params?: {
    page?: number;
    page_size?: number;
    is_active?: boolean;
    is_local?: boolean;
    role?: UserRole;
    search?: string;
  }): Promise<UserListResponse> => {
    const { data } = await api.get('/users', { params });
    return data;
  },

  get: async (id: string): Promise<User> => {
    const { data } = await api.get(`/users/${id}`);
    return data;
  },

  create: async (user: {
    email: string;
    name: string;
    password: string;
    role: UserRole;
  }): Promise<User> => {
    const { data } = await api.post('/users', user);
    return data;
  },

  update: async (
    id: string,
    updates: {
      email?: string;
      name?: string;
      role?: UserRole;
      is_active?: boolean;
    }
  ): Promise<User> => {
    const { data } = await api.patch(`/users/${id}`, updates);
    return data;
  },

  deactivate: async (id: string): Promise<void> => {
    await api.delete(`/users/${id}`);
  },

  resetPassword: async (id: string, newPassword: string): Promise<void> => {
    await api.post(`/users/${id}/reset-password`, { new_password: newPassword });
  },

  unlock: async (id: string): Promise<void> => {
    await api.post(`/users/${id}/unlock`);
  },
};

// SAML Provider API endpoints (admin only)
export const samlProviderApi = {
  list: async (): Promise<{ items: SAMLProvider[]; total: number }> => {
    const { data } = await api.get('/saml-providers');
    return data;
  },

  get: async (id: string): Promise<SAMLProvider & { certificate: string }> => {
    const { data } = await api.get(`/saml-providers/${id}`);
    return data;
  },

  create: async (provider: {
    name: string;
    provider_type: 'azure_ad' | 'okta' | 'ping_identity';
    entity_id: string;
    sso_url: string;
    slo_url?: string;
    certificate: string;
    sp_entity_id: string;
    role_attribute?: string;
    role_mapping?: Record<string, string>;
    default_role?: UserRole;
    auto_provision_users?: boolean;
  }): Promise<SAMLProvider> => {
    const { data } = await api.post('/saml-providers', provider);
    return data;
  },

  update: async (
    id: string,
    updates: Partial<{
      name: string;
      entity_id: string;
      sso_url: string;
      slo_url: string;
      certificate: string;
      sp_entity_id: string;
      role_attribute: string;
      role_mapping: Record<string, string>;
      default_role: UserRole;
      auto_provision_users: boolean;
    }>
  ): Promise<SAMLProvider> => {
    const { data } = await api.patch(`/saml-providers/${id}`, updates);
    return data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/saml-providers/${id}`);
  },

  activate: async (id: string): Promise<SAMLProvider> => {
    const { data } = await api.post(`/saml-providers/${id}/activate`);
    return data;
  },
};

// Helper function to download files with authentication
export const downloadWithAuth = async (url: string, filename: string): Promise<void> => {
  const response = await api.get(url, {
    responseType: 'blob',
  });

  // Get filename from Content-Disposition header if available
  const contentDisposition = response.headers['content-disposition'];
  let downloadFilename = filename;
  if (contentDisposition) {
    const filenameMatch = contentDisposition.match(/filename="?(.+?)"?(?:;|$)/);
    if (filenameMatch) {
      downloadFilename = filenameMatch[1];
    }
  }

  // Create blob URL and trigger download
  const blob = new Blob([response.data]);
  const downloadUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.download = downloadFilename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(downloadUrl);
};

export default api;
