# FlowLens vs Faddom: Python-Feasible Parity Matrix

**Version:** 1.0
**Date:** 2024-12-24
**Purpose:** Categorize Faddom features by implementation feasibility using only flow data and Python services (no proprietary agents, no packet capture)

---

## Executive Summary

This document analyzes Faddom's feature set and categorizes each capability based on what can be realistically implemented in FlowLens using:
- **NetFlow/sFlow/IPFIX** as the primary data source
- **Python-based services** for processing
- **Agentless protocols** (SSH, WMI, SNMP, cloud APIs) for enrichment
- **No proprietary agents** deployed on endpoints
- **No deep packet inspection (DPI)** or packet capture

### Parity Summary

| Category | Count | Percentage |
|----------|-------|------------|
| **Day-1 Parity** | 24 | 53% |
| **Deferred Parity** | 14 | 31% |
| **Out-of-Scope** | 7 | 16% |
| **Total Features** | 45 | 100% |

---

## Categorization Criteria

### Day-1 Parity
Features achievable in MVP using:
- Flow data (NetFlow v5/v9, sFlow, IPFIX)
- Standard Python libraries and frameworks
- PostgreSQL for storage
- Agentless credential-based queries (SSH, WMI, SNMP)
- Public cloud APIs

### Deferred Parity
Features requiring:
- Additional infrastructure (Kafka, specialized collectors)
- Complex ML/analytics pipelines
- Third-party integrations with significant development effort
- Scale optimizations beyond MVP

### Out-of-Scope
Features requiring:
- Proprietary agents on endpoints
- Deep packet inspection / payload analysis
- Real-time kernel-level instrumentation
- Capabilities outside Python ecosystem feasibility

---

## Detailed Parity Matrix

### 1. Asset Discovery

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **Agentless server discovery** | Day-1 | NetFlow source/dest IPs + port scan confirmation | `scapy`, `python-nmap`, `asyncssh` | Requires flow data or network access |
| **VM discovery (VMware)** | Day-1 | vSphere API queries | `pyvmomi` | Requires vCenter credentials |
| **Cloud instance discovery (AWS)** | Day-1 | AWS EC2/VPC APIs | `boto3` | Requires IAM credentials |
| **Cloud instance discovery (Azure)** | Day-1 | Azure Resource Manager APIs | `azure-mgmt-compute` | Requires service principal |
| **Cloud instance discovery (GCP)** | Deferred | GCP Compute API | `google-cloud-compute` | Lower priority, similar pattern |
| **Container discovery (Docker)** | Day-1 | Docker API queries | `docker-py` | Requires Docker socket access |
| **Kubernetes workload discovery** | Deferred | K8s API server queries | `kubernetes` | Requires cluster credentials |
| **Network device discovery** | Day-1 | SNMP polling | `pysnmp`, `netmiko` | Requires SNMP community strings |
| **OS fingerprinting** | Day-1 | SSH/WMI banner + software queries | `paramiko`, `pywinrm` | Requires credentials |
| **Software inventory** | Day-1 | SSH (`dpkg`, `rpm`) / WMI queries | `paramiko`, `pywinrm` | Requires elevated credentials |
| **Hardware inventory** | Deferred | SNMP + SSH/WMI DMI queries | `pysnmp`, `paramiko` | Not core to dependency mapping |
| **Auto-classification by type** | Day-1 | Port/protocol heuristics + OS detection | Custom logic | Rule-based, improvable over time |

### 2. Dependency Mapping

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **Network connection mapping** | Day-1 | NetFlow/sFlow/IPFIX ingestion | `scapy`, custom UDP listener | Core functionality |
| **Application-to-application mapping** | Day-1 | Flow aggregation by src/dst + port | Custom aggregation | Port-based inference only |
| **Service-level mapping** | Deferred | Port → service name resolution + process correlation | Custom + SSH queries | Requires host access for accuracy |
| **Database dependency detection** | Day-1 | Well-known ports (3306, 5432, 1433, 27017) | Flow analysis | Port-based, not query-level |
| **Message queue detection** | Day-1 | Well-known ports (5672, 9092, 6379) | Flow analysis | Port-based detection |
| **HTTP/HTTPS traffic identification** | Day-1 | Ports 80/443/8080/8443 | Flow analysis | Cannot see URLs without DPI |
| **Protocol identification (layer 7)** | Deferred | Port heuristics + flow patterns | ML-based inference | Limited without DPI |
| **Bidirectional flow correlation** | Day-1 | 5-tuple matching (src/dst swap) | Custom logic | Standard flow correlation |
| **Connection frequency/volume tracking** | Day-1 | Flow byte/packet counters | PostgreSQL aggregation | Native to flow data |
| **Subnet-level dependency mapping** | Day-1 | IP → subnet aggregation | `ipaddress` stdlib | Simple computation |
| **External dependency detection** | Day-1 | RFC1918 vs public IP classification | `ipaddress` stdlib | Egress traffic analysis |
| **Load balancer detection** | Deferred | Many-to-one flow patterns | Heuristic analysis | Pattern-based inference |
| **DNS dependency mapping** | Deferred | Port 53 flows + optional DNS server queries | Flow + `dnspython` | Limited without DNS logs |

