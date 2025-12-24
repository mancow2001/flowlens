// Asset types
export interface Asset {
  id: string;
  name: string;
  display_name: string | null;
  asset_type: AssetType;
  ip_address: string;
  hostname: string | null;
  fqdn: string | null;
  mac_address: string | null;
  subnet: string | null;
  vlan_id: number | null;
  datacenter: string | null;
  environment: string | null;
  country_code: string | null;
  city: string | null;
  is_internal: boolean;
  is_critical: boolean;
  criticality_score: number;
  owner: string | null;
  team: string | null;
  external_id: string | null;
  description: string | null;
  tags: Record<string, string> | null;
  metadata: Record<string, unknown> | null;
  first_seen: string;
  last_seen: string;
  bytes_in_total: number;
  bytes_out_total: number;
  connections_in: number;
  connections_out: number;
  services: Service[];
  created_at: string;
  updated_at: string;
}

export type AssetType =
  | 'server'
  | 'workstation'
  | 'network_device'
  | 'database'
  | 'load_balancer'
  | 'firewall'
  | 'container'
  | 'cloud_service'
  | 'external'
  | 'unknown';

export interface Service {
  id: string;
  asset_id: string;
  port: number;
  protocol: number;
  name: string | null;
  service_type: string | null;
  version: string | null;
  first_seen: string;
  last_seen: string;
  bytes_total: number;
  connections_total: number;
}

// Dependency types
export interface AssetInfo {
  id: string;
  name: string;
  ip_address: string;
  hostname: string | null;
  is_critical: boolean;
}

export interface Dependency {
  id: string;
  source_asset_id: string;
  target_asset_id: string;
  source_asset?: AssetInfo;
  target_asset?: AssetInfo;
  target_port: number;
  protocol: number;
  dependency_type: string | null;
  is_critical: boolean;
  is_confirmed: boolean;
  is_ignored: boolean;
  description: string | null;
  tags: Record<string, string> | null;
  metadata: Record<string, unknown> | null;
  bytes_total: number;
  packets_total: number;
  flows_total: number;
  bytes_last_24h: number;
  bytes_last_7d: number;
  first_seen: string;
  last_seen: string;
  valid_from: string;
  valid_to: string | null;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  discovered_by: string;
  created_at: string;
  updated_at: string;
}

// Topology types
export interface TopologyNode {
  id: string;
  name: string;
  type: AssetType;
  ip_address: string | null;
  is_external: boolean;
  x?: number;
  y?: number;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  port: number;
  protocol: string;
  bytes_total: number;
  is_active: boolean;
}

export interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

// Alert types
export interface Alert {
  id: string;
  title: string;
  message: string;
  severity: AlertSeverity;
  change_event_id: string;
  asset_id: string | null;
  dependency_id: string | null;
  is_acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  is_resolved: boolean;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_notes: string | null;
  notification_sent: boolean;
  tags: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export type AlertSeverity = 'critical' | 'error' | 'warning' | 'info';

export interface AlertSummary {
  total: number;
  critical: number;
  error: number;
  warning: number;
  info: number;
  unacknowledged: number;
  unresolved: number;
}

// Change event types
export interface ChangeEvent {
  id: string;
  change_type: string;
  summary: string;
  description: string | null;
  detected_at: string;
  occurred_at: string | null;
  asset_id: string | null;
  dependency_id: string | null;
  source_asset_id: string | null;
  target_asset_id: string | null;
  previous_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
  impact_score: number;
  affected_assets_count: number;
  is_processed: boolean;
  processed_at: string | null;
  metadata: Record<string, unknown> | null;
  alerts_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChangeEventSummary {
  total: number;
  by_type: Record<string, number>;
  unprocessed: number;
  last_24h: number;
  last_7d: number;
}

// API response types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertListResponse extends PaginatedResponse<Alert> {
  summary: AlertSummary;
}

export interface ChangeEventListResponse extends PaginatedResponse<ChangeEvent> {
  summary: ChangeEventSummary;
}

// WebSocket event types
export interface WebSocketEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// Analysis types
export interface ImpactAnalysis {
  asset_id: string;
  asset_name: string;
  total_affected: number;
  critical_path_length: number;
  affected_assets: AffectedAsset[];
}

export interface AffectedAsset {
  id: string;
  name: string;
  type: AssetType;
  depth: number;
  path: string[];
}

export interface BlastRadius {
  center_asset_id: string;
  center_asset_name: string;
  total_affected: number;
  by_depth: Record<number, number>;
  affected_assets: AffectedAsset[];
}

// Dashboard stats
export interface DashboardStats {
  total_assets: number;
  active_assets: number;
  total_dependencies: number;
  active_dependencies: number;
  total_alerts: number;
  unresolved_alerts: number;
  changes_24h: number;
  changes_7d: number;
}
