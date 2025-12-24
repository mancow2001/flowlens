# FlowLens Phase 1: Python-Native Architecture

**Version:** 1.0
**Date:** 2024-12-24
**Status:** Design Document

---

## 1. Executive Summary

This document defines the Python-native, service-oriented architecture for FlowLens Phase 1. The architecture prioritizes:

1. **PostgreSQL as the authoritative store** - All truth lives in PostgreSQL
2. **Python services using FastAPI** - Async-first, high-performance
3. **Optional Kafka/Redis** - Introduced only when thresholds are exceeded
4. **Horizontal scalability** - Each service independently scalable

---

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL DATA SOURCES                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   NetFlow    │  │    sFlow     │  │    IPFIX     │  │  Cloud APIs / SSH /  │ │
│  │  Exporters   │  │   Agents     │  │  Exporters   │  │  WMI / SNMP Sources  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘ │
│         │                 │                 │                      │             │
│         └─────────────────┴────────┬────────┴──────────────────────┘             │
│                                    │                                             │
│                              UDP/TCP                                             │
└────────────────────────────────────┼─────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           INGESTION LAYER                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                     FLOW INGESTION SERVICE                               │    │
│  │                        (Python/FastAPI)                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │    │
│  │  │   NetFlow   │  │   sFlow     │  │   IPFIX     │  │   Rate Limiter  │ │    │
│  │  │   Parser    │  │   Parser    │  │   Parser    │  │   & Sampler     │ │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘ │    │
│  │         └────────────────┴────────────────┴──────────────────┘          │    │
│  │                                   │                                      │    │
│  │                          Normalized Flow                                 │    │
│  └───────────────────────────────────┼──────────────────────────────────────┘    │
│                                      │                                           │
│         ┌────────────────────────────┼────────────────────────────┐              │
│         │                            │                            │              │
│         ▼                            ▼                            ▼              │
│  ┌─────────────┐            ┌─────────────────┐           ┌─────────────┐       │
│  │  PostgreSQL │◄───────────│  OPTIONAL PATH  │──────────►│    Kafka    │       │
│  │  (Direct)   │            │   Decision Gate │           │   (Buffer)  │       │
│  │             │            │                 │           │             │       │
│  │  < 10k/sec  │            │  Rate Monitor   │           │  ≥ 10k/sec  │       │
│  └──────┬──────┘            └─────────────────┘           └──────┬──────┘       │
│         │                                                        │              │
│         └────────────────────────┬───────────────────────────────┘              │
│                                  │                                              │
└──────────────────────────────────┼──────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PROCESSING LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                     ENRICHMENT SERVICE                                   │    │
│  │                        (Python/FastAPI)                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │    │
│  │  │     DNS     │  │   GeoIP     │  │    Cloud    │  │     Asset       │ │    │
│  │  │   Resolver  │  │   Lookup    │  │ API Enricher│  │    Correlator   │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │    │
│  │                                                                          │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐│    │
│  │  │                    OPTIONAL: Redis Cache                            ││    │
│  │  │         (DNS cache, GeoIP cache, Asset metadata cache)              ││    │
│  │  └─────────────────────────────────────────────────────────────────────┘│    │
│  └───────────────────────────────────┬──────────────────────────────────────┘    │
│                                      │                                           │
│                                      ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                  DEPENDENCY RESOLUTION SERVICE                           │    │
│  │                        (Python/FastAPI)                                  │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │    │
│  │  │    Flow     │  │   Asset     │  │  Dependency │  │     Change      │ │    │
│  │  │  Aggregator │  │   Mapper    │  │   Builder   │  │    Detector     │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │    │
│  │                                                                          │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐│    │
│  │  │              OPTIONAL: Redis (Aggregation Windows)                  ││    │
│  │  │         (In-flight aggregation buffers, deduplication)              ││    │
│  │  └─────────────────────────────────────────────────────────────────────┘│    │
│  └───────────────────────────────────┬──────────────────────────────────────┘    │
│                                      │                                           │
└──────────────────────────────────────┼──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         PostgreSQL 15+                                   │    │
│  │                    (Authoritative Data Store)                            │    │
│  │                                                                          │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                │    │
│  │  │    assets     │  │ dependencies  │  │  flow_stats   │                │    │
│  │  │               │  │               │  │  (time-series)│                │    │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                │    │
│  │                                                                          │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                │    │
│  │  │ change_events │  │    alerts     │  │  audit_logs   │                │    │
│  │  │               │  │               │  │               │                │    │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                │    │
│  │                                                                          │    │
│  │  Extensions: pg_partman (partitioning), pg_trgm (search)                │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             API LAYER                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                      QUERY / API SERVICE                                 │    │
│  │                        (Python/FastAPI)                                  │    │
│  │                                                                          │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │    │
│  │  │   Assets    │  │Dependencies │  │  Topology   │  │    Analysis     │ │    │
│  │  │    API      │  │    API      │  │    API      │  │      API        │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │    │
│  │                                                                          │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │    │
│  │  │   Alerts    │  │   Changes   │  │  Discovery  │  │    WebSocket    │ │    │
│  │  │    API      │  │    API      │  │    API      │  │   (Real-time)   │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────┘ │    │
│  │                                                                          │    │
│  │  ┌─────────────────────────────────────────────────────────────────────┐│    │
│  │  │              OPTIONAL: Redis (Query Cache)                          ││    │
│  │  │    (Topology cache, search results, session tokens, rate limits)    ││    │
│  │  └─────────────────────────────────────────────────────────────────────┘│    │
│  └───────────────────────────────────┬──────────────────────────────────────┘    │
│                                      │                                           │
└──────────────────────────────────────┼──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL CONSUMERS                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   Web UI     │  │   CLI Tool   │  │  CMDB Sync   │  │   Alerting Systems   │ │
│  │  (SPA/React) │  │  (Python)    │  │  (ServiceNow)│  │  (Slack/PagerDuty)   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Service Responsibilities

