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
  environment: Environment | null;
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
  | 'database'
  | 'load_balancer'
  | 'firewall'
  | 'router'
  | 'switch'
  | 'storage'
  | 'container'
  | 'virtual_machine'
  | 'cloud_service'
  | 'group'
  | 'unknown';

// Environment enum values
export type Environment = 'prod' | 'uat' | 'qa' | 'test' | 'dev';

export const ENVIRONMENT_OPTIONS: { value: Environment; label: string }[] = [
  { value: 'prod', label: 'Production' },
  { value: 'uat', label: 'UAT' },
  { value: 'qa', label: 'QA' },
  { value: 'test', label: 'Test' },
  { value: 'dev', label: 'Development' },
];

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

// Full dependency with all fields (used by detail views)
export interface DependencyFull {
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

// Dependency summary used by list views (matches DependencySummary schema)
export interface Dependency {
  id: string;
  source_asset_id: string;
  target_asset_id: string;
  source_asset?: AssetInfo;
  target_asset?: AssetInfo;
  target_port: number;
  protocol: number;
  bytes_total: number;
  bytes_last_24h: number;
  last_seen: string;
  valid_to: string | null;
  is_critical: boolean;
}

// Topology types
export interface TopologyNode {
  id: string;
  name: string;
  label?: string;
  asset_type: AssetType;
  ip_address: string | null;
  is_internal: boolean;
  is_critical: boolean;
  environment: Environment | null;
  datacenter: string | null;
  location?: string | null;
  connections_in: number;
  connections_out: number;
  bytes_in_24h?: number;
  bytes_out_24h?: number;
  x?: number;
  y?: number;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  target_port: number;
  protocol: number;
  protocol_name: string | null;
  service_type: string | null;
  bytes_total: number;
  bytes_last_24h: number;
  is_critical: boolean;
  last_seen: string;
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

// SPOF Analysis types
export interface SPOFCandidate {
  asset_id: string;
  asset_name: string;
  ip_address: string;
  is_critical: boolean;
  dependents_count: number;
  critical_dependents: number;
  unique_path_count: number;
  centrality_score: number;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
}

export interface SPOFAnalysisResult {
  scope: string;
  candidates: SPOFCandidate[];
  total_analyzed: number;
  high_risk_count: number;
  calculated_at: string;
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

// Saved view types
export interface ViewFilters {
  asset_types?: string[];
  environments?: string[];
  datacenters?: string[];
  include_external: boolean;
  min_bytes_24h: number;
  as_of?: string;
}

export interface ViewZoom {
  scale: number;
  x: number;
  y: number;
}

export interface ViewConfig {
  filters: ViewFilters;
  grouping: 'none' | 'location' | 'environment' | 'datacenter' | 'type';
  zoom: ViewZoom;
  selected_asset_ids: string[];
  layout_positions: Record<string, { x: number; y: number }>;
}

export interface SavedView {
  id: string;
  name: string;
  description: string | null;
  created_by: string | null;
  is_public: boolean;
  is_default: boolean;
  config: ViewConfig;
  last_accessed_at: string | null;
  access_count: number;
  created_at: string;
  updated_at: string;
}

export interface SavedViewSummary {
  id: string;
  name: string;
  description: string | null;
  is_public: boolean;
  is_default: boolean;
  access_count: number;
  created_at: string;
}

// Gateway types
export interface GatewayRelationship {
  gateway_id: string;
  gateway_asset_id: string;
  gateway_ip: string;
  gateway_name: string;
  gateway_role: GatewayRole;
  is_default: boolean;
  traffic_share: number | null;
  bytes_total: number;
  confidence: number;
  last_seen: string;
}

export type GatewayRole = 'primary' | 'secondary' | 'ecmp';

export interface AssetGatewayResponse {
  id: string;
  source_asset_id: string;
  gateway_asset_id: string;
  destination_network: string | null;
  gateway_role: GatewayRole;
  is_default_gateway: boolean;
  bytes_total: number;
  flows_total: number;
  bytes_last_24h: number;
  bytes_last_7d: number;
  traffic_share: number | null;
  confidence: number;
  confidence_scores: Record<string, number> | null;
  first_seen: string;
  last_seen: string;
  inference_method: string;
  valid_from: string;
  valid_to: string | null;
}

export interface GatewayListResponse extends PaginatedResponse<AssetGatewayResponse> {}

export interface GatewayTopologyNode {
  id: string;
  name: string;
  ip_address: string;
  asset_type: string;
  is_gateway: boolean;
  client_count: number;
}

export interface GatewayTopologyEdge {
  id: string;
  source: string;
  target: string;
  gateway_role: GatewayRole;
  is_default: boolean;
  traffic_share: number | null;
  confidence: number;
  bytes_total: number;
}

export interface GatewayTopologyData {
  nodes: GatewayTopologyNode[];
  edges: GatewayTopologyEdge[];
  generated_at: string;
}

export interface GatewayForAssetResponse {
  asset_id: string;
  asset_ip: string;
  asset_name: string;
  gateways: GatewayRelationship[];
  total_gateways: number;
}

export interface GatewayClientsResponse {
  gateway_id: string;
  gateway_ip: string;
  gateway_name: string;
  clients: GatewayRelationship[];
  total_clients: number;
}

// Background Task types
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export type TaskType =
  | 'apply_classification_rules'
  | 'bulk_asset_update'
  | 'bulk_asset_delete'
  | 'export_assets'
  | 'import_assets';

export interface TaskSummary {
  id: string;
  task_type: TaskType;
  name: string;
  status: TaskStatus;
  progress_percent: number;
  total_items: number;
  processed_items: number;
  successful_items: number;
  failed_items: number;
  skipped_items: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Task extends TaskSummary {
  description: string | null;
  duration_seconds: number | null;
  parameters: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  error_details: Record<string, unknown> | null;
  triggered_by: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  updated_at: string;
}

export interface TaskListResponse extends PaginatedResponse<TaskSummary> {}
