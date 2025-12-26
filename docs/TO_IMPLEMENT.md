# FlowLens Implementation Status

**Version:** 1.0
**Date:** 2024-12-25
**Purpose:** Track implementation progress against PRD and Parity Matrix requirements

---

## Currently Implemented (Phase 1-2 MVP)

| Category | Status | Details |
|----------|--------|---------|
| **Flow Ingestion** | 95% | NetFlow v5/v9, sFlow, IPFIX parsers with Kafka/PostgreSQL routing |
| **Dependency Mapping** | 90% | Flow aggregation, dependency building, temporal validity |
| **Visualization** | 95% | D3.js topology map, zoom/pan, hierarchical grouping, path highlighting, time-slider, saved views, export |
| **Change Detection** | 90% | 13 change types, asset/dependency lifecycle tracking |
| **Alerts** | 80% | Alert model, severity levels, acknowledgment, email notifications |
| **Impact Analysis** | 95% | Blast radius, upstream/downstream, SPOF detection, path finding |
| **REST API** | 95% | Comprehensive endpoints for all entities |
| **Enrichment** | 80% | GeoIP, DNS, protocol identification (200+ services) |

### Visualization Features (Completed)

| Feature | PRD Ref | Status |
|---------|---------|--------|
| Interactive topology map with zoom/pan | FR-VZ-001 | ✅ Done |
| Hierarchical grouping (location, environment, datacenter, type) | FR-VZ-002 | ✅ Done |
| Highlight dependency paths (upstream/downstream) | FR-VZ-003 | ✅ Done |
| Display connection metadata on click | FR-VZ-004 | ✅ Done |
| Reset view button | - | ✅ Done |
| Clear selection button | - | ✅ Done |
| Internal/External node coloring (I/E indicators) | - | ✅ Done |
| Convex hull group visualization | - | ✅ Done |
| Dynamic legend with group counts | - | ✅ Done |
| Historical topology (time-slider) | FR-VZ-006 | ✅ Done |
| Saved views/dashboards | FR-VZ-008 | ✅ Done |
| Diagram export (PNG/SVG) | FR-VZ-007 | ✅ Done |

---

## Missing from Day-1 Parity (P0 Requirements)

| Feature | PRD Ref | Priority | Effort | Status |
|---------|---------|----------|--------|--------|
| Asset metadata editing | FR-AD-007 | P0 | Low | Not Started |
| CIDR-based classification rules | FR-AD-007 | P0 | Medium | Not Started |
| Dynamic grouping from CIDR rules | FR-AD-007 | P0 | Medium | Not Started |
| Bulk asset import/update | FR-AD-007 | P0 | Low | Not Started |
| SSH-based asset discovery | FR-AD-002 | P0 | Medium | Not Started |
| WMI-based discovery (Windows) | FR-AD-002 | P0 | Medium | Not Started |
| SNMP device discovery | FR-AD-002 | P0 | Medium | Not Started |
| Discovery job scheduler | FR-AD-001 | P0 | Medium | Not Started |
| Discovery credentials management | FR-AD-005 | P0 | Medium | Not Started |
| Alert rules engine | FR-CD-005 | P0 | Medium | Not Started |
| Alert rules UI | FR-CD-005 | P0 | Medium | Not Started |
| Webhook notifications | FR-CD-006 | P0 | Low | Not Started |
| Slack integration | FR-CD-006 | P0 | Low | Not Started |
| RBAC implementation | FR-AM-001 | P0 | Medium | Not Started |
| User management UI | FR-AM-001 | P0 | Medium | Not Started |
| Audit logging | FR-AM-002 | P0 | Medium | Not Started |

---

## Missing from Day-1 Parity (P1 Requirements)

