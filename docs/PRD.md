# FlowLens - Application Dependency Mapping Platform
## Product Requirements Document (PRD)

**Version:** 1.0
**Date:** 2024-12-24
**Status:** Draft

---

## 1. Executive Summary

FlowLens is a Python-based Application Dependency Mapping (ADM) platform designed to automatically discover, visualize, and track dependencies between applications, services, and infrastructure components within enterprise environments. Comparable to Faddom, FlowLens provides agentless discovery capabilities with a focus on simplicity, accuracy, and actionable insights.

---

## 2. Core Personas

### 2.1 Infrastructure Engineer (Primary)
**Name:** Alex Chen
**Role:** Senior Infrastructure Engineer
**Goals:**
- Understand application-to-infrastructure relationships
- Plan infrastructure changes without causing outages
- Identify single points of failure
- Capacity planning and resource optimization

**Pain Points:**
- Outdated or non-existent documentation
- Surprise dependencies discovered during incidents
- Manual dependency tracking is error-prone and time-consuming

**Usage Pattern:** Daily monitoring, weekly deep-dives, ad-hoc queries during change management

### 2.2 Platform/DevOps Engineer
**Name:** Jordan Martinez
**Role:** Platform Engineer
**Goals:**
- Automate discovery of service dependencies
- Maintain accurate service catalogs
- Support CI/CD pipeline planning
- Enable self-service for development teams

**Pain Points:**
- Microservices sprawl makes tracking dependencies difficult
- Teams deploy services without updating documentation
- Lack of visibility into cross-team dependencies

**Usage Pattern:** Integration with CI/CD pipelines, weekly reviews, on-demand queries

### 2.3 Security Analyst
**Name:** Sam Williams
**Role:** Security Operations Analyst
**Goals:**
- Identify attack surface and blast radius
- Understand data flow paths for compliance
- Detect shadow IT and unauthorized services
- Support incident response with dependency context

**Pain Points:**
- Cannot quickly determine impact scope during incidents
- Compliance audits require manual dependency mapping
- Unknown services pose security risks

**Usage Pattern:** Security assessments, incident response, compliance audits

### 2.4 IT Operations Manager
**Name:** Morgan Taylor
**Role:** IT Operations Manager
**Goals:**
- Maintain accurate CMDB data
- Plan change windows with confidence
- Report on infrastructure complexity
- Reduce mean time to resolution (MTTR)

**Pain Points:**
- CMDB data is stale within weeks of updates
- Change advisory board lacks accurate impact data
- Difficult to quantify technical debt

**Usage Pattern:** Executive reporting, change management meetings, strategic planning

### 2.5 Application Owner / Product Manager
**Name:** Riley Johnson
**Role:** Product Manager
**Goals:**
- Understand full stack supporting their application
- Plan migrations and modernization efforts
- Identify shared dependencies with other teams

**Pain Points:**
- Lacks visibility into infrastructure supporting their app
- Surprised by downstream impacts of changes
- Cannot accurately scope migration projects

**Usage Pattern:** Quarterly planning, migration projects, ad-hoc queries

---

## 3. Primary Workflows

### 3.1 Initial Discovery Setup
**Trigger:** New environment onboarding
**Actor:** Infrastructure Engineer
**Flow:**
1. Configure network scan ranges (CIDR blocks)
2. Provide credentials for agentless discovery (SSH, WMI, SNMP, API keys)
3. Configure discovery schedules (continuous, periodic, one-time)
4. Initiate baseline discovery scan
5. Review discovered assets and connections
6. Validate and approve discovered topology
7. Configure alerts for topology changes

**Outcome:** Complete dependency map of target environment

### 3.2 Continuous Monitoring
**Trigger:** Scheduled interval or real-time event
**Actor:** System (automated)
**Flow:**
1. Execute periodic discovery scans
2. Compare current state against baseline
3. Detect new, modified, or removed dependencies
4. Classify changes (expected vs. unexpected)
5. Generate change notifications
6. Update dependency database
7. Refresh visualization cache

**Outcome:** Up-to-date dependency map with change history

### 3.3 Impact Analysis
**Trigger:** Planned change or incident
**Actor:** Infrastructure Engineer, Security Analyst
**Flow:**
1. Select target asset(s) for analysis
2. Choose analysis type (upstream, downstream, full blast radius)
3. Configure analysis depth (hops)
4. Execute dependency traversal
5. Generate impact report with affected assets
6. Export results for change management or incident response
7. Optionally create maintenance window associations

