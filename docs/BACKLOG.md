# FlowLens Development Backlog

**Last Updated:** 2026-01-04

---

## Completed Features (MVP)

### Backend - Core Infrastructure
- [x] FastAPI application with async PostgreSQL
- [x] SQLAlchemy 2.0 models (assets, dependencies, services, changes, alerts)
- [x] Alembic database migrations
- [x] NetFlow/sFlow/IPFIX ingestion pipeline
- [x] Dependency resolution and graph building
- [x] CIDR-based IP classification rules

### Backend - Change Detection & Alerting
- [x] Change detection engine with all 13 ChangeType events:
  - DEPENDENCY_CREATED, DEPENDENCY_REMOVED, DEPENDENCY_STALE
  - DEPENDENCY_TRAFFIC_SPIKE, DEPENDENCY_TRAFFIC_DROP
  - ASSET_DISCOVERED, ASSET_REMOVED, ASSET_OFFLINE, ASSET_ONLINE
  - SERVICE_DISCOVERED, SERVICE_REMOVED
  - NEW_EXTERNAL_CONNECTION, CRITICAL_PATH_CHANGE
- [x] Auto-notification dispatch from alerts
- [x] Email notification channel
- [x] Webhook notification channel (HMAC-SHA256 signed)

### Backend - WebSocket Real-time Updates
- [x] WebSocket connection manager
- [x] Broadcast helpers for change events and alerts
- [x] Alert acknowledge/resolve broadcasts

### Backend - Analysis APIs
- [x] Blast radius calculation (`GET /analysis/blast-radius/{id}`)
- [x] Impact analysis (`POST /analysis/impact`)
- [x] SPOF detection (`GET /analysis/spof`)
- [x] Critical paths (`GET /analysis/critical-paths/{id}`)
- [x] Path finding between assets (`GET /topology/path`) - bidirectional search
- [x] Subgraph extraction (`POST /topology/subgraph`)
- [x] Upstream/downstream traversal

### Frontend - Core UI
- [x] React + TypeScript + Vite application
- [x] TailwindCSS styling with dark theme
- [x] React Query for data fetching
- [x] Responsive layout with sidebar navigation

### Frontend - Pages
- [x] Dashboard with stats overview
- [x] Assets list with search/filter
- [x] Asset detail with dependencies and blast radius
- [x] Topology visualization (D3.js force-directed graph)
- [x] Alerts list with acknowledge/resolve actions
- [x] Changes feed
- [x] Classification rules management
- [x] Saved views management
- [x] Analysis page with tabs:
  - SPOF detection display
  - Blast radius topology visualization (D3.js with hop slider 1-5)
  - Path finder between assets

### Frontend - Real-time Features
- [x] WebSocket connection with auto-reconnect
- [x] React Query cache invalidation on events
- [x] Toast notifications for new alerts
- [x] Connection status indicator in header

---

## Completed Features (Post-MVP)

### Alert Rules Engine
- [x] **AlertRule model** - Configurable rules with change type triggers, asset filters, templates
- [x] **Alert rules API** - Full CRUD with toggle, test endpoints
- [x] **Alert rules UI** - Management page with create/edit modal, enable/disable toggle
- [x] **Default rules migration** - 5 pre-configured rules for common scenarios

### Maintenance Windows
- [x] **MaintenanceWindow model** - Schedule with asset/environment/datacenter scope
- [x] **Maintenance API** - CRUD, active windows, asset check endpoints
- [x] **Maintenance UI** - Scheduling modal, active window alerts, cancel functionality
- [x] **PostgreSQL functions** - `is_asset_in_maintenance()`, `get_active_maintenance_windows()`

### Notification Channels
- [x] **Slack integration** - Block Kit formatting with priority colors/emojis
- [x] **Microsoft Teams integration** - Adaptive Cards with FactSet metadata
- [x] **PagerDuty integration** - Events API v2 with dedup, acknowledge, resolve