### 3. Visualization

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **Interactive topology map** | Day-1 | Graph data API + frontend rendering | FastAPI + Cytoscape.js | Frontend implementation |
| **Node clustering/grouping** | Day-1 | Hierarchical grouping API | Custom logic | Business logic driven |
| **Connection status indicators** | Day-1 | Last-seen timestamp coloring | Flow timestamps | Green/grey/red status |
| **Directional arrows** | Day-1 | Flow direction from NetFlow | Native to flow data | Initiator vs responder |
| **Zoom/pan/filter** | Day-1 | Frontend implementation | Cytoscape.js / D3.js | Standard graph UI |
| **Subnet view** | Day-1 | IP aggregation layer | Custom + `ipaddress` | Hierarchical rendering |
| **Application grouping** | Deferred | Manual tagging + auto-inference | Custom logic | Requires asset enrichment |
| **Historical topology playback** | Deferred | Time-series queries + animation | PostgreSQL + frontend | Requires historical storage |
| **Export to Visio/PNG/SVG** | Deferred | Server-side rendering | `graphviz`, `svgwrite` | Secondary priority |
| **Saved views/dashboards** | Deferred | User preferences storage | PostgreSQL | UX feature |

### 4. Change Detection & Alerting

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **New asset detection** | Day-1 | First-seen IP tracking | PostgreSQL queries | Compare against baseline |
| **New connection detection** | Day-1 | First-seen flow 5-tuple | PostgreSQL queries | Core change detection |
| **Removed asset detection** | Day-1 | Missing from recent flows | Last-seen threshold | Configurable timeout |
| **Removed connection detection** | Day-1 | Connection not seen in window | Last-seen threshold | Configurable timeout |
| **Email notifications** | Day-1 | SMTP integration | `smtplib`, `aiosmtplib` | Standard integration |
| **Webhook notifications** | Day-1 | HTTP POST on events | `httpx`, `aiohttp` | Standard integration |
| **Slack/Teams integration** | Day-1 | Webhook + optional API | `slack-sdk`, webhooks | Common requirement |
| **PagerDuty integration** | Deferred | Events API v2 | `pdpyras` | Enterprise feature |
| **Alert rules engine** | Day-1 | Configurable rule evaluation | Custom logic | JSON-based rules |
| **Alert suppression windows** | Deferred | Maintenance window scheduler | `APScheduler` | Enterprise feature |

### 5. Security & Compliance

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **CVE detection** | Out-of-Scope | — | — | Requires agent for software inventory accuracy |
| **Shadow IT detection** | Day-1 | Unknown assets in flows | Baseline comparison | Flow-based detection |
| **Traffic anomaly detection** | Deferred | Statistical deviation analysis | `scipy`, `scikit-learn` | Requires baseline + ML |
| **SSL certificate monitoring** | Out-of-Scope | — | — | Requires TLS handshake inspection |
| **Attack surface mapping** | Day-1 | External-facing asset identification | Flow analysis | Ingress flow patterns |
| **Micro-segmentation support** | Day-1 | Export flow matrix for firewall rules | Flow aggregation | Data export, not enforcement |
| **Compliance reporting** | Deferred | Pre-built report templates | `reportlab`, `weasyprint` | Template development |
| **RBAC** | Day-1 | Role-based API access | FastAPI + JWT | Standard implementation |
| **Audit logging** | Day-1 | Action logging to PostgreSQL | Custom middleware | Compliance requirement |

### 6. Analysis & Reporting

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **Upstream dependency analysis** | Day-1 | Graph traversal (BFS/DFS) | `networkx` | Core analysis |
| **Downstream dependency analysis** | Day-1 | Reverse graph traversal | `networkx` | Core analysis |
| **Blast radius calculation** | Day-1 | N-hop traversal with counting | `networkx` | Graph algorithm |
| **Single point of failure detection** | Day-1 | Graph centrality analysis | `networkx` | Betweenness centrality |
| **Path finding between assets** | Day-1 | Shortest path algorithms | `networkx` | Dijkstra/BFS |
| **What-if scenario modeling** | Deferred | Simulated node removal | `networkx` | Complex UX |
| **PDF report generation** | Deferred | Template-based generation | `reportlab`, `weasyprint` | Secondary priority |
| **CSV/JSON export** | Day-1 | API export endpoints | FastAPI + `csv` stdlib | Standard feature |
| **Resource optimization recommendations** | Out-of-Scope | — | — | Requires performance metrics (APM territory) |
| **VM right-sizing recommendations** | Out-of-Scope | — | — | Requires hypervisor metrics |