### 3.1 Flow Ingestion Service

**Purpose:** Receive, parse, normalize, and route flow data from network infrastructure.

**Technology:** Python 3.11+, FastAPI (for health/metrics endpoints), asyncio UDP server

**Responsibilities:**

| Responsibility | Description |
|----------------|-------------|
| **Protocol Parsing** | Parse NetFlow v5/v9, sFlow v5, IPFIX into normalized internal format |
| **Template Management** | Handle NetFlow v9/IPFIX templates with LRU cache |
| **Rate Monitoring** | Track incoming flow rate, emit metrics |
| **Sampling** | Apply configurable sampling (1:N) under load |
| **Routing Decision** | Route to PostgreSQL (low volume) or Kafka (high volume) |
| **Backpressure** | Drop/sample when downstream cannot keep up |
| **Health Endpoints** | `/health`, `/metrics` for observability |

**Interfaces:**

```python
# Input: UDP packets on ports 2055 (NetFlow), 6343 (sFlow), 4739 (IPFIX)
# Output: Normalized FlowRecord

@dataclass
class FlowRecord:
    timestamp: datetime
    src_ip: IPv4Address | IPv6Address
    dst_ip: IPv4Address | IPv6Address
    src_port: int
    dst_port: int
    protocol: int  # TCP=6, UDP=17, ICMP=1
    bytes: int
    packets: int
    tcp_flags: int
    input_interface: int
    output_interface: int
    src_as: int | None
    dst_as: int | None
    exporter_ip: IPv4Address

# Routing decision
class FlowRouter(Protocol):
    async def route(self, flows: list[FlowRecord]) -> None: ...

class PostgreSQLRouter(FlowRouter): ...  # Direct DB insert
class KafkaRouter(FlowRouter): ...        # Kafka producer
```

**Configuration Knobs:**

```yaml
ingestion:
  # UDP listener settings
  bind_address: "0.0.0.0"
  netflow_port: 2055
  sflow_port: 6343
  ipfix_port: 4739

  # Buffer settings
  receive_buffer_size: 16777216  # 16MB UDP buffer
  batch_size: 1000               # Flows per batch
  batch_timeout_ms: 100          # Max wait before flush

  # Routing thresholds
  routing:
    mode: "auto"  # "postgres", "kafka", or "auto"
    kafka_threshold_flows_per_sec: 10000

  # Backpressure
  backpressure:
    enabled: true
    sample_rate_under_pressure: 10  # 1:10 sampling
    drop_threshold_queue_depth: 100000
```

---

### 3.2 Enrichment Service

**Purpose:** Enhance raw flow data with contextual information from external sources.

**Technology:** Python 3.11+, FastAPI, asyncio

