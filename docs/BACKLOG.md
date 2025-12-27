# FlowLens Development Backlog

**Last Updated:** 2025-12-27

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

### Database Improvements
- [x] **BigInteger migrations** - All byte/packet/flow counters use BIGINT
- [x] **Timezone-aware datetimes** - All timestamp columns properly typed

### Testing Infrastructure
- [x] **Comprehensive pytest test suite** - 219 unit tests + 74 integration tests
  - Unit tests for: scoring engine, heuristics, classification constants, gateway inference, change detector, flow aggregator, backpressure queue, NetFlow v5 parser, rate limiting, caching
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

## Backlog - High Priority

### Backend Enhancements
- [ ] **Scheduled discovery scans** - Periodic re-discovery of assets via SSH/WMI/SNMP
- [ ] **Alert rule evaluation** - Wire rules to change_detector for dynamic alerting

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
- [ ] **Application grouping** - Group assets into logical applications
- [ ] **Compliance reporting** - Pre-built report templates
- [ ] **PDF report generation** - Export analysis results as PDFs
- [ ] **Keyboard shortcuts** - Power user navigation

### Security & Enterprise
- [ ] **SSO integration** - SAML/OIDC authentication
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

---

*Document maintained by: Engineering Team*