### 7. Integration

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **REST API** | Day-1 | FastAPI implementation | `fastapi`, `pydantic` | Core requirement |
| **ServiceNow CMDB integration** | Deferred | REST API sync | `httpx`, `pysnow` | Enterprise feature |
| **BMC Helix integration** | Deferred | REST API sync | `httpx` | Enterprise feature |
| **Datadog integration** | Out-of-Scope | — | — | APM territory, not ADM |
| **SIEM export (Splunk, QRadar)** | Deferred | Syslog/HTTP forwarding | `logging`, `httpx` | Security use case |
| **SSO (SAML/OIDC)** | Deferred | Identity provider integration | `python-saml`, `authlib` | Enterprise feature |
| **Terraform provider** | Out-of-Scope | — | — | Infrastructure-as-code, different domain |

### 8. Deployment & Operations

| Faddom Feature | Category | FlowLens Approach | Python Libraries | Constraints |
|----------------|----------|-------------------|------------------|-------------|
| **OVA appliance deployment** | Deferred | Docker Compose / VM image | Docker, Packer | Packaging effort |
| **Sub-60-minute time to value** | Day-1 | Streamlined onboarding flow | UX design | Design goal |
| **No-credential mode** | Day-1 | Flow-only discovery | NetFlow ingestion | Reduced accuracy tradeoff |
| **Offline operation** | Out-of-Scope | — | — | Requires air-gap specific architecture |
| **Multi-site deployment** | Deferred | Federated collectors | Distributed architecture | Scale feature |

---

## Python Implementation Stack

### Day-1 Libraries

```
# Core Framework
fastapi>=0.104.0          # Web framework
uvicorn>=0.24.0           # ASGI server
pydantic>=2.5.0           # Data validation
sqlalchemy>=2.0.0         # ORM
asyncpg>=0.29.0           # PostgreSQL async driver
alembic>=1.12.0           # Migrations

# Network & Discovery
scapy>=2.5.0              # Packet crafting (flow parsing)
python-nmap>=0.7.1        # Port scanning
paramiko>=3.3.0           # SSH connections
pywinrm>=0.4.3            # WMI/WinRM
pysnmp>=4.4.12            # SNMP queries
netmiko>=4.2.0            # Network device SSH

# Cloud Providers
boto3>=1.29.0             # AWS
azure-mgmt-compute>=30.0  # Azure
pyvmomi>=8.0.0            # VMware vSphere

# Graph Analysis
networkx>=3.2             # Graph algorithms

# Utilities
httpx>=0.25.0             # HTTP client
aiosmtplib>=3.0.0         # Async SMTP
ipaddress                 # stdlib - IP handling
```

### Deferred Libraries (Phase 2+)

```
# Stream Processing
faust-streaming>=0.10.0   # Kafka stream processing
aiokafka>=0.9.0           # Kafka client

# ML/Analytics
scikit-learn>=1.3.0       # Anomaly detection
scipy>=1.11.0             # Statistical analysis

# Reporting
reportlab>=4.0.0          # PDF generation
weasyprint>=60.0          # HTML to PDF

# Enterprise Integrations
python-saml>=1.15.0       # SAML SSO
authlib>=1.2.0            # OIDC
pysnow>=0.7.0             # ServiceNow
kubernetes>=28.0.0        # K8s API
docker>=6.1.0             # Docker API
google-cloud-compute>=1.0 # GCP
```

---

## Feature Gap Analysis

### What Flow Data Provides

| Data Element | Available | Notes |
|--------------|-----------|-------|
| Source IP | ✅ | Core flow field |
| Destination IP | ✅ | Core flow field |
| Source Port | ✅ | Core flow field |
| Destination Port | ✅ | Core flow field |
| Protocol (L4) | ✅ | TCP/UDP/ICMP |
| Byte count | ✅ | Traffic volume |
| Packet count | ✅ | Connection activity |
| Timestamp | ✅ | Temporal analysis |
| TCP flags | ✅ | Connection state |
| Interface/VLAN | ✅ | Network context |
| AS numbers | ✅ | BGP-enabled environments |

### What Flow Data Does NOT Provide