**Outcome:** Comprehensive list of potentially affected systems

### 3.4 Application Stack Mapping
**Trigger:** Migration planning, compliance audit
**Actor:** Application Owner, Security Analyst
**Flow:**
1. Identify entry point (application name, IP, hostname)
2. Discover full application stack (web → app → database → storage)
3. Map external dependencies (APIs, SaaS integrations)
4. Document data flows
5. Generate application topology diagram
6. Export documentation for stakeholders

**Outcome:** Complete application architecture documentation

### 3.5 Anomaly Investigation
**Trigger:** Alert on unexpected dependency
**Actor:** Security Analyst, Infrastructure Engineer
**Flow:**
1. Receive alert on new/changed dependency
2. Review connection details (source, destination, protocol, port)
3. Investigate historical context (when first seen, frequency)
4. Correlate with known change requests
5. Classify as legitimate or suspicious
6. Take action (approve, investigate further, remediate)
7. Update baseline if legitimate

**Outcome:** Resolved anomaly with documented decision

### 3.6 Reporting and Export
**Trigger:** Scheduled or ad-hoc request
**Actor:** IT Operations Manager, Security Analyst
**Flow:**
1. Select report type (inventory, dependencies, changes, compliance)
2. Configure filters (time range, asset groups, dependency types)
3. Choose output format (PDF, CSV, JSON, API)
4. Generate report
5. Distribute to stakeholders or integrate with external systems

**Outcome:** Actionable reports for decision-making

---

## 4. Functional Requirements

### 4.1 Asset Discovery

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-AD-001 | System SHALL discover assets via network scanning (TCP/UDP port scanning) | P0 |
| FR-AD-002 | System SHALL discover assets via agentless protocols (SSH, WMI, SNMP v2/v3) | P0 |
| FR-AD-003 | System SHALL discover cloud assets via provider APIs (AWS, Azure, GCP) | P1 |
| FR-AD-004 | System SHALL discover container workloads (Docker, Kubernetes) | P1 |
| FR-AD-005 | System SHALL support credential vault integration (HashiCorp Vault, AWS Secrets Manager) | P1 |
| FR-AD-006 | System SHALL deduplicate assets across multiple discovery sources | P0 |
| FR-AD-007 | System SHALL classify assets by type (server, VM, container, database, load balancer, etc.) | P0 |
| FR-AD-008 | System SHALL extract OS and software inventory from discovered assets | P1 |
| FR-AD-009 | System SHALL support custom discovery plugins for proprietary systems | P2 |

### 4.2 Dependency Mapping

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-DM-001 | System SHALL discover network connections via flow analysis (NetFlow, sFlow, IPFIX) | P0 |
| FR-DM-002 | System SHALL discover connections via packet capture (span port, TAP) | P1 |
| FR-DM-003 | System SHALL discover connections via host-level process/socket inspection | P0 |
| FR-DM-004 | System SHALL identify application protocols (HTTP, HTTPS, SQL, Redis, Kafka, etc.) | P1 |
| FR-DM-005 | System SHALL map dependencies at service level (not just IP:port) | P0 |
| FR-DM-006 | System SHALL support manual dependency declaration via API or UI | P0 |
| FR-DM-007 | System SHALL maintain historical dependency data with timestamps | P0 |
| FR-DM-008 | System SHALL detect bidirectional vs. unidirectional dependencies | P1 |
| FR-DM-009 | System SHALL support dependency tagging and classification | P1 |

### 4.3 Visualization

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-VZ-001 | System SHALL provide interactive topology map with zoom/pan | P0 |
| FR-VZ-002 | System SHALL support hierarchical grouping (by application, environment, location) | P0 |
| FR-VZ-003 | System SHALL highlight dependency paths between selected nodes | P0 |
| FR-VZ-004 | System SHALL display connection metadata on hover/click | P0 |
| FR-VZ-005 | System SHALL support filtering by asset type, tag, environment | P0 |
| FR-VZ-006 | System SHALL provide time-slider for historical topology views | P1 |
| FR-VZ-007 | System SHALL export topology diagrams (PNG, SVG, Visio) | P1 |
| FR-VZ-008 | System SHALL support saved views and dashboards | P1 |