| Feature | PRD Ref | Priority | Effort | Status |
|---------|---------|----------|--------|--------|
| VMware vSphere discovery | FR-AD-003 | P1 | Medium | Not Started |
| Nutanix AHV discovery | FR-AD-003 | P1 | Medium | Not Started |
| AWS EC2/VPC discovery | FR-AD-003 | P1 | Medium | Not Started |
| AWS VPC Flow Logs ingestion | FR-DM-001 | P1 | Medium | Not Started |
| Azure VM discovery | FR-AD-003 | P1 | Medium | Not Started |
| Azure NSG Flow Logs ingestion | FR-DM-001 | P1 | Medium | Not Started |
| Docker container discovery | FR-AD-004 | P1 | Low | Not Started |
| Kubernetes discovery | FR-AD-004 | P1 | Medium | Not Started |
| Credential vault integration | FR-AD-005 | P1 | Medium | Not Started |
| Software inventory extraction | FR-AD-008 | P1 | Medium | Not Started |
| Packet capture integration | FR-DM-002 | P1 | High | Not Started |
| Historical topology (time-slider) | FR-VZ-006 | P1 | Medium | Done |
| Diagram export (PNG/SVG) | FR-VZ-007 | P1 | Low | Done |
| Saved views/dashboards | FR-VZ-008 | P1 | Medium | Done |
| PagerDuty integration | FR-CD-006 | P1 | Low | Not Started |
| Alert suppression windows | FR-CD-007 | P1 | Medium | Not Started |
| Notification preferences | FR-CD-008 | P1 | Low | Not Started |
| SSO (SAML/OIDC) | FR-IN-005 | P1 | High | Not Started |
| CMDB integration (ServiceNow) | FR-IN-002 | P1 | High | Not Started |
| Data retention policies | FR-AM-006 | P1 | Medium | Not Started |
| System health dashboard | FR-AM-007 | P1 | Medium | Not Started |
| Flow source management UI | FR-AM-007 | P1 | Low | Not Started |
| Prometheus metrics endpoint | FR-AM-007 | P1 | Low | Not Started |

---

## Deferred/Phase 3+ (P2)

| Feature | PRD Ref | Status |
|---------|---------|--------|
| GCP discovery | FR-AD-003 | Not Started |
| GraphQL API | FR-IN-006 | Not Started |
| What-if scenario modeling | FR-IA-007 | Not Started |
| Custom discovery plugins | FR-AD-009 | Not Started |
| Multi-tenancy | FR-AM-003 | Not Started |
| Multi-region deployment | NFR-SC-004 | Not Started |
| Load balancer detection | - | Not Started |
| DNS dependency mapping | - | Not Started |
| Compliance reporting | - | Not Started |

---

## Out of Scope (Per Parity Matrix)

These require agents or capabilities outside flow-based architecture:

| Feature | Reason | Alternative |
|---------|--------|-------------|
| CVE detection | Requires agent for software inventory accuracy | Integrate with Nessus, Qualys, Trivy |
| SSL certificate monitoring | Requires TLS handshake inspection | Integrate with cert-manager, Venafi |
| VM right-sizing recommendations | Requires CPU/memory metrics | Integrate with Prometheus, CloudWatch |
| Resource optimization | APM domain, not ADM | Integrate with Datadog, New Relic |
| Terraform provider | Infrastructure provisioning, different domain | Out of scope |
| Offline/air-gap operation | Requires different update/deployment model | Potential v2.0 feature |
| Datadog integration | APM integration, FlowLens is not APM | Users correlate externally |

---

## Prioritized Implementation Roadmap

The following prioritization is based on:
- **User Value**: Features that unlock the most functionality for end users
- **Effort/Impact Ratio**: Low-effort, high-impact items first
- **Dependencies**: Features that enable other features
- **Production Readiness**: Security and compliance requirements for production use

---

### Sprint 1: Production Readiness (Security & Compliance)
*These are blockers for any production deployment*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 1 | **Audit logging** | Medium | Compliance requirement; needed for SOC2, security audits |
| 2 | **RBAC implementation** | Medium | Multi-user security; prevents unauthorized access |
| 3 | **Webhook notifications** | Low | Enables integration ecosystem; unblocks external tooling |
| 4 | **User management UI** | Medium | Admin interface to create/manage users and roles |