| Data Element | Impact | Mitigation |
|--------------|--------|------------|
| Application protocol (L7) | Cannot distinguish HTTP vs custom on port 8080 | Port heuristics, SSH-based process inspection |
| Hostname | Must resolve IP → hostname separately | DNS lookups, reverse DNS, cloud API enrichment |
| Process name | Cannot see which process owns connection | SSH `netstat`/`ss` queries (requires credentials) |
| Container ID | Cannot attribute to specific container | Docker/K8s API correlation |
| User identity | Cannot see authenticated user | Out of scope for flow-based ADM |
| Payload/content | Cannot inspect data transferred | Out of scope (DPI required) |
| TLS certificate details | Cannot see cert chain | Out of scope (TLS inspection required) |
| SQL queries | Cannot see database operations | Out of scope (requires agent/proxy) |

---

## Day-1 vs Faddom Competitive Position

### Strengths (Day-1)

| Capability | FlowLens | Faddom |
|------------|----------|--------|
| Open source / self-hosted | ✅ | ❌ (Commercial only) |
| Python ecosystem extensibility | ✅ | ❌ |
| PostgreSQL as system of record | ✅ | Unknown |
| Cost | Free (self-hosted) | $10K+/year |
| Customization | Full | Limited |

### Gaps (Day-1)

| Capability | FlowLens | Faddom |
|------------|----------|--------|
| Time to value | ~4 hours | <1 hour |
| CVE detection | ❌ | ✅ |
| SSL certificate monitoring | ❌ | ✅ |
| VM right-sizing | ❌ | ✅ |
| Polished UI/UX | MVP-level | Production-grade |
| Enterprise support | Community | Commercial |

### Competitive Neutralizers

| Faddom Strength | FlowLens Neutralizer |
|-----------------|---------------------|
| 60-minute deployment | Docker Compose one-liner + guided setup |
| No credentials required | Flow-only mode available (reduced accuracy disclosed) |
| OVA appliance | Docker image / Helm chart |

---

## Implementation Phases

### Phase 1: Day-1 Parity (MVP)
**Timeline target: First release**

Focus:
1. NetFlow/sFlow/IPFIX ingestion
2. Asset discovery via flows + port scanning
3. Basic agentless enrichment (SSH/WMI/SNMP)
4. Interactive topology visualization
5. Change detection with email/webhook alerts
6. Impact analysis (upstream/downstream)
7. REST API with OpenAPI docs

### Phase 2: Deferred Parity
**Timeline target: v1.x releases**

Focus:
1. Kafka pipeline for high-volume flow ingestion
2. Cloud provider deep integrations (AWS, Azure, GCP)
3. Kubernetes/container discovery
4. Historical topology with time-slider
5. ML-based anomaly detection
6. ServiceNow/CMDB integration
7. SSO (SAML/OIDC)

### Phase 3: Differentiation
**Timeline target: v2.0+**

Focus:
1. Features Faddom doesn't have
2. Open API ecosystem
3. Community-contributed discovery plugins
4. GitOps-native configuration
5. Multi-cluster/multi-region federation

---

## Out-of-Scope Rationale

| Feature | Reason | Alternative |
|---------|--------|-------------|
| **CVE Detection** | Requires accurate software inventory from running processes; flow data insufficient | Integrate with dedicated vulnerability scanners (Nessus, Qualys, Trivy) |
| **SSL Certificate Monitoring** | Requires TLS handshake interception | Integrate with cert monitoring tools (cert-manager, Venafi) |
| **VM Right-Sizing** | Requires CPU/memory utilization metrics, not network flows | Integrate with monitoring (Prometheus, CloudWatch) |
| **Resource Optimization** | APM domain, not ADM | Integrate with APM tools (Datadog, New Relic) |
| **Terraform Provider** | Infrastructure provisioning, not discovery | Out of domain; users provision then discover |
| **Offline/Air-Gap** | Requires fundamentally different update/deployment model | Potential v2.0 feature with dedicated engineering |
| **Datadog Integration** | APM integration, FlowLens is not APM | Users correlate externally if needed |

---

## Conclusion

FlowLens can achieve **~53% feature parity with Faddom on Day-1** using only flow data and Python services. The remaining **31% is achievable with deferred effort**, primarily requiring Kafka for scale and enterprise integrations.

The **16% out-of-scope features** are fundamentally outside the flow-based, agentless architecture and should be addressed through integrations with specialized tools rather than native implementation.

**Key differentiator:** FlowLens offers an open-source, Python-native alternative that organizations can customize, extend, and integrate into their existing toolchains without vendor lock-in.

---

*Document maintained by: Engineering Team*
*Last updated: 2024-12-24*