### 4.4 Change Detection and Alerting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CD-001 | System SHALL detect new assets appearing in the environment | P0 |
| FR-CD-002 | System SHALL detect new dependencies between assets | P0 |
| FR-CD-003 | System SHALL detect removed assets and dependencies | P0 |
| FR-CD-004 | System SHALL detect changes in asset attributes (IP, hostname, ports) | P1 |
| FR-CD-005 | System SHALL support configurable alert thresholds and rules | P0 |
| FR-CD-006 | System SHALL integrate with notification systems (email, Slack, PagerDuty, webhooks) | P0 |
| FR-CD-007 | System SHALL provide alert suppression during maintenance windows | P1 |
| FR-CD-008 | System SHALL track alert acknowledgment and resolution | P1 |

### 4.5 Impact Analysis

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-IA-001 | System SHALL calculate upstream dependencies (what does X depend on) | P0 |
| FR-IA-002 | System SHALL calculate downstream dependencies (what depends on X) | P0 |
| FR-IA-003 | System SHALL support configurable traversal depth | P0 |
| FR-IA-004 | System SHALL generate impact reports exportable to common formats | P0 |
| FR-IA-005 | System SHALL estimate blast radius for failures | P1 |
| FR-IA-006 | System SHALL identify single points of failure | P1 |
| FR-IA-007 | System SHALL support what-if scenario modeling | P2 |

### 4.6 Integration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-IN-001 | System SHALL provide RESTful API for all major functions | P0 |
| FR-IN-002 | System SHALL support CMDB integration (ServiceNow, BMC) | P1 |
| FR-IN-003 | System SHALL support ITSM integration for change management | P1 |
| FR-IN-004 | System SHALL provide webhook endpoints for external triggers | P0 |
| FR-IN-005 | System SHALL support SSO authentication (SAML, OIDC) | P1 |
| FR-IN-006 | System SHALL provide GraphQL API for complex queries | P2 |
| FR-IN-007 | System SHALL support data export to SIEM systems | P1 |

### 4.7 Administration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-AM-001 | System SHALL support role-based access control (RBAC) | P0 |
| FR-AM-002 | System SHALL provide audit logging of all user and system actions | P0 |
| FR-AM-003 | System SHALL support multi-tenancy with data isolation | P1 |
| FR-AM-004 | System SHALL provide system health monitoring dashboard | P0 |
| FR-AM-005 | System SHALL support scheduled maintenance operations | P1 |
| FR-AM-006 | System SHALL provide data retention policy configuration | P1 |

---

## 5. Non-Functional Requirements

### 5.1 Throughput

| ID | Requirement | Target | Measurement |
|----|-------------|--------|-------------|
| NFR-TH-001 | Discovery scan throughput | ≥ 1,000 assets/minute | Assets discovered per minute during active scan |
| NFR-TH-002 | Flow data ingestion rate | ≥ 100,000 flows/second | NetFlow/sFlow records processed per second |
| NFR-TH-003 | Concurrent API requests | ≥ 500 requests/second | Sustained API request handling |
| NFR-TH-004 | Dependency graph updates | ≥ 10,000 edges/second | Dependency relationship updates processed |
| NFR-TH-005 | Report generation | ≤ 30 seconds for 10,000 assets | Time to generate comprehensive report |

### 5.2 Latency

| ID | Requirement | Target | P99 Target |
|----|-------------|--------|------------|
| NFR-LT-001 | API query response (simple) | ≤ 100ms | ≤ 250ms |
| NFR-LT-002 | API query response (complex graph traversal) | ≤ 500ms | ≤ 2s |
| NFR-LT-003 | Topology visualization load | ≤ 2s for 1,000 nodes | ≤ 5s |
| NFR-LT-004 | Impact analysis (3-hop) | ≤ 1s | ≤ 3s |
| NFR-LT-005 | Search results | ≤ 200ms | ≤ 500ms |
| NFR-LT-006 | Change detection latency | ≤ 5 minutes | ≤ 15 minutes |
| NFR-LT-007 | Alert notification delivery | ≤ 30 seconds from detection | ≤ 60 seconds |

