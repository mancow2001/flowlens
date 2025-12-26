# FlowLens Development Backlog

**Last Updated:** 2024-12-26

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

## In Progress

*Nothing currently in progress*

---

## Backlog - High Priority

### Backend Enhancements
- [ ] **Historical topology time-slider** - Query topology at a specific point in time using `as_of` parameter
- [ ] **Scheduled discovery scans** - Periodic re-discovery of assets via SSH/WMI/SNMP
- [ ] **Alert rules engine** - Configurable rules for when to generate alerts (beyond default change detection)
- [ ] **Maintenance windows** - Suppress alerts during scheduled maintenance periods

### Frontend Enhancements
- [ ] **Topology filtering panel** - Filter by environment, datacenter, asset type in topology view
- [ ] **Historical topology playback** - Time-slider to view topology at past timestamps
- [ ] **Bulk asset operations** - Select multiple assets for bulk tagging, classification
- [ ] **Export topology as image** - PNG/SVG export of current topology view

### API & Integration
- [ ] **GraphQL API** - For complex nested queries
- [ ] **Slack/Teams notifications** - Direct integration (currently webhook only)
- [ ] **PagerDuty integration** - Native Events API v2 support

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

## Bug Fixes Applied (This Session)

- [x] Fixed SPOF query `asyncpg` NULL parameter error - dynamic query building
- [x] Fixed `ChangeEventResponse.metadata` validation - `validation_alias` for SQLAlchemy attribute mapping
- [x] Fixed Path Finder API endpoint - changed from `/analysis/path` to `/topology/path`
- [x] Fixed Path Finder bidirectional search - treats dependencies as undirected for path finding
- [x] Fixed Path Finder multiple dependencies - `.limit(1)` for assets with multiple connections

---

## Technical Debt

- [ ] Add comprehensive test suite (pytest)
- [ ] Add API rate limiting
- [ ] Add request validation error handling improvements
- [ ] Optimize topology queries for large graphs (>10k nodes)
- [ ] Add database connection pooling configuration
- [ ] Add structured logging to all services

---

*Document maintained by: Engineering Team*