**Responsibilities:**

| Responsibility | Description |
|----------------|-------------|
| **DNS Resolution** | Reverse DNS lookup for IP addresses |
| **GeoIP Lookup** | Country/city/ASN from MaxMind databases |
| **Cloud Enrichment** | AWS/Azure/GCP metadata via APIs |
| **Asset Correlation** | Match IPs to known assets in database |
| **Protocol Inference** | Infer L7 protocol from port patterns |
| **Caching** | Cache enrichment results (Redis optional) |

**Interfaces:**

```python
@dataclass
class EnrichedFlow:
    flow: FlowRecord

    # DNS enrichment
    src_hostname: str | None
    dst_hostname: str | None

    # GeoIP enrichment
    src_geo: GeoInfo | None
    dst_geo: GeoInfo | None

    # Asset correlation
    src_asset_id: UUID | None
    dst_asset_id: UUID | None

    # Protocol inference
    inferred_protocol: str | None  # "http", "postgresql", "redis", etc.

    # Classification
    is_internal: bool  # Both IPs are RFC1918
    is_egress: bool    # Internal → External
    is_ingress: bool   # External → Internal

@dataclass
class GeoInfo:
    country_code: str
    city: str | None
    latitude: float | None
    longitude: float | None
    asn: int | None
    as_org: str | None
```

**Configuration Knobs:**

```yaml
enrichment:
  # DNS settings
  dns:
    enabled: true
    resolver: "system"  # or specific DNS server
    timeout_ms: 500
    cache_ttl_seconds: 3600
    negative_cache_ttl_seconds: 300
    max_concurrent_lookups: 100

  # GeoIP settings
  geoip:
    enabled: true
    database_path: "/data/GeoLite2-City.mmdb"
    asn_database_path: "/data/GeoLite2-ASN.mmdb"

  # Cloud enrichment
  cloud:
    aws:
      enabled: true
      regions: ["us-east-1", "us-west-2"]
      refresh_interval_seconds: 300
    azure:
      enabled: false
    gcp:
      enabled: false

  # Caching (Redis optional)
  cache:
    backend: "memory"  # "memory" or "redis"
    redis_url: "redis://localhost:6379/0"
    max_memory_entries: 100000
```

---

### 3.3 Dependency Resolution Service

**Purpose:** Transform enriched flows into asset relationships and detect changes.

**Technology:** Python 3.11+, FastAPI, asyncio

**Responsibilities:**

| Responsibility | Description |
|----------------|-------------|
| **Flow Aggregation** | Aggregate flows into connection summaries (5-min windows) |
| **Asset Upsert** | Create/update assets from observed IPs |
| **Dependency Building** | Create/update edges between assets |
| **Deduplication** | Prevent duplicate dependency records |
| **Change Detection** | Compare against baseline, emit change events |
| **Statistics** | Compute connection frequency, byte volume, timing |

**Interfaces:**

```python
@dataclass
class ConnectionSummary:
    """Aggregated view of flows between two endpoints over a time window."""
    src_asset_id: UUID
    dst_asset_id: UUID
    protocol: int
    dst_port: int

    window_start: datetime
    window_end: datetime

    flow_count: int
    total_bytes: int
    total_packets: int

    # Observed TCP flags (useful for connection state analysis)
    observed_tcp_flags: int

@dataclass
class DependencyRecord:
    """Persistent dependency between two assets."""
    id: UUID
    source_asset_id: UUID
    target_asset_id: UUID

    protocol: int
    port: int
    inferred_service: str | None  # "postgresql", "http", etc.

    first_seen: datetime
    last_seen: datetime

    # Aggregated statistics
    total_bytes: int
    total_flows: int
    avg_flows_per_hour: float

    # Confidence score (0.0 - 1.0)
    confidence: float

    # User-provided metadata
    tags: dict[str, str]
    notes: str | None

class ChangeType(Enum):
    NEW_ASSET = "new_asset"
    NEW_DEPENDENCY = "new_dependency"
    REMOVED_ASSET = "removed_asset"
    REMOVED_DEPENDENCY = "removed_dependency"
    ASSET_ATTRIBUTE_CHANGED = "asset_changed"
    DEPENDENCY_ATTRIBUTE_CHANGED = "dependency_changed"

@dataclass
class ChangeEvent:
    id: UUID
    change_type: ChangeType
    entity_type: str  # "asset" or "dependency"
    entity_id: UUID
    detected_at: datetime
    before_state: dict | None
    after_state: dict | None
```