### 5.3 Durability and Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-DR-001 | Data durability | 99.999% (five nines) |
| NFR-DR-002 | System availability | 99.9% uptime (8.76 hours downtime/year) |
| NFR-DR-003 | Recovery Point Objective (RPO) | ≤ 1 hour |
| NFR-DR-004 | Recovery Time Objective (RTO) | ≤ 4 hours |
| NFR-DR-005 | Data retention (raw flows) | 30 days configurable |
| NFR-DR-006 | Data retention (aggregated dependencies) | 2 years minimum |
| NFR-DR-007 | Backup frequency | Daily full, hourly incremental |
| NFR-DR-008 | Transaction consistency | ACID compliance for all writes |

### 5.4 Scalability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-SC-001 | Maximum assets | 100,000 discovered assets |
| NFR-SC-002 | Maximum dependencies | 10,000,000 dependency edges |
| NFR-SC-003 | Maximum concurrent users | 500 users |
| NFR-SC-004 | Horizontal scaling | Support for 3+ application nodes |
| NFR-SC-005 | Data growth | Support 50GB/month raw data ingestion |

### 5.5 Security

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-SE-001 | Data encryption at rest | AES-256 |
| NFR-SE-002 | Data encryption in transit | TLS 1.3 |
| NFR-SE-003 | Credential storage | Encrypted with HSM-backed keys |
| NFR-SE-004 | Session management | Secure tokens with configurable expiry |
| NFR-SE-005 | Vulnerability scanning | Zero critical/high vulnerabilities in production |
| NFR-SE-006 | Compliance | SOC 2 Type II compatible controls |

---

## 6. Technology Stack Decisions

### 6.1 Core Stack (Required)

| Component | Technology | Justification |
|-----------|------------|---------------|
| **Backend Language** | Python 3.11+ | Constraint requirement; rich ecosystem for network analysis, async support |
| **Web Framework** | FastAPI | High performance async, automatic OpenAPI docs, Pydantic validation |
| **Primary Database** | PostgreSQL 15+ | Constraint requirement; ACID compliance, JSON support, proven reliability |
| **ORM** | SQLAlchemy 2.0 | Mature, async support, excellent PostgreSQL integration |
| **Task Queue** | Celery | Distributed task execution for discovery scans, Python-native |
| **API Documentation** | OpenAPI 3.0 | Auto-generated via FastAPI |

### 6.2 Kafka Decision: JUSTIFIED FOR USE

**Decision:** Include Kafka for flow data ingestion pipeline

**Justification:**
1. **Volume:** NFR-TH-002 requires 100,000 flows/second ingestion. Direct database writes cannot sustain this throughput without data loss.
2. **Decoupling:** Flow collectors (NetFlow, sFlow) must not be blocked by processing delays. Kafka provides necessary buffering.
3. **Durability:** Flow data loss during processing spikes is unacceptable. Kafka's replication ensures no data loss.
4. **Replay:** Security investigations may require reprocessing historical flows. Kafka retention enables replay.
5. **Multiple Consumers:** Flow data feeds both real-time detection and batch aggregation. Kafka enables fan-out without duplication.

**Scope of Use:**
- Flow data ingestion (NetFlow, sFlow, IPFIX)
- Real-time change event streaming
- Audit log streaming

**NOT used for:**
- Low-volume API events
- User session management
- Configuration storage

### 6.3 Redis Decision: JUSTIFIED FOR USE

**Decision:** Include Redis for caching and real-time features

**Justification:**
1. **Visualization Performance:** NFR-LT-003 requires topology load ≤2s for 1,000 nodes. Pre-computed graph layouts must be cached.
2. **API Latency:** NFR-LT-001 requires ≤100ms simple queries. Hot path data (asset metadata, recent queries) needs caching.
3. **Session Management:** NFR-SE-004 requires secure session tokens. Redis provides fast, centralized session storage.
4. **Rate Limiting:** API rate limiting requires distributed counters across application nodes.
5. **Real-time Notifications:** WebSocket presence and pub/sub for live topology updates.

**Scope of Use:**
- Query result caching (TTL: 5 minutes for dynamic data, 1 hour for static)
- Session storage
- Rate limiting counters
- Real-time pub/sub for WebSocket notifications
- Distributed locks for scan coordination

**NOT used for:**
- Primary data storage
- Long-term data persistence
- Audit logging

### 6.4 Complete Technology Matrix