**Outcome**: Production-ready security posture

**Missing detail**: RBAC requires a way to actually manage users - need user CRUD endpoints and admin UI

---

### Sprint 1.5: Asset Management & Classification
*Enable users to enrich and organize discovered assets - required for grouping to be useful*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 1.5a | **Asset metadata editing** | Low | Allow manual editing of owner, team, description, criticality on Asset Detail page |
| 1.5b | **CIDR-based classification rules** | Medium | Define IP ranges with attributes (environment, datacenter, location) |
| 1.5c | **Dynamic grouping from CIDR rules** | Medium | Topology grouping evaluates CIDR rules in real-time, not static asset fields |
| 1.5d | **Bulk asset import/update** | Low | CSV/JSON import for attributes not derivable from CIDR (owner, team, criticality) |

**Outcome**: Topology grouping becomes meaningful; assets have organizational context

**Details:**
- **Asset metadata editing**: Manual edits for fields that can't be derived from IP (owner, team, description, is_critical)
- **CIDR classification rules**:
  - Rules define: CIDR range → environment, datacenter, location, asset_type
  - More specific CIDRs (longer prefix) take priority over broader ones
  - Rules are the source of truth - renaming "DC-East" to "US-East-1" instantly updates all assets in that range
  - New assets automatically classified on discovery based on matching rules
- **Dynamic grouping**:
  - Topology "Group by Datacenter" evaluates each asset's IP against CIDR rules at query time
  - No need to store derived attributes on asset records (avoids stale data)
  - Rules can be cached/materialized for performance if needed
- **Bulk import**: For attributes that vary per-asset (owner, team) not per-subnet

---

### Sprint 2: Actionable Alerting
*Make the alerting system useful for operations*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 5 | **Alert rules engine** | Medium | Without rules, alerts are noise; enables actionable notifications |
| 6 | **Alert rules UI** | Medium | UI to create/edit/test alert rules |
| 7 | **Slack integration** | Low | #1 enterprise notification channel; immediate user value |
| 8 | **PagerDuty integration** | Low | On-call alerting for critical dependencies; ops essential |
| 9 | **Alert suppression windows** | Medium | Prevents alert fatigue during maintenance |
| 10 | **Notification preferences** | Low | Per-user settings for which alerts to receive and how |

**Outcome**: Ops teams can respond to meaningful alerts

**Missing detail**: Alert rules need a UI to configure them, not just backend logic

---

### Sprint 3: Active Discovery (Linux/Containers)
*Enrich flow-based discovery with active host interrogation*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 8 | **Discovery job scheduler** | Medium | Background job system to run discovery on schedule |
| 9 | **Discovery credentials management** | Medium | Secure storage for SSH keys, passwords (encrypted in DB or vault) |
| 10 | **SSH-based discovery** | Medium | Linux servers are majority of infrastructure; hostname, OS, services |
| 11 | **Docker container discovery** | Low | Containers are ubiquitous; low effort via Docker API |
| 12 | **Kubernetes discovery** | Medium | K8s is standard orchestration; builds on Docker work |

**Outcome**: Rich asset metadata for Linux/container environments

**Missing detail**: Discovery requires infrastructure - job scheduling, credential storage, discovery status UI

---

### Sprint 4: Network & Windows Discovery
*Complete the discovery story for heterogeneous environments*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 11 | **SNMP device discovery** | Medium | Network devices (routers, switches, firewalls); critical for full topology |
| 12 | **WMI-based discovery** | Medium | Windows environments; completes cross-platform story |
| 13 | **Software inventory extraction** | Medium | Builds on SSH/WMI; enables application-level mapping |

**Outcome**: Full cross-platform asset discovery

---