**Configuration Knobs:**

```yaml
dependency_resolution:
  # Aggregation windows
  aggregation:
    window_size_seconds: 300  # 5-minute windows
    flush_interval_seconds: 60
    buffer_backend: "memory"  # "memory" or "redis"
    redis_url: "redis://localhost:6379/1"

  # Asset creation
  assets:
    auto_create: true
    min_flows_for_creation: 5  # Require N flows before creating asset

  # Dependency creation
  dependencies:
    min_flows_for_creation: 3
    confidence_threshold: 0.5
    stale_after_hours: 168  # 7 days without traffic = stale

  # Change detection
  change_detection:
    enabled: true
    baseline_window_days: 7
    check_interval_seconds: 300
```

---

### 3.4 Query / API Service

**Purpose:** Serve all external API requests for assets, dependencies, topology, and analysis.

**Technology:** Python 3.11+, FastAPI, Uvicorn, asyncpg

**Responsibilities:**

| Responsibility | Description |
|----------------|-------------|
| **REST API** | Full CRUD for assets, dependencies, alerts |
| **Topology API** | Graph data for visualization (nodes, edges) |
| **Analysis API** | Impact analysis, path finding, SPOF detection |
| **Search** | Full-text search across assets |
| **WebSocket** | Real-time topology updates |
| **Authentication** | JWT-based auth, RBAC enforcement |
| **Rate Limiting** | Per-user/API-key rate limits |
| **Caching** | Query result caching (Redis optional) |

**API Structure:**

```
/api/v1/
├── assets/
│   ├── GET    /                    # List assets (paginated, filtered)
│   ├── POST   /                    # Create manual asset
│   ├── GET    /{id}                # Get asset details
│   ├── PATCH  /{id}                # Update asset
│   ├── DELETE /{id}                # Delete asset
│   └── GET    /{id}/dependencies   # Get asset's dependencies
│
├── dependencies/
│   ├── GET    /                    # List dependencies
│   ├── POST   /                    # Declare manual dependency
│   ├── GET    /{id}                # Get dependency details
│   ├── PATCH  /{id}                # Update dependency metadata
│   └── DELETE /{id}                # Remove dependency
│
├── topology/
│   ├── GET    /                    # Get graph data
│   ├── GET    /export              # Export diagram
│   └── WS     /ws                  # WebSocket for real-time updates
│
├── analysis/
│   ├── POST   /impact              # Impact analysis
│   ├── POST   /path                # Path finding
│   ├── GET    /spof                # Single points of failure
│   └── POST   /blast-radius        # Blast radius calculation
│
├── changes/
│   ├── GET    /                    # List change events
│   └── GET    /{id}                # Get change details
│
├── alerts/
│   ├── GET    /                    # List alerts
│   ├── GET    /{id}                # Get alert details
│   └── PATCH  /{id}                # Acknowledge/resolve alert
│
├── discovery/
│   ├── POST   /scans               # Trigger discovery scan
│   ├── GET    /scans               # List scan history
│   └── GET    /scans/{id}          # Get scan status
│
└── admin/
    ├── GET    /health              # Health check
    ├── GET    /metrics             # Prometheus metrics
    └── GET    /config              # Runtime configuration
```

**Configuration Knobs:**

```yaml
api:
  # Server settings
  host: "0.0.0.0"
  port: 8000
  workers: 4

  # Rate limiting
  rate_limiting:
    enabled: true
    backend: "memory"  # "memory" or "redis"
    redis_url: "redis://localhost:6379/2"
    default_limit: "100/minute"
    burst_limit: "20/second"

  # Caching
  cache:
    enabled: true
    backend: "memory"  # "memory" or "redis"
    redis_url: "redis://localhost:6379/3"
    topology_ttl_seconds: 300
    search_ttl_seconds: 60

  # Pagination
  pagination:
    default_page_size: 50
    max_page_size: 1000

  # Authentication
  auth:
    enabled: true
    jwt_secret: "${JWT_SECRET}"
    token_expiry_hours: 24

  # WebSocket
  websocket:
    enabled: true
    ping_interval_seconds: 30
    max_connections: 1000
```

---

## 4. Data Flow Diagrams