| Layer | Technology | Purpose |
|-------|------------|---------|
| API Gateway | nginx / Traefik | Load balancing, TLS termination |
| Application | FastAPI + Uvicorn | REST API, WebSocket |
| Task Processing | Celery + Redis broker | Async discovery tasks |
| Stream Processing | Kafka + Faust | Flow data pipeline |
| Caching | Redis Cluster | Query cache, sessions |
| Primary Storage | PostgreSQL | System of record |
| Search | PostgreSQL FTS + pg_trgm | Full-text search (avoid Elasticsearch complexity) |
| Visualization | D3.js / Cytoscape.js | Frontend graph rendering |

---

## 7. Explicit Exclusions

The following capabilities are explicitly OUT OF SCOPE for FlowLens v1.0:

### 7.1 Feature Exclusions

| Exclusion | Rationale |
|-----------|-----------|
| **Agent-based discovery** | Agentless-only approach reduces deployment friction; agents may be considered for v2.0 |
| **Application Performance Monitoring (APM)** | FlowLens focuses on topology, not performance metrics; integrate with existing APM tools |
| **Log aggregation/analysis** | Use dedicated SIEM/log tools; FlowLens provides dependency context, not log search |
| **Network packet inspection (DPI)** | Protocol identification yes, payload inspection no; privacy and performance concerns |
| **Automated remediation** | FlowLens is observability-focused; automated actions require separate approval workflows |
| **Cost analysis/FinOps** | Focus on technical dependencies; financial analysis is separate domain |
| **Code-level dependency analysis** | FlowLens maps runtime dependencies; use dedicated SBOM tools for code dependencies |
| **Mobile device discovery** | Enterprise server/container focus; mobile devices are out of scope |
| **IoT/OT device deep inspection** | Basic discovery only; specialized OT security tools required for industrial systems |

### 7.2 Integration Exclusions

| Exclusion | Rationale |
|-----------|-----------|
| **Proprietary cloud-specific services** | Focus on compute/network; managed services (RDS, Lambda) tracked as external dependencies only |
| **Legacy mainframe integration** | Requires specialized protocols; potential future add-on |
| **Custom ERP system connectors** | SAP, Oracle ERP integrations require certified partnerships |

### 7.3 Deployment Exclusions

| Exclusion | Rationale |
|-----------|-----------|
| **SaaS-hosted offering** | v1.0 is self-hosted only; SaaS requires additional compliance work |
| **Air-gapped deployment** | Requires offline update mechanisms; potential v1.x feature |
| **Windows-native deployment** | Linux containers only; Windows hosts can be discovery targets, not deployment platform |

### 7.4 Scale Exclusions

| Exclusion | Rationale |
|-----------|-----------|
| **>100,000 assets** | Requires architectural changes for sharding; enterprise tier consideration |
| **Multi-region deployment** | Single-region deployment for v1.0; geo-distribution adds complexity |
| **Real-time sub-second change detection** | 5-minute detection latency is acceptable; real-time requires significant infrastructure |

---

## 8. Data Model Overview

### 8.1 Core Entities (PostgreSQL)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     Asset       │     │   Dependency    │     │   Discovery     │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (UUID)       │────<│ source_asset_id │     │ id (UUID)       │
│ type            │     │ target_asset_id │>────│ asset_id        │
│ name            │     │ protocol        │     │ source          │
│ fqdn            │     │ port            │     │ timestamp       │
│ ip_addresses[]  │     │ first_seen      │     │ raw_data (JSONB)│
│ tags (JSONB)    │     │ last_seen       │     │ confidence      │
│ metadata (JSONB)│     │ confidence      │     └─────────────────┘
│ created_at      │     │ metadata (JSONB)│
│ updated_at      │     └─────────────────┘
└─────────────────┘
         │
         │         ┌─────────────────┐     ┌─────────────────┐
         │         │   ChangeEvent   │     │     Alert       │
         └────────<├─────────────────┤     ├─────────────────┤
                   │ id (UUID)       │     │ id (UUID)       │
                   │ entity_type     │────>│ change_event_id │
                   │ entity_id       │     │ rule_id         │
                   │ change_type     │     │ severity        │
                   │ before (JSONB)  │     │ status          │
                   │ after (JSONB)   │     │ acknowledged_by │
                   │ detected_at     │     │ resolved_at     │
                   └─────────────────┘     └─────────────────┘