### Sprint 5: Hypervisor Discovery
*On-premises virtualization platforms - critical for enterprise datacenters*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 14 | **VMware vSphere discovery** | Medium | Dominant enterprise hypervisor; vCenter API for VMs, hosts, clusters |
| 15 | **Nutanix AHV discovery** | Medium | Growing HCI platform; Prism API for VMs and clusters |

**Outcome**: Full visibility into virtualized infrastructure

---

### Sprint 6: Cloud Discovery
*Extend discovery to cloud-native infrastructure*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 16 | **AWS EC2/VPC discovery** | Medium | Largest cloud provider; VPC flow logs + EC2 metadata |
| 17 | **AWS VPC Flow Logs ingestion** | Medium | Native AWS flow data; richer than NetFlow for AWS traffic |
| 18 | **Azure VM discovery** | Medium | Second largest; similar pattern to AWS |
| 19 | **Azure NSG Flow Logs ingestion** | Medium | Native Azure flow data |
| 20 | **Credential vault integration** | Medium | Secure storage for cloud/hypervisor APIs (HashiCorp Vault, AWS Secrets Manager) |

**Outcome**: Cloud workloads integrated into dependency map

**Missing detail**: Cloud discovery should include native flow log ingestion, not just metadata

---

### Sprint 7: Enterprise Authentication & Integration
*Enterprise SSO and CMDB sync*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 19 | **SSO (SAML/OIDC)** | High | Enterprise requirement; centralized identity |
| 20 | **CMDB integration (ServiceNow)** | High | Bidirectional sync; single source of truth |
| 21 | **Data retention policies** | Medium | Compliance; storage management |

**Outcome**: Enterprise-ready identity and CMDB integration

---

### Sprint 8: Advanced Visualization ✅ COMPLETED
*Polish and power-user features*

| # | Feature | Effort | Status |
|---|---------|--------|--------|
| 22 | **Historical topology (time-slider)** | Medium | ✅ Done |
| 23 | **Saved views/dashboards** | Medium | ✅ Done |
| 24 | **Diagram export (PNG/SVG)** | Low | ✅ Done |

**Outcome**: Complete visualization feature set - ACHIEVED

---

### Sprint 9: Advanced Data Collection
*Optional enhancements for deeper visibility*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 25 | **Packet capture integration** | High | Deep protocol inspection; optional for most users |
| 26 | **GCP discovery** | Medium | Third cloud provider; lower priority than AWS/Azure |

**Outcome**: Extended data collection options

---

### Sprint 10: Operational Excellence
*Features needed to run FlowLens in production at scale*

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 27 | **System health dashboard** | Medium | Monitor ingestion rates, queue depths, error rates |
| 28 | **Flow source management UI** | Low | Add/edit/delete NetFlow/sFlow exporters with status |
| 29 | **Database maintenance jobs** | Medium | Automated cleanup, vacuuming, partition management |
| 30 | **Backup/restore procedures** | Medium | Documented and tested backup strategy |
| 31 | **Prometheus metrics endpoint** | Low | Expose /metrics for external monitoring |
| 32 | **Log aggregation integration** | Low | Structured logging compatible with ELK/Splunk |

**Outcome**: FlowLens can be operated reliably in production

**Missing detail**: No visibility into system health or flow source status currently

---

### Future/Backlog (P2)

| Feature | Rationale for Deferral |
|---------|------------------------|
| GraphQL API | REST API sufficient; GraphQL adds complexity |
| What-if scenario modeling | Nice-to-have; requires significant UI work |
| Custom discovery plugins | Extensibility after core is stable |
| Multi-tenancy | Enterprise-tier feature |
| Multi-region deployment | Scale requirement; architecture change |
| Load balancer detection | Heuristic-based; low accuracy without agents |
| DNS dependency mapping | Requires DNS server integration |
| Compliance reporting | Template-based; customer-specific |

---

## Quick Wins (Can Be Done Anytime)