### Topology Enhancements
- [x] **Historical topology** - `as_of` parameter for point-in-time views
- [x] **Topology filtering panel** - Filter by environment, datacenter, asset type
- [x] **Filter URL sync** - Shareable filtered views via URL parameters
- [x] **PNG/SVG export** - Canvas-based topology image export

### Bulk Operations
- [x] **Bulk asset update API** - `PATCH /assets/bulk` for environment, datacenter, critical
- [x] **Bulk asset delete API** - `DELETE /assets/bulk` with soft delete
- [x] **Bulk operations UI** - Multi-select with action toolbar

### Asset Auto-Classification
- [x] **Classification engine** - Behavioral feature extraction from flow data
- [x] **Scoring engine** - Rule-based scoring with confidence thresholds
- [x] **Classification worker** - Background service for auto-classification
- [x] **Asset feature extraction** - Fan-in/out, port patterns, protocol distribution
- [x] **Classification history** - Audit trail for type changes
- [x] **CIDR classification rules** - Environment/datacenter/location by IP range

### Gateway Detection
- [x] **Gateway observation model** - Intermediate observations from next_hop field
- [x] **Asset gateway model** - Inferred gateway relationships with confidence
- [x] **Gateway inference service** - Roll up observations to asset relationships
- [x] **Gateway API endpoints** - List gateways, for-asset, clients, topology
- [x] **Gateway UI integration** - Gateways tab on asset detail page

### Topology Enhancements
- [x] **Group by type** - Group topology nodes by asset type
- [x] **Hierarchical blast radius** - Nodes arranged by hop distance

### Background Task System
- [x] **BackgroundTask model** - Track async operations with progress, status, timing
- [x] **Task executor service** - Background task execution with own database sessions
- [x] **Classification task** - Batch processing of CIDR rule application
- [x] **Tasks API** - List, status, cancel endpoints (`GET /tasks`, `POST /tasks/{id}/cancel`)
- [x] **Tasks UI page** - Progress bars, status badges, cancel/delete actions with polling
- [x] **Auto-trigger on rule changes** - Classification tasks auto-triggered on rule create/update

### Environment Enum Constraint
- [x] **Environment enum** - Fixed dropdown values: prod, uat, qa, test, dev
- [x] **Schema updates** - AssetBase, AssetUpdate, ClassificationRuleBase, ClassificationRuleUpdate
- [x] **Frontend dropdowns** - Environment selection in ClassificationRules and AssetDetail pages
- [x] **TypeScript types** - ENVIRONMENT_OPTIONS array with labels

### Database Improvements
- [x] **BigInteger migrations** - All byte/packet/flow counters use BIGINT
- [x] **Timezone-aware datetimes** - All timestamp columns properly typed

### Testing Infrastructure
- [x] **Comprehensive pytest test suite** - 281 unit tests + 76 integration tests (357 total)
  - Unit tests for: scoring engine, heuristics, classification constants, gateway inference, change detector, flow aggregator, backpressure queue, NetFlow v5 parser, rate limiting, caching, alert rule evaluator, dependency builder, classification import/export
  - Integration tests for: assets, dependencies, topology, alerts, changes, classification, gateways, maintenance windows APIs
  - Test fixtures in conftest.py for classification, gateway, and change detection scenarios
  - Markers for unit/integration/slow test categorization

### API Performance & Security
- [x] **Rate limiting middleware** - Sliding window rate limiter with configurable limits per client
  - Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After
  - Configurable via API_RATE_LIMIT_ENABLED, API_RATE_LIMIT_REQUESTS, API_RATE_LIMIT_WINDOW_SECONDS
  - EndpointRateLimiter for stricter per-endpoint limits on sensitive operations
- [x] **Topology query optimization** - Performance improvements for large graphs (>10k nodes)
  - Composite indexes for topology filters (asset_type, is_internal, deleted_at)
  - GiST index for CIDR containment queries
  - Optimized graph traversal functions with result limits
  - In-memory cache with configurable TTL (API_TOPOLOGY_CACHE_TTL_SECONDS)
  - Node/edge limits (API_TOPOLOGY_MAX_NODES, API_TOPOLOGY_MAX_EDGES)