### 4.1 Low-Volume Path (PostgreSQL Direct)

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   NetFlow    │────▶│  Flow Ingestion  │────▶│   PostgreSQL     │
│   Exporter   │     │     Service      │     │   (flow_raw)     │
└──────────────┘     └──────────────────┘     └────────┬─────────┘
                                                       │
                     ┌─────────────────────────────────┘
                     │
                     ▼
              ┌──────────────────┐     ┌──────────────────┐
              │   Enrichment     │────▶│   PostgreSQL     │
              │     Service      │     │(assets, deps)    │
              │  (pulls batches) │     │                  │
              └──────────────────┘     └──────────────────┘
                     │
                     ▼
              ┌──────────────────┐     ┌──────────────────┐
              │   Dependency     │────▶│   PostgreSQL     │
              │   Resolution     │     │  (dependencies,  │
              │                  │     │  change_events)  │
              └──────────────────┘     └──────────────────┘
```

**Characteristics:**
- Ingestion writes directly to PostgreSQL `flow_raw` table
- Enrichment service polls for unprocessed flows
- Simple, debuggable, PostgreSQL is single source of truth
- Suitable for < 10,000 flows/sec

### 4.2 High-Volume Path (Kafka Buffered)

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   NetFlow    │────▶│  Flow Ingestion  │────▶│      Kafka       │
│   Exporter   │     │     Service      │     │  (flows.raw)     │
└──────────────┘     └──────────────────┘     └────────┬─────────┘
                                                       │
                     ┌─────────────────────────────────┘
                     │
                     ▼
              ┌──────────────────┐     ┌──────────────────┐
              │   Enrichment     │────▶│      Kafka       │
              │     Service      │     │ (flows.enriched) │
              │ (Kafka consumer) │     │                  │
              └──────────────────┘     └────────┬─────────┘
                                                │
                     ┌──────────────────────────┘
                     │
                     ▼
              ┌──────────────────┐     ┌──────────────────┐
              │   Dependency     │────▶│   PostgreSQL     │
              │   Resolution     │     │  (aggregated     │
              │ (Kafka consumer) │     │   data only)     │
              └──────────────────┘     └──────────────────┘
```

**Characteristics:**
- Ingestion writes to Kafka for durability and buffering
- Services consume from Kafka topics at their own pace
- Raw flows NOT written to PostgreSQL (only aggregates)
- Suitable for 10,000 - 200,000+ flows/sec

---

## 5. PostgreSQL Schema

### 5.1 Core Tables

