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

// Application types
export type Criticality = 'low' | 'medium' | 'high' | 'critical';

export interface EntryPoint {
  id: string;
  member_id: string;
  port: number;
  protocol: number;
  order: number;
  label: string | null;
  created_at: string;
  updated_at: string;
}

export interface EntryPointCreate {
  port: number;
  protocol?: number;
  order?: number;
  label?: string | null;
}

export interface EntryPointUpdate {
  port?: number;
  protocol?: number;
  order?: number;
  label?: string | null;
}

export interface ApplicationMember {
  id: string;
  asset_id: string;
  asset: AssetSummary;
  role: string | null;
  entry_points: EntryPoint[];
  created_at: string;
  updated_at: string;
}

// Helper to check if a member has entry points
export const isEntryPoint = (member: ApplicationMember): boolean => {
  return member.entry_points.length > 0;
};

export interface Application {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  owner: string | null;
  team: string | null;
  environment: string | null;
  criticality: Criticality | null;
  tags: Record<string, string> | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationWithMembers extends Application {
  members: ApplicationMember[];
}

export interface ApplicationMemberCreate {
  asset_id: string;
  role?: string | null;
  entry_points?: EntryPointCreate[];
}

export interface ApplicationCreate {
  name: string;
  display_name?: string | null;
  description?: string | null;
  owner?: string | null;
  team?: string | null;
  environment?: string | null;
  criticality?: Criticality | null;
  tags?: Record<string, string> | null;
  metadata?: Record<string, unknown> | null;
  members?: ApplicationMemberCreate[];
}

export interface ApplicationUpdate {
  name?: string;
  display_name?: string | null;
  description?: string | null;
  owner?: string | null;
  team?: string | null;
  environment?: string | null;
  criticality?: Criticality | null;
  tags?: Record<string, string> | null;
  metadata?: Record<string, unknown> | null;
}

export interface ApplicationMemberUpdate {
  role?: string | null;
}

export interface ApplicationListResponse extends PaginatedResponse<Application> {}

// Application topology types
export interface TopologyEntryPoint {
  id: string;
  port: number;
  protocol: number;
  order: number;
  label: string | null;
}

export interface ApplicationTopologyNode {
  id: string;
  name: string;
  display_name: string | null;
  ip_address: string;
  asset_type: AssetType;
  is_entry_point: boolean;
  entry_points: TopologyEntryPoint[];
  entry_point_order: number | null;
  role: string | null;
  is_critical: boolean;
  is_external?: boolean;
  is_internal_asset?: boolean;
  hop_distance?: number;
  from_entry_points?: Array<{
    entry_point_id: string;
    distance: number;
  }>;
}

export interface ApplicationTopologyEdge {
  source: string;
  target: string;
  target_port: number;
  protocol: number;
  dependency_type: string | null;
  bytes_last_24h: number | null;
  last_seen: string | null;
  is_internal: boolean;
  is_from_entry_point?: boolean;
  hop_distance?: number;
}

export interface ApplicationEntryPoint {
  id: string;
  asset_id: string;
  asset_name: string;
  port: number;
  protocol: number;
  order: number;
  label: string | null;
}

export interface InboundSummary {
  entry_point_id: string;
  entry_point_asset_id: string;
  entry_point_name: string;
  port: number;
  protocol: number;
  label: string | null;
  client_count: number;
  total_bytes_24h: number;
}

export interface ApplicationTopology {
  application: {
    id: string;
    name: string;
    display_name: string | null;
  };
  nodes: ApplicationTopologyNode[];
  edges: ApplicationTopologyEdge[];
  entry_points: ApplicationEntryPoint[];
  inbound_summary: InboundSummary[];
  max_depth: number;
}

// Asset summary type (referenced by ApplicationMember)
export interface AssetSummary {
  id: string;
  name: string;
  display_name: string | null;
  asset_type: AssetType;
  ip_address: string;
  hostname: string | null;
  is_internal: boolean;
  is_critical: boolean;
  last_seen: string;
}

// Search types
export interface ConnectionMatch {
  id: string;
  source: AssetInfo;
  target: AssetInfo;
  target_port: number;
  protocol: number;
  bytes_last_24h: number;
  last_seen: string;
}

export interface SearchResponse {
  assets: AssetSummary[];
  connections: ConnectionMatch[];
}

// Auth types
export type UserRole = 'admin' | 'analyst' | 'viewer';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  is_active: boolean;
  is_local: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthStatus {
  auth_enabled: boolean;
  saml_enabled: boolean;
  setup_required: boolean;
  active_provider: SAMLProvider | null;
}

export interface InitialSetupRequest {
  email: string;
  name: string;
  password: string;
}

export interface InitialSetupResponse {
  success: boolean;
  message: string;
  user: User;
}

export interface SAMLProvider {
  id: string;
  name: string;
  provider_type: SAMLProviderType;
  entity_id: string;
  sso_url: string;
  slo_url: string | null;
  certificate: string;
  sp_entity_id: string;
  role_attribute: string | null;
  role_mapping: Record<string, string> | null;
  default_role: UserRole;
  auto_provision_users: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type SAMLProviderType = 'azure_ad' | 'okta' | 'ping_identity';

export interface UserListResponse extends PaginatedResponse<User> {}

export interface AuthSession {
  id: string;
  ip_address: string | null;
  user_agent: string | null;
  expires_at: string;
  revoked_at: string | null;
  created_at: string;
  is_current: boolean;
}

// Discovery Provider types
export type DiscoveryProviderType = 'kubernetes' | 'vcenter' | 'nutanix';
export type DiscoveryProviderStatus = 'idle' | 'running' | 'success' | 'failed';

export interface KubernetesConfig {
  cluster_name: string;
  namespace: string | null;
  token: string | null;
  ca_cert: string | null;
}

export interface VCenterConfig {
  include_tags: boolean;
}

export interface NutanixConfig {}

export interface DiscoveryProvider {
  id: string;
  name: string;
  display_name: string | null;
  provider_type: DiscoveryProviderType;
  api_url: string;
  username: string | null;
  has_password: boolean;
  verify_ssl: boolean;
  timeout_seconds: number;
  is_enabled: boolean;
  priority: number;
  sync_interval_minutes: number;
  kubernetes_config: KubernetesConfig | null;
  vcenter_config: VCenterConfig | null;
  nutanix_config: NutanixConfig | null;
  status: DiscoveryProviderStatus;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  assets_discovered: number;
  applications_discovered: number;
  created_at: string;
  updated_at: string;
}

export interface DiscoveryProviderSummary {
  id: string;
  name: string;
  display_name: string | null;
  provider_type: DiscoveryProviderType;
  api_url: string;
  is_enabled: boolean;
  status: DiscoveryProviderStatus;
  last_success_at: string | null;
  assets_discovered: number;
}

export interface DiscoveryProviderListResponse {
  items: DiscoveryProviderSummary[];
  total: number;
}

export interface DiscoveryProviderCreate {
  name: string;
  display_name?: string;
  provider_type: DiscoveryProviderType;
  api_url: string;
  username?: string;
  password?: string;
  verify_ssl?: boolean;
  timeout_seconds?: number;
  is_enabled?: boolean;
  priority?: number;
  sync_interval_minutes?: number;
  kubernetes_config?: KubernetesConfig;
  vcenter_config?: VCenterConfig;
  nutanix_config?: NutanixConfig;
}

export interface DiscoveryProviderUpdate {
  name?: string;
  display_name?: string;
  api_url?: string;
  username?: string;
  password?: string;
  verify_ssl?: boolean;
  timeout_seconds?: number;
  is_enabled?: boolean;
  priority?: number;
  sync_interval_minutes?: number;
  kubernetes_config?: KubernetesConfig;
  vcenter_config?: VCenterConfig;
  nutanix_config?: NutanixConfig;
}

export interface ConnectionTestResponse {
  success: boolean;
  message: string;
  details: Record<string, unknown> | null;
}

export interface SyncTriggerResponse {
  success: boolean;
  message: string;
  provider_id: string;
}

// Segmentation Policy types
export type PolicyStance = 'allow_list' | 'deny_list';
export type PolicyStatus = 'draft' | 'pending_review' | 'approved' | 'active' | 'archived';
export type RuleType = 'inbound' | 'outbound' | 'internal';
export type RuleAction = 'allow' | 'deny';
export type SourceDestType = 'any' | 'app_member' | 'cidr' | 'asset';

export interface SegmentationPolicyRule {
  id: string;
  policy_id: string;
  rule_type: RuleType;
  source_type: SourceDestType;
  source_asset_id: string | null;
  source_cidr: string | null;
  source_app_id: string | null;
  source_label: string | null;
  dest_type: SourceDestType;
  dest_asset_id: string | null;
  dest_cidr: string | null;
  dest_app_id: string | null;
  dest_label: string | null;
  port: number | null;
  port_range_end: number | null;
  protocol: number;
  service_label: string | null;
  action: RuleAction;
  description: string | null;
  is_enabled: boolean;
  priority: number;
  rule_order: number;
  is_auto_generated: boolean;
  generated_from_dependency_id: string | null;
  generated_from_entry_point_id: string | null;
  bytes_observed: number | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SegmentationPolicyRuleSummary {
  id: string;
  rule_type: RuleType;
  source_label: string | null;
  dest_label: string | null;
  port: number | null;
  protocol: number;
  service_label: string | null;
  action: RuleAction;
  is_enabled: boolean;
  is_auto_generated: boolean;
}

export interface SegmentationPolicy {
  id: string;
  application_id: string;
  name: string;
  description: string | null;
  stance: PolicyStance;
  status: PolicyStatus;
  version: number;
  is_active: boolean;
  rule_count: number;
  inbound_rule_count: number;
  outbound_rule_count: number;
  internal_rule_count: number;
  generated_from_topology_at: string | null;
  generated_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SegmentationPolicySummary {
  id: string;
  application_id: string;
  name: string;
  stance: PolicyStance;
  status: PolicyStatus;
  version: number;
  is_active: boolean;
  rule_count: number;
  created_at: string;
}

export interface SegmentationPolicyWithRules extends SegmentationPolicy {
  rules: SegmentationPolicyRule[];
}

export interface SegmentationPolicyVersion {
  id: string;
  policy_id: string;
  version_number: number;
  version_label: string | null;
  stance: PolicyStance;
  status: PolicyStatus;
  rules_snapshot: Record<string, unknown>[];
  rules_added: number;
  rules_removed: number;
  rules_modified: number;
  created_by: string | null;
  change_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface RuleDiff {
  rule_id: string | null;
  change_type: 'added' | 'removed' | 'modified' | 'unchanged';
  rule_data: Record<string, unknown>;
  previous_data: Record<string, unknown> | null;
  changed_fields: string[] | null;
}

export interface PolicyComparisonResponse {
  policy_id: string;
  version_a: number | null;
  version_b: number | null;
  stance_changed: boolean;
  rules_added: RuleDiff[];
  rules_removed: RuleDiff[];
  rules_modified: RuleDiff[];
  rules_unchanged: RuleDiff[] | null;
  summary: string;
}

export interface FirewallRuleExport {
  rule_id: string;
  priority: number;
  action: RuleAction;
  source_cidr: string;
  dest_cidr: string;
  port: string;
  protocol: string;
  description: string;
  application_name: string;
  rule_type: RuleType;
  is_enabled: boolean;
}

export interface PolicyExportFormat {
  policy_name: string;
  application_name: string;
  stance: PolicyStance;
  version: number;
  exported_at: string;
  rule_count: number;
  rules: FirewallRuleExport[];
}

export interface PolicyGenerateRequest {
  application_id: string;
  stance?: PolicyStance;
  include_external_inbound?: boolean;
  include_internal_communication?: boolean;
  include_downstream_dependencies?: boolean;
  max_downstream_depth?: number;
  min_bytes_threshold?: number;
}

export interface PolicyRuleCreate {
  rule_type: RuleType;
  source_type: SourceDestType;
  source_asset_id?: string | null;
  source_cidr?: string | null;
  source_app_id?: string | null;
  source_label?: string | null;
  dest_type: SourceDestType;
  dest_asset_id?: string | null;
  dest_cidr?: string | null;
  dest_app_id?: string | null;
  dest_label?: string | null;
  port?: number | null;
  port_range_end?: number | null;
  protocol?: number;
  service_label?: string | null;
  action?: RuleAction;
  description?: string | null;
  is_enabled?: boolean;
  priority?: number;
}

export interface PolicyRuleUpdate {
  priority?: number;
  is_enabled?: boolean;
  description?: string | null;
  action?: RuleAction;
  source_label?: string | null;
  dest_label?: string | null;
  service_label?: string | null;
}

export interface PolicyCreate {
  name: string;
  application_id: string;
  description?: string | null;
  stance?: PolicyStance;
}

export interface PolicyUpdate {
  name?: string;
  description?: string | null;
  stance?: PolicyStance;
}

export interface PublishVersionRequest {
  version_label?: string | null;
  change_reason?: string | null;
}

export interface PolicyStatusUpdate {
  status: PolicyStatus;
  reason?: string | null;
}

export interface PolicyApprovalResponse {
  policy_id: string;
  status: PolicyStatus;
  approved_by: string | null;
  approved_at: string | null;
  message: string;
}

export interface SegmentationPolicyListResponse extends PaginatedResponse<SegmentationPolicySummary> {}

// =============================================================================
// Folder types (for arc-based topology)
// =============================================================================

export interface Folder {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  parent_id: string | null;
  color: string | null;
  icon: string | null;
  order: number;
  owner: string | null;
  team: string | null;
  tags: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface FolderSummary {
  id: string;
  name: string;
  display_name: string | null;
  color: string | null;
  icon: string | null;
  parent_id: string | null;
}

export interface FolderCreate {
  name: string;
  display_name?: string | null;
  description?: string | null;
  parent_id?: string | null;
  color?: string | null;
  icon?: string | null;
  order?: number;
  owner?: string | null;
  team?: string | null;
  tags?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
}

export interface FolderUpdate {
  name?: string;
  display_name?: string | null;
  description?: string | null;
  color?: string | null;
  icon?: string | null;
  order?: number;
  owner?: string | null;
  team?: string | null;
  tags?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
}

export interface FolderList {
  items: FolderSummary[];
  total: number;
}

export interface MoveFolderRequest {
  new_parent_id: string | null;
}

export interface FolderPath {
  path: FolderSummary[];
}

export interface ApplicationInFolder {
  id: string;
  name: string;
  display_name: string | null;
  environment: string | null;
  criticality: string | null;
  team: string | null;
}

export interface FolderTreeNode {
  id: string;
  name: string;
  display_name: string | null;
  color: string | null;
  icon: string | null;
  order: number;
  parent_id: string | null;
  team: string | null;
  children: FolderTreeNode[];
  applications: ApplicationInFolder[];
}

export interface FolderTree {
  roots: FolderTreeNode[];
  total_folders: number;
  total_applications: number;
}

// =============================================================================
// Arc Topology types
// =============================================================================

export type EdgeDirection = 'in' | 'out' | 'bi';

export interface ArcDependency {
  source_folder_id: string | null;
  source_app_id: string;
  source_app_name: string;
  target_folder_id: string | null;
  target_app_id: string;
  target_app_name: string;
  connection_count: number;
  bytes_total: number;
  bytes_last_24h: number;
  direction: EdgeDirection;
}

export interface FolderDependency {
  source_folder_id: string;
  source_folder_name: string;
  target_folder_id: string;
  target_folder_name: string;
  direction: EdgeDirection;
  connection_count: number;
  bytes_total: number;
  bytes_last_24h: number;
}

export interface ArcTopologyData {
  hierarchy: FolderTree;
  dependencies: ArcDependency[];
  folder_dependencies: FolderDependency[];
  statistics: {
    total_folders: number;
    total_applications: number;
    total_dependencies: number;
    total_folder_dependencies?: number;
  };
}

export interface MoveApplicationRequest {
  folder_id: string | null;
}

// Application Dependency Details (for details pane)
export interface ApplicationDependencySummary {
  counterparty_id: string;
  counterparty_name: string;
  counterparty_folder_id: string | null;
  counterparty_folder_name: string | null;
  direction: EdgeDirection;
  connection_count: number;
  bytes_total: number;
  bytes_last_24h: number;
  last_seen: string | null;
}

export interface ConnectionDetail {
  source_ip: string;
  destination_ip: string;
  destination_port: number;
  protocol: number;
  direction: EdgeDirection;
  bytes_total: number;
  bytes_last_24h: number;
  last_seen: string | null;
}

export interface ApplicationDependencyList {
  app_id: string;
  app_name: string;
  direction_filter: string;
  dependencies: ApplicationDependencySummary[];
  top_connections: ConnectionDetail[];
  total_connections: number;
  total_bytes: number;
  total_bytes_24h: number;
}

// Topology Exclusion types
export type ExclusionEntityType = 'folder' | 'application';

export interface TopologyExclusionCreate {
  entity_type: ExclusionEntityType;
  entity_id: string;
  reason?: string;
}

export interface TopologyExclusion {
  id: string;
  user_id: string;
  entity_type: ExclusionEntityType;
  entity_id: string;
  entity_name: string | null;
  reason: string | null;
  created_at: string;
}

export interface TopologyExclusionList {
  items: TopologyExclusion[];
  total: number;
}