---

## In Progress

*Nothing currently in progress*

---

## Completed Features (Recent)

### Authentication & Authorization
- [x] **JWT Authentication** - Access and refresh token-based authentication
- [x] **Role-Based Access Control (RBAC)** - Admin, Analyst, Viewer roles
- [x] **User Management** - Local user accounts with password hashing
- [x] **SAML Integration** - SSO support for Azure AD, Okta, Ping Identity
- [x] **Auth Audit Logging** - Track login, logout, password changes, account locks
- [x] **Session Management** - Refresh token tracking and revocation
- [x] **Account Security** - Failed login tracking, account locking
- [x] **Setup Flow** - First-run admin user creation

### Application Grouping
- [x] **Application model** - Logical groupings of related assets
- [x] **Application members** - Assets with roles (frontend, backend, database, cache, etc.)
- [x] **Multiple entry points** - Each member can have multiple port/protocol entry points
- [x] **Application API** - Full CRUD for applications and members
- [x] **Application UI** - Management page with create/edit modal, member management
- [x] **Application topology** - Filter topology by application

### Import/Export Functionality
- [x] **Classification rules export** - JSON export of all CIDR classification rules
- [x] **Classification rules import** - Validate and import rules with preview
- [x] **Application export** - JSON export with member IP addresses and entry points
- [x] **Application import** - Validate assets exist, preview changes, import
- [x] **Frontend UI** - Import/export buttons on Classification Rules and Applications pages

### Topology Enhancements
- [x] **Edge service labels** - Show service names (HTTP, SSH, MySQL) on dependency edges
- [x] **Ephemeral port filtering** - Only show known services, not ephemeral ports
- [x] **Overlapping label handling** - Curved edge labels positioned correctly
- [x] **Multiple entry point connections** - Edges connect to correct entry point positions
- [x] **Comprehensive PORT_SERVICES mapping** - Extensive service-to-port mappings

### Dependency Filtering
- [x] **Discard external flows option** - Filter out non-internal traffic at ingestion
- [x] **External source/target filtering** - Configurable exclusion of external dependencies
- [x] **Settings propagation** - Filters properly applied to DependencyBuilder
- [x] **Filtering tests** - Unit tests for dependency builder filtering

### Alert Rule Evaluation Engine
- [x] **AlertRuleEvaluator service** - Evaluates change events against configured alert rules
- [x] **Rule matching** - Change type matching, asset filter evaluation, cooldown periods
- [x] **Template rendering** - Dynamic title and description from rule templates
- [x] **Maintenance window integration** - Suppresses alerts during scheduled maintenance
- [x] **Notification channel routing** - Uses rule-specified channels or severity-based defaults
- [x] **All notification channels registered** - Email, Webhook, Slack, Teams, PagerDuty
- [x] **Schedule support** - Rules can be limited to specific days/hours
- [x] **Unit tests** - 35 tests for alert rule evaluation

---

## Backlog - High Priority

### Backend Enhancements
- [ ] **Scheduled discovery scans** - Periodic re-discovery of assets via SSH/WMI/SNMP

### Frontend Enhancements
- [ ] **Recurring maintenance UI** - UI for recurring schedules (model supports it)

### API & Integration
- [ ] **GraphQL API** - For complex nested queries

---

## Backlog - Medium Priority

### Backend
- [ ] **Kubernetes discovery** - K8s API-based workload and service discovery
- [ ] **Cloud provider integrations** - AWS EC2/VPC, Azure VMs, GCP Compute discovery
- [ ] **Protocol inference ML** - Classify application protocols beyond port heuristics
- [ ] **Traffic anomaly detection ML** - Statistical analysis of traffic patterns