```sql
-- Assets table
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    name VARCHAR(255),
    fqdn VARCHAR(255),
    asset_type VARCHAR(50) NOT NULL,  -- 'server', 'vm', 'container', 'network_device', 'unknown'

    -- Network identity
    ip_addresses INET[] NOT NULL,
    mac_addresses MACADDR[],

    -- Enrichment data
    os_family VARCHAR(50),
    os_version VARCHAR(100),
    cloud_provider VARCHAR(20),  -- 'aws', 'azure', 'gcp', null
    cloud_region VARCHAR(50),
    cloud_instance_id VARCHAR(100),

    -- Classification
    environment VARCHAR(50),  -- 'production', 'staging', 'development'
    tags JSONB DEFAULT '{}',

    -- Timestamps
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Source tracking
    discovery_source VARCHAR(50) NOT NULL,  -- 'flow', 'scan', 'cloud_api', 'manual'
    confidence REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1)
);

-- Indexes for assets
CREATE INDEX idx_assets_ip_addresses ON assets USING GIN (ip_addresses);
CREATE INDEX idx_assets_type ON assets (asset_type);
CREATE INDEX idx_assets_last_seen ON assets (last_seen);
CREATE INDEX idx_assets_tags ON assets USING GIN (tags);
CREATE INDEX idx_assets_fqdn_trgm ON assets USING GIN (fqdn gin_trgm_ops);
CREATE INDEX idx_assets_name_trgm ON assets USING GIN (name gin_trgm_ops);

-- Dependencies table
CREATE TABLE dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relationship
    source_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    target_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,

    -- Connection details
    protocol SMALLINT NOT NULL,  -- IP protocol number
    port INTEGER NOT NULL,
    inferred_service VARCHAR(50),  -- 'http', 'postgresql', 'redis', etc.

    -- Statistics
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    total_bytes BIGINT DEFAULT 0,
    total_flows BIGINT DEFAULT 0,

    -- Classification
    direction VARCHAR(20) DEFAULT 'outbound',  -- 'outbound', 'inbound', 'bidirectional'
    is_internal BOOLEAN DEFAULT true,

    -- Metadata
    confidence REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    tags JSONB DEFAULT '{}',
    notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint on logical dependency
    UNIQUE (source_asset_id, target_asset_id, protocol, port)
);

-- Indexes for dependencies
CREATE INDEX idx_deps_source ON dependencies (source_asset_id);
CREATE INDEX idx_deps_target ON dependencies (target_asset_id);
CREATE INDEX idx_deps_last_seen ON dependencies (last_seen);
CREATE INDEX idx_deps_port ON dependencies (port);
CREATE INDEX idx_deps_service ON dependencies (inferred_service);

-- Change events table
CREATE TABLE change_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    change_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(20) NOT NULL,  -- 'asset', 'dependency'
    entity_id UUID NOT NULL,

    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    before_state JSONB,
    after_state JSONB,

    -- Processing status
    processed BOOLEAN DEFAULT false,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_changes_detected ON change_events (detected_at);
CREATE INDEX idx_changes_type ON change_events (change_type);
CREATE INDEX idx_changes_entity ON change_events (entity_type, entity_id);
CREATE INDEX idx_changes_unprocessed ON change_events (processed) WHERE processed = false;

-- Alerts table
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    change_event_id UUID REFERENCES change_events(id),
    rule_id UUID,  -- Reference to alert rule (future)

    severity VARCHAR(20) NOT NULL,  -- 'info', 'warning', 'critical'
    title VARCHAR(255) NOT NULL,
    description TEXT,

    status VARCHAR(20) DEFAULT 'open',  -- 'open', 'acknowledged', 'resolved'

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_alerts_status ON alerts (status);
CREATE INDEX idx_alerts_severity ON alerts (severity);
CREATE INDEX idx_alerts_created ON alerts (created_at);

-- Flow statistics (time-series, partitioned)
CREATE TABLE flow_stats (
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    source_asset_id UUID NOT NULL,
    target_asset_id UUID NOT NULL,
    protocol SMALLINT NOT NULL,
    port INTEGER NOT NULL,

    -- Aggregated metrics
    flow_count INTEGER NOT NULL,
    byte_count BIGINT NOT NULL,
    packet_count BIGINT NOT NULL,

    PRIMARY KEY (time, source_asset_id, target_asset_id, protocol, port)
) PARTITION BY RANGE (time);

-- Create partitions (managed by pg_partman or manually)
CREATE TABLE flow_stats_default PARTITION OF flow_stats DEFAULT;

-- Indexes for flow_stats
CREATE INDEX idx_flow_stats_source ON flow_stats (source_asset_id, time);
CREATE INDEX idx_flow_stats_target ON flow_stats (target_asset_id, time);
```

### 5.2 Raw Flow Table (Low-Volume Mode Only)

```sql
-- Only used in PostgreSQL-direct mode (< 10k flows/sec)
CREATE TABLE flow_raw (
    id BIGSERIAL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Flow data
    exporter_ip INET NOT NULL,
    src_ip INET NOT NULL,
    dst_ip INET NOT NULL,
    src_port INTEGER NOT NULL,
    dst_port INTEGER NOT NULL,
    protocol SMALLINT NOT NULL,

    bytes BIGINT NOT NULL,
    packets INTEGER NOT NULL,
    tcp_flags SMALLINT,

    -- Processing status
    processed BOOLEAN DEFAULT false,

    PRIMARY KEY (received_at, id)
) PARTITION BY RANGE (received_at);

-- Partitioned by day, auto-dropped after 7 days
CREATE INDEX idx_flow_raw_unprocessed ON flow_raw (processed) WHERE processed = false;
```

---

## 6. Inter-Service Communication

### 6.1 Communication Patterns

| From | To | Pattern | Protocol |
|------|-----|---------|----------|
| Flow Ingestion | PostgreSQL | Direct | asyncpg |
| Flow Ingestion | Kafka | Producer | aiokafka |
| Enrichment | PostgreSQL | Direct | asyncpg |
| Enrichment | Redis | Cache R/W | aioredis |
| Enrichment | Kafka | Consumer/Producer | aiokafka |
| Dependency Resolution | PostgreSQL | Direct | asyncpg |
| Dependency Resolution | Redis | Aggregation buffer | aioredis |
| Dependency Resolution | Kafka | Consumer | aiokafka |
| Query API | PostgreSQL | Direct | asyncpg |
| Query API | Redis | Cache R/W | aioredis |
| Query API | WebSocket clients | Push | FastAPI WebSocket |