These are low-effort items that can fill gaps between sprints:

| Feature | Effort | Notes |
|---------|--------|-------|
| Asset metadata editing | Low | Edit environment, datacenter, owner, team on Asset Detail page |
| Diagram export (PNG/SVG) | Low | Canvas/SVG serialization - ✅ Done |
| Webhook notifications | Low | HTTP POST on events |
| Slack integration | Low | Webhook + optional API |
| PagerDuty integration | Low | Events API v2 |
| Docker container discovery | Low | Docker API queries |

---

## Dependencies Graph

```
Audit Logging ──┐
                ├──> User Management UI ──> Production Ready ──> Enterprise Deployment
RBAC ───────────┘

Asset Metadata Editing ──┐
                         ├──> Meaningful Topology Grouping
CIDR Classification ─────┘

Alert Rules Engine ──> Alert Rules UI ──┬──> Slack/PagerDuty ──> Actionable Ops
                                        └──> Suppression Windows

Discovery Job Scheduler ──┐
                          ├──> SSH/WMI/SNMP Discovery ──> Software Inventory
Credential Management ────┘

SSH Discovery ──┬──> Software Inventory
                └──> Container Discovery ──> K8s Discovery

SNMP + WMI ─────> Full Cross-Platform Discovery

VMware/Nutanix ─> Hypervisor Visibility ──┐
                                          ├──> Complete Infrastructure Map
AWS/Azure + Flow Logs ──> Credential Vault┘

SSO ────────────> CMDB Integration ──> Enterprise Ready

System Health Dashboard ──> Flow Source Mgmt ──> Operational Excellence
```

---

## Effort Estimates

| Effort | Meaning | Typical Duration |
|--------|---------|------------------|
| Low | < 2 days | Simple integration, API wrapper |
| Medium | 3-5 days | New subsystem, moderate complexity |
| High | 1-2 weeks | Significant architecture, external dependencies |

---

## Risk Assessment

| Feature | Risk | Mitigation |
|---------|------|------------|
| SSO (SAML/OIDC) | Complex protocol, IdP variations | Use established library (authlib) |
| CMDB Integration | ServiceNow API complexity | Start with read-only sync |
| Packet Capture | Performance impact, legal concerns | Make optional, document privacy |
| Kubernetes | API versioning, RBAC complexity | Target specific K8s versions |
| WMI Discovery | Windows security policies | Require domain admin guidance |
| VMware vSphere | vCenter API versioning (6.x vs 7.x vs 8.x) | Use pyvmomi; support multiple versions |
| Nutanix AHV | Prism API v2 vs v3 differences | Target Prism Central v3 API |

---

## Architecture Notes

### What's Working Well

- **Flow ingestion pipeline** - Robust NetFlow/sFlow/IPFIX parsing with adaptive routing
- **Dependency resolution** - Accurate flow-to-dependency mapping with temporal tracking
- **Impact analysis** - Comprehensive graph traversal algorithms
- **API design** - RESTful, well-structured endpoints with OpenAPI docs
- **Change detection** - 13 change types covering asset and dependency lifecycle

### Areas Needing Work

- **Discovery** - Currently passive (flow-based only), needs active discovery
- **Notifications** - Only email implemented, missing webhooks/Slack/PagerDuty
- **Security** - No RBAC, no audit logging, no SSO
- **UI Polish** - Basic functionality works, needs UX improvements

---

## Technical Debt

| Item | Priority | Notes |
|------|----------|-------|
| Remove `AssetType.EXTERNAL` from database | High | Enum removed from code, existing data needs migration |
| Redis caching | Medium | Referenced in config but not fully implemented |
| WebSocket real-time updates | Medium | Router exists but not fully integrated with frontend |
| Test coverage | Medium | Unit and integration tests needed |
| API rate limiting | Low | Mentioned in PRD but not implemented |

---

*Document maintained by: Engineering Team*
*Last updated: 2024-12-25*