### Frontend
- [x] ~~**Application grouping** - Group assets into logical applications~~ *(Completed 2025-12-30)*
- [ ] **Compliance reporting** - Pre-built report templates
- [ ] **PDF report generation** - Export analysis results as PDFs
- [ ] **Keyboard shortcuts** - Power user navigation

### Security & Enterprise
- [x] ~~**SSO integration** - SAML/OIDC authentication~~ *(Completed 2025-12-29)*
- [ ] **Multi-tenancy** - Separate data by organization/tenant
- [ ] **Audit log export** - SIEM integration for audit events

---

## Backlog - Low Priority / Future

### Backend
- [ ] **ServiceNow CMDB sync** - Bidirectional asset sync
- [ ] **What-if scenario modeling** - Simulate asset removal impact
- [ ] **Custom discovery plugins** - Plugin architecture for proprietary systems
- [ ] **Credential vault integration** - HashiCorp Vault, AWS Secrets Manager

### Frontend
- [ ] **Visio export** - Export topology to Microsoft Visio format
- [ ] **Custom dashboards** - User-defined dashboard widgets
- [ ] **Dark/light theme toggle** - Currently dark-only

### Deployment
- [ ] **OVA appliance** - VM image for easy deployment
- [ ] **Helm chart** - Kubernetes deployment package
- [ ] **Air-gap support** - Offline deployment capability

---

## Out of Scope (by design)

These features are explicitly excluded from FlowLens scope:

| Feature | Reason | Alternative |
|---------|--------|-------------|
| CVE Detection | Requires agent-based software inventory | Integrate with Nessus, Qualys, Trivy |
| SSL Certificate Monitoring | Requires TLS handshake inspection | Use cert-manager, Venafi |
| VM Right-sizing | Requires hypervisor performance metrics | Use CloudWatch, Prometheus |
| APM/Performance Metrics | Different domain (observability vs. dependency mapping) | Use Datadog, New Relic |
| Deep Packet Inspection | Privacy/performance concerns | Port-based protocol inference |
| Automated Remediation | Requires change approval workflows | Out of scope |
| Code-level Dependencies | Static analysis domain | Use SBOM tools |

---

## Bug Fixes Applied

### Session 2026-01-04
- [x] Fixed classification rules import/export is_internal handling - proper boolean handling in task execution
- [x] Fixed settings propagation to DependencyBuilder - external flow filtering now applies correctly
- [x] Fixed topology edge labels - only show known services, filter ephemeral ports (>32767)
- [x] Fixed overlapping edge labels - curved edges now position labels correctly
- [x] Fixed edge connections for multiple entry points - edges connect to correct entry point positions on assets
- [x] Fixed asset IP validation during application import - proper validation before import
- [x] Fixed 401 error when exporting applications and classification rules - authentication token handling
- [x] Fixed duplicate /api/v1 path in export URLs - corrected API path construction
- [x] Fixed PostgreSQL advisory lock deadlock in asset creation - lock ordering
- [x] Fixed external asset creation in enrichment service - proper handling of non-internal IPs
- [x] Added uv.lock for dependency reproducibility

### Session 2025-12-28
- [x] Fixed PATCH /assets endpoint 500 error - manual AssetResponse construction instead of model_validate
- [x] Fixed metadata field mapping - `extra_data` ORM attribute to `metadata` API field
- [x] Fixed Environment enum validation - added field_validator to convert empty string to None
- [x] Fixed classification rule updates not applying - force=True when rules are updated
- [x] Fixed classification confidence formula - more generous scoring allows more auto-classifications
- [x] Fixed classification task session error - new database session for background tasks

### Session 2025-12-27
- [x] Fixed topology "Group by Type" - changed `node.type` to `node.asset_type` to match backend schema
- [x] Fixed classification worker timezone errors - `datetime.utcnow()` to `datetime.now(timezone.utc)`
- [x] Fixed feature extractor IP address comparison - append `/32` suffix for INET matching
- [x] Fixed gateway inference Decimal * float error - explicit float() conversion
- [x] Fixed enrichment duplicate key race condition - IntegrityError handling with rollback
- [x] Fixed asset model DateTime columns - added `timezone=True` for first_seen, last_seen, last_classified_at
- [x] Fixed gateway model DateTime columns - added `timezone=True` for first_seen, last_seen, last_inferred_at
- [x] Fixed docker-compose.yml duplicate YAML merge keys - combined environment anchors