### 6.2 Internal Events (Optional Kafka Topics)

```
flows.raw              # Raw normalized flows from ingestion
flows.enriched         # Flows with DNS, GeoIP, asset correlation
changes.detected       # Change events from dependency resolution
alerts.triggered       # Alert events for notification dispatch
```

### 6.3 Health Check Contract

All services expose:

```
GET /health
{
  "status": "healthy" | "degraded" | "unhealthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "checks": {
    "postgresql": "ok",
    "kafka": "ok" | "not_configured",
    "redis": "ok" | "not_configured"
  }
}

GET /metrics
# Prometheus format
flowlens_flows_received_total{exporter="10.0.0.1"} 123456
flowlens_flows_processed_total 123400
flowlens_processing_latency_seconds{quantile="0.99"} 0.05
```

---

## 7. Deployment Configurations

### 7.1 Minimal Deployment (PostgreSQL Only)

```yaml
# docker-compose.minimal.yml
version: "3.8"

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: flowlens
      POSTGRES_USER: flowlens
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  ingestion:
    image: flowlens/ingestion:latest
    environment:
      FLOWLENS_ROUTING_MODE: postgres
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
    ports:
      - "2055:2055/udp"  # NetFlow
      - "6343:6343/udp"  # sFlow

  enrichment:
    image: flowlens/enrichment:latest
    environment:
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      FLOWLENS_CACHE_BACKEND: memory

  resolution:
    image: flowlens/resolution:latest
    environment:
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      FLOWLENS_BUFFER_BACKEND: memory

  api:
    image: flowlens/api:latest
    environment:
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      FLOWLENS_CACHE_BACKEND: memory
    ports:
      - "8000:8000"

volumes:
  postgres_data:
```

### 7.2 Full Deployment (With Kafka + Redis)

```yaml
# docker-compose.full.yml
version: "3.8"

services:
  postgres:
    image: postgres:15
    # ... same as above

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

  ingestion:
    image: flowlens/ingestion:latest
    environment:
      FLOWLENS_ROUTING_MODE: auto
      FLOWLENS_KAFKA_THRESHOLD: 10000
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    ports:
      - "2055:2055/udp"
      - "6343:6343/udp"

  enrichment:
    image: flowlens/enrichment:latest
    environment:
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      REDIS_URL: redis://redis:6379/0
      FLOWLENS_CACHE_BACKEND: redis

  resolution:
    image: flowlens/resolution:latest
    environment:
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      REDIS_URL: redis://redis:6379/1
      FLOWLENS_BUFFER_BACKEND: redis

  api:
    image: flowlens/api:latest
    environment:
      DATABASE_URL: postgresql://flowlens:${DB_PASSWORD}@postgres:5432/flowlens
      REDIS_URL: redis://redis:6379/2
      FLOWLENS_CACHE_BACKEND: redis
    ports:
      - "8000:8000"

volumes:
  postgres_data:
  redis_data:
```

---

## 8. Service Scaling

### 8.1 Horizontal Scaling Matrix

| Service | Stateless? | Scalable? | Scaling Approach |
|---------|------------|-----------|------------------|
| Flow Ingestion | Yes | Yes | Multiple instances, each on different port or load-balanced UDP |
| Enrichment | Yes | Yes | Kafka consumer group with N partitions |
| Dependency Resolution | Mostly | Yes | Kafka consumer group, Redis for shared state |
| Query API | Yes | Yes | Load balancer (nginx/Traefik) in front of N instances |

### 8.2 Recommended Scaling

```
Flow Rate          Ingestion    Enrichment    Resolution    API
─────────────────────────────────────────────────────────────────
< 5k/sec           1            1             1             1
5k - 20k/sec       2            2             2             2
20k - 50k/sec      4            4             4             2
50k - 100k/sec     8            8             4             4
100k - 200k/sec    16           16            8             4
```

---

*Document maintained by: Engineering Team*
*Last updated: 2024-12-24*