```

### 8.2 Key Indexes

- `assets`: GIN index on `ip_addresses`, `tags`; B-tree on `type`, `name`
- `dependencies`: Composite index on `(source_asset_id, target_asset_id)`; B-tree on `last_seen`
- `change_events`: B-tree on `detected_at`, `entity_type`
- Full-text search index on `assets.name`, `assets.fqdn`

---

## 9. API Overview

### 9.1 Core Endpoints

```
Assets
  GET    /api/v1/assets                    # List assets with filtering
  GET    /api/v1/assets/{id}               # Get asset details
  POST   /api/v1/assets                    # Create manual asset
  PATCH  /api/v1/assets/{id}               # Update asset metadata
  DELETE /api/v1/assets/{id}               # Remove asset

Dependencies
  GET    /api/v1/dependencies              # List dependencies
  GET    /api/v1/assets/{id}/dependencies  # Get asset dependencies
  POST   /api/v1/dependencies              # Declare manual dependency
  DELETE /api/v1/dependencies/{id}         # Remove dependency

Discovery
  POST   /api/v1/discovery/scans           # Trigger discovery scan
  GET    /api/v1/discovery/scans           # List scan history
  GET    /api/v1/discovery/scans/{id}      # Get scan status/results

Analysis
  POST   /api/v1/analysis/impact           # Run impact analysis
  POST   /api/v1/analysis/path             # Find dependency path
  GET    /api/v1/analysis/spof             # Identify single points of failure

Topology
  GET    /api/v1/topology                  # Get graph data for visualization
  GET    /api/v1/topology/export           # Export topology diagram

Changes & Alerts
  GET    /api/v1/changes                   # List change events
  GET    /api/v1/alerts                    # List alerts
  PATCH  /api/v1/alerts/{id}               # Acknowledge/resolve alert
```

---

## 10. Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Discovery accuracy | >95% of actual dependencies detected | Manual validation against known topology |
| False positive rate | <5% of reported dependencies | User feedback on incorrect mappings |
| Time to first value | <4 hours from deployment to first map | Onboarding telemetry |
| User adoption | >80% of target users active weekly | Login analytics |
| MTTR improvement | 25% reduction | Pre/post incident analysis |
| Change success rate | 15% improvement | ITSM integration metrics |

---

## 11. Milestones

### Phase 1: Foundation (MVP)
- Core asset discovery (network scan, SSH, WMI)
- Basic dependency detection (host sockets)
- PostgreSQL data model
- REST API (assets, dependencies)
- Basic web visualization
- Manual dependency declaration

### Phase 2: Scale
- Kafka flow ingestion pipeline
- Redis caching layer
- NetFlow/sFlow integration
- Change detection and alerting
- Impact analysis

### Phase 3: Enterprise
- Cloud provider integrations (AWS, Azure, GCP)
- Container/Kubernetes discovery
- SSO integration
- Advanced visualization features
- CMDB/ITSM integrations

### Phase 4: Intelligence
- Anomaly detection
- Automated classification
- What-if scenario modeling
- Advanced reporting

---

## 12. Open Questions

1. **Multi-tenancy model:** Separate databases vs. row-level security?
2. **Credential management:** Built-in vault vs. external-only integration?
3. **Visualization technology:** Build custom vs. commercial graph library?
4. **Kubernetes discovery:** In-cluster agent vs. API-only approach?
5. **Historical data retention:** Compression strategy for long-term storage?

---

## 13. Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| **Asset** | Any discoverable entity (server, VM, container, service) |
| **Dependency** | Directional relationship between two assets |
| **Blast radius** | Set of assets affected by failure of a given asset |
| **Flow** | Network connection metadata (NetFlow, sFlow, IPFIX) |
| **SPOF** | Single Point of Failure - asset whose failure causes cascade |

### B. Reference Implementations

- Faddom (commercial)
- NetBox (open source, IPAM-focused)
- Weave Scope (container-focused)
- VMware vRealize Network Insight

### C. Compliance Considerations

- GDPR: IP addresses may be PII in some jurisdictions
- SOC 2: Audit logging, access controls, encryption
- HIPAA: May discover PHI-containing systems; requires BAA consideration

---

*Document maintained by: Product Team*
*Last reviewed: 2024-12-24*
*Next review: 2025-01-24*