### Previous Sessions
- [x] Fixed SPOF query `asyncpg` NULL parameter error - dynamic query building
- [x] Fixed `ChangeEventResponse.metadata` validation - `validation_alias` for SQLAlchemy attribute mapping
- [x] Fixed Path Finder API endpoint - changed from `/analysis/path` to `/topology/path`
- [x] Fixed Path Finder bidirectional search - treats dependencies as undirected for path finding
- [x] Fixed Path Finder multiple dependencies - `.limit(1)` for assets with multiple connections

---

## Technical Debt

- [x] Add comprehensive test suite (pytest) - **Completed 2025-12-27**
- [x] Add API rate limiting - **Completed 2025-12-27**
- [x] Optimize topology queries for large graphs (>10k nodes) - **Completed 2025-12-27**
- [ ] Add request validation error handling improvements
- [ ] Add database connection pooling configuration
- [ ] Add structured logging to all services

---

## Environment Variables (New Features)

### Authentication
```bash
AUTH_ENABLED=true                           # Enable/disable authentication (default: true)
AUTH_SECRET_KEY=your-secret-key             # JWT signing key (CHANGE IN PRODUCTION!)
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30         # Access token lifetime (default: 30)
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7            # Refresh token lifetime (default: 7)
AUTH_MAX_FAILED_ATTEMPTS=5                  # Failed logins before lockout (default: 5)
AUTH_LOCKOUT_MINUTES=15                     # Lockout duration (default: 15)
```

### SAML SSO
```bash
SAML_ENABLED=true                           # Enable SAML authentication
SAML_SP_ENTITY_ID=flowlens                  # Service Provider entity ID
SAML_SP_ACS_URL=https://flowlens.example.com/api/v1/auth/saml/acs
SAML_DEFAULT_ROLE=viewer                    # Default role for new SAML users
```

### Slack Notifications
```bash
SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
SLACK_DEFAULT_CHANNEL=#alerts
SLACK_USERNAME=FlowLens
SLACK_ICON_EMOJI=:bell:
```

### Microsoft Teams Notifications
```bash
TEAMS_ENABLED=true
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxx
```

### PagerDuty Notifications
```bash
PAGERDUTY_ENABLED=true
PAGERDUTY_ROUTING_KEY=your-integration-key
PAGERDUTY_SERVICE_NAME=FlowLens
```

### API Rate Limiting
```bash
API_RATE_LIMIT_ENABLED=true       # Enable/disable rate limiting (default: true)
API_RATE_LIMIT_REQUESTS=100       # Max requests per window per client (default: 100)
API_RATE_LIMIT_WINDOW_SECONDS=60  # Rate limit window in seconds (default: 60)
```

### Topology Query Performance
```bash
API_TOPOLOGY_MAX_NODES=5000          # Max nodes in topology response (default: 5000)
API_TOPOLOGY_MAX_EDGES=10000         # Max edges in topology response (default: 10000)
API_TOPOLOGY_CACHE_TTL_SECONDS=30    # Cache TTL for topology queries (default: 30, 0 to disable)
```

### Dependency Filtering
```bash
RESOLUTION_EXCLUDE_EXTERNAL_IPS=false       # Exclude non-private IPs from dependencies
RESOLUTION_EXCLUDE_EXTERNAL_SOURCES=false   # Exclude dependencies with external sources
RESOLUTION_EXCLUDE_EXTERNAL_TARGETS=false   # Exclude dependencies with external targets
INGESTION_DISCARD_EXTERNAL_FLOWS=true       # Discard flows with external IPs at ingestion (default: true)
```

---

*Document maintained by: Engineering Team*
