# FlowLens: Dependency Graph in PostgreSQL

**Version:** 1.0
**Date:** 2024-12-24
**Purpose:** Model application dependencies as a graph in PostgreSQL without a dedicated graph database

---

## 1. Design Overview

### 1.1 Graph Model in PostgreSQL

PostgreSQL can efficiently model graphs using:
- **Node tables:** Represent vertices (assets, services, applications)
- **Edge tables:** Represent relationships (dependencies, connections)
- **Recursive CTEs:** Enable graph traversal (BFS, DFS)
- **Materialized views:** Cache frequently accessed paths

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DEPENDENCY GRAPH DATA MODEL                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  NODES (Vertices)                                                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │   assets    │    │  services   │    │applications │                     │
│  │             │    │             │    │             │                     │
│  │ - Servers   │    │ - Ports     │    │ - Business  │                     │
│  │ - VMs       │◄───│ - Protocols │◄───│   apps      │                     │
│  │ - Containers│    │ - Listeners │    │ - App groups│                     │
│  └─────────────┘    └─────────────┘    └─────────────┘                     │
│         │                  │                  │                             │
│         └──────────────────┴──────────────────┘                             │
│                            │                                                 │
│                            ▼                                                 │
│  EDGES (Relationships)                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      dependencies                                    │   │
│  │  - source_node_id → target_node_id                                  │   │
│  │  - Protocol, port, direction                                        │   │
│  │  - Temporal validity (valid_from, valid_to)                         │   │
│  │  - Aggregated metrics (bytes, packets, sessions)                    │   │
│  │  - Confidence score                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Temporal Model

Dependencies change over time. We track:
- **Current state:** Active dependencies as of now
- **Historical state:** Point-in-time queries
- **Change events:** When dependencies appeared/disappeared

```
Timeline:
─────────────────────────────────────────────────────────────────────────────►
     │                    │                    │                    │
  first_seen          last_seen            valid_from          valid_to
     │                    │                    │                    │
     │◄── Flow observed ─►│                    │◄── Validity ──────►│
     │                    │                    │    (for historical │
     │                    │                    │     queries)       │

States:
- ACTIVE:   valid_to IS NULL AND last_seen > (NOW - stale_threshold)
- STALE:    valid_to IS NULL AND last_seen < (NOW - stale_threshold)
- INACTIVE: valid_to IS NOT NULL
```

---

## 2. Node Tables

### 2.1 Assets Table (Primary Nodes)

```sql
-- ============================================================================
-- ASSETS: Primary graph nodes representing infrastructure entities
-- ============================================================================

CREATE TABLE assets (
    -- Primary key
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    name                VARCHAR(255),
    fqdn                VARCHAR(255),
    display_name        VARCHAR(255) GENERATED ALWAYS AS (
                            COALESCE(name, fqdn, host(ip_addresses[1])::text)
                        ) STORED,

    -- Asset classification
    asset_type          VARCHAR(50) NOT NULL DEFAULT 'unknown',
    asset_subtype       VARCHAR(50),

    -- Network identity (multiple IPs possible for multi-homed hosts)
    ip_addresses        INET[] NOT NULL,
    mac_addresses       MACADDR[],

    -- Canonical IP (first observed or primary)
    primary_ip          INET GENERATED ALWAYS AS (ip_addresses[1]) STORED,

    -- Operating system
    os_family           VARCHAR(50),          -- 'linux', 'windows', 'macos', 'network_os'
    os_name             VARCHAR(100),         -- 'Ubuntu 22.04', 'Windows Server 2022'
    os_version          VARCHAR(50),

    -- Cloud metadata
    cloud_provider      VARCHAR(20),          -- 'aws', 'azure', 'gcp', 'vmware', null
    cloud_region        VARCHAR(50),
    cloud_zone          VARCHAR(50),
    cloud_account_id    VARCHAR(100),
    cloud_instance_id   VARCHAR(100),
    cloud_instance_type VARCHAR(50),

    -- Container metadata
    container_runtime   VARCHAR(20),          -- 'docker', 'containerd', 'cri-o'
    container_id        VARCHAR(100),
    container_name      VARCHAR(255),
    container_image     VARCHAR(500),
    k8s_namespace       VARCHAR(255),
    k8s_pod_name        VARCHAR(255),
    k8s_deployment      VARCHAR(255),

    -- Organization
    environment         VARCHAR(50),          -- 'production', 'staging', 'development', 'test'
    business_unit       VARCHAR(100),
    cost_center         VARCHAR(50),
    owner               VARCHAR(255),

    -- Tags for flexible categorization
    tags                JSONB DEFAULT '{}',
    labels              JSONB DEFAULT '{}',   -- K8s-style labels

    -- Temporal tracking
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Validity window for historical queries
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,          -- NULL = currently valid

    -- Discovery metadata
    discovery_source    VARCHAR(50) NOT NULL DEFAULT 'flow',
    discovery_method    VARCHAR(50),          -- 'netflow', 'api', 'scan', 'manual'
    confidence          REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),

    -- Soft delete
    is_deleted          BOOLEAN DEFAULT FALSE,
    deleted_at          TIMESTAMPTZ,

    -- Graph metrics (denormalized for performance)
    in_degree           INTEGER DEFAULT 0,    -- Number of incoming dependencies
    out_degree          INTEGER DEFAULT 0,    -- Number of outgoing dependencies

    -- Constraints
    CONSTRAINT assets_ip_not_empty CHECK (array_length(ip_addresses, 1) > 0),
    CONSTRAINT assets_valid_range CHECK (valid_from <= COALESCE(valid_to, 'infinity'::timestamptz))
);

-- Asset type constants
COMMENT ON COLUMN assets.asset_type IS 'Types: server, vm, container, pod, network_device, load_balancer, database, storage, unknown';

-- Indexes for assets
CREATE INDEX idx_assets_primary_ip ON assets (primary_ip) WHERE NOT is_deleted;
CREATE INDEX idx_assets_ip_gin ON assets USING GIN (ip_addresses) WHERE NOT is_deleted;
CREATE INDEX idx_assets_type ON assets (asset_type) WHERE NOT is_deleted;
CREATE INDEX idx_assets_env ON assets (environment) WHERE NOT is_deleted;
CREATE INDEX idx_assets_last_seen ON assets (last_seen DESC) WHERE NOT is_deleted;
CREATE INDEX idx_assets_cloud ON assets (cloud_provider, cloud_region) WHERE cloud_provider IS NOT NULL;
CREATE INDEX idx_assets_k8s ON assets (k8s_namespace, k8s_deployment) WHERE k8s_namespace IS NOT NULL;
CREATE INDEX idx_assets_tags ON assets USING GIN (tags);
CREATE INDEX idx_assets_labels ON assets USING GIN (labels);

-- Full-text search
CREATE INDEX idx_assets_fts ON assets USING GIN (
    to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(fqdn, '') || ' ' || COALESCE(k8s_pod_name, ''))
);

-- Temporal queries
CREATE INDEX idx_assets_temporal ON assets (valid_from, valid_to);
CREATE INDEX idx_assets_valid_current ON assets (id)
    WHERE valid_to IS NULL AND NOT is_deleted;
```

### 2.2 Services Table (Logical Services)

```sql
-- ============================================================================
-- SERVICES: Logical services running on assets (listening ports)
-- ============================================================================

CREATE TABLE services (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Parent asset
    asset_id            UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,

    -- Service identity
    name                VARCHAR(255),         -- Inferred or configured name
    service_type        VARCHAR(50),          -- 'http', 'database', 'cache', 'queue', etc.

    -- Network binding
    listen_ip           INET,                 -- NULL = all interfaces (0.0.0.0)
    listen_port         INTEGER NOT NULL,
    protocol            SMALLINT NOT NULL DEFAULT 6,  -- IP protocol (6=TCP, 17=UDP)

    -- Protocol details
    application_protocol VARCHAR(50),         -- 'http', 'https', 'postgresql', 'mysql', etc.
    tls_enabled         BOOLEAN DEFAULT FALSE,

    -- Process information (if available from discovery)
    process_name        VARCHAR(255),
    process_pid         INTEGER,
    process_user        VARCHAR(100),
    process_cmdline     TEXT,

    -- Software details
    software_name       VARCHAR(255),         -- 'nginx', 'postgresql', 'redis'
    software_version    VARCHAR(100),
    software_vendor     VARCHAR(100),

    -- Temporal
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,

    -- Discovery
    discovery_source    VARCHAR(50) NOT NULL DEFAULT 'flow',
    confidence          REAL DEFAULT 0.5,

    is_deleted          BOOLEAN DEFAULT FALSE,

    -- Unique constraint per asset/port/protocol
    UNIQUE (asset_id, listen_port, protocol, valid_from)
);

CREATE INDEX idx_services_asset ON services (asset_id) WHERE NOT is_deleted;
CREATE INDEX idx_services_port ON services (listen_port, protocol) WHERE NOT is_deleted;
CREATE INDEX idx_services_type ON services (service_type) WHERE NOT is_deleted;
CREATE INDEX idx_services_app_proto ON services (application_protocol) WHERE NOT is_deleted;
```

### 2.3 Applications Table (Business Applications)

```sql
-- ============================================================================
-- APPLICATIONS: Business applications grouping multiple assets/services
-- ============================================================================

CREATE TABLE applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    name                VARCHAR(255) NOT NULL,
    code                VARCHAR(50) UNIQUE,   -- Short code (e.g., 'PAYROLL', 'CRM')
    description         TEXT,

    -- Classification
    app_type            VARCHAR(50),          -- 'web', 'api', 'batch', 'database', 'infrastructure'
    tier                VARCHAR(20),          -- 'frontend', 'backend', 'data', 'infrastructure'
    criticality         VARCHAR(20),          -- 'critical', 'high', 'medium', 'low'

    -- Ownership
    owner               VARCHAR(255),
    owner_email         VARCHAR(255),
    team                VARCHAR(100),
    business_unit       VARCHAR(100),
    cost_center         VARCHAR(50),

    -- Environment classification
    environment         VARCHAR(50),

    -- Tags
    tags                JSONB DEFAULT '{}',

    -- Temporal
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,

    -- Source
    discovery_source    VARCHAR(50) DEFAULT 'manual',  -- Usually manual or CMDB import
    external_id         VARCHAR(255),                  -- ID from external system (ServiceNow, etc.)

    is_deleted          BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_applications_name ON applications (name) WHERE NOT is_deleted;
CREATE INDEX idx_applications_code ON applications (code) WHERE NOT is_deleted;
CREATE INDEX idx_applications_team ON applications (team) WHERE NOT is_deleted;
CREATE INDEX idx_applications_tags ON applications USING GIN (tags);
```

### 2.4 Application Membership (Assets ↔ Applications)

```sql
-- ============================================================================
-- APPLICATION_MEMBERS: Many-to-many relationship between assets and applications
-- ============================================================================

CREATE TABLE application_members (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    application_id      UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    asset_id            UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,

    -- Role within the application
    role                VARCHAR(50),          -- 'web_server', 'app_server', 'database', 'cache'

    -- Temporal validity
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,

    -- Discovery
    discovery_source    VARCHAR(50) DEFAULT 'manual',
    confidence          REAL DEFAULT 1.0,

    UNIQUE (application_id, asset_id, valid_from)
);

CREATE INDEX idx_app_members_app ON application_members (application_id);
CREATE INDEX idx_app_members_asset ON application_members (asset_id);
CREATE INDEX idx_app_members_valid ON application_members (application_id)
    WHERE valid_to IS NULL;
```

---

## 3. Edge Tables

### 3.1 Dependencies Table (Primary Edges)

```sql
-- ============================================================================
-- DEPENDENCIES: Directed edges representing connections between assets
-- ============================================================================

CREATE TABLE dependencies (
    -- Primary key
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Edge endpoints (source depends on target, or source connects to target)
    source_asset_id     UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    target_asset_id     UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,

    -- Connection details (for disambiguation)
    source_ip           INET NOT NULL,
    target_ip           INET NOT NULL,
    target_port         INTEGER NOT NULL,
    protocol            SMALLINT NOT NULL DEFAULT 6,  -- IP protocol number

    -- Optional service reference
    target_service_id   UUID REFERENCES services(id) ON DELETE SET NULL,

    -- Inferred application protocol
    application_protocol VARCHAR(50),         -- 'http', 'postgresql', 'redis', etc.

    -- Direction and classification
    direction           VARCHAR(20) DEFAULT 'outbound',  -- 'outbound', 'inbound', 'bidirectional'
    is_internal         BOOLEAN DEFAULT TRUE,            -- Both endpoints are internal
    traffic_class       VARCHAR(50),                     -- 'database', 'api', 'web', 'storage', etc.

    -- =========================================================================
    -- AGGREGATION FIELDS
    -- =========================================================================

    -- Traffic metrics (cumulative since first_seen)
    bytes_total         BIGINT DEFAULT 0,
    packets_total       BIGINT DEFAULT 0,
    flows_total         BIGINT DEFAULT 0,

    -- Session metrics (for TCP)
    sessions_total      BIGINT DEFAULT 0,
    sessions_active     INTEGER DEFAULT 0,    -- Currently active (estimated)

    -- Recent metrics (rolling 24-hour window, updated periodically)
    bytes_last_24h      BIGINT DEFAULT 0,
    packets_last_24h    BIGINT DEFAULT 0,
    flows_last_24h      BIGINT DEFAULT 0,

    -- Rate metrics (calculated, flows per hour)
    avg_flows_per_hour  REAL DEFAULT 0,
    peak_flows_per_hour REAL DEFAULT 0,

    -- Byte rate metrics
    avg_bytes_per_sec   REAL DEFAULT 0,
    peak_bytes_per_sec  REAL DEFAULT 0,

    -- =========================================================================
    -- TEMPORAL VALIDITY
    -- =========================================================================

    -- When dependency was first and last observed
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Validity window for historical queries
    -- valid_to = NULL means currently valid
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,

    -- Standard timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- =========================================================================
    -- METADATA
    -- =========================================================================

    -- Confidence score (0.0 - 1.0)
    -- Higher = more certain this is a real dependency
    confidence          REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),

    -- How was this dependency discovered?
    discovery_source    VARCHAR(50) NOT NULL DEFAULT 'flow',  -- 'flow', 'scan', 'manual', 'api'

    -- User-provided metadata
    tags                JSONB DEFAULT '{}',
    notes               TEXT,

    -- Manual override flags
    is_manual           BOOLEAN DEFAULT FALSE,    -- Manually declared, not discovered
    is_verified         BOOLEAN DEFAULT FALSE,    -- User verified as correct
    is_suppressed       BOOLEAN DEFAULT FALSE,    -- User suppressed from views

    -- Soft delete
    is_deleted          BOOLEAN DEFAULT FALSE,
    deleted_at          TIMESTAMPTZ,

    -- =========================================================================
    -- CONSTRAINTS
    -- =========================================================================

    -- Prevent self-loops
    CONSTRAINT no_self_dependency CHECK (source_asset_id != target_asset_id),

    -- Valid temporal range
    CONSTRAINT valid_temporal_range CHECK (
        first_seen <= last_seen AND
        valid_from <= COALESCE(valid_to, 'infinity'::timestamptz)
    ),

    -- Unique edge per source/target/port/protocol/validity window
    UNIQUE (source_asset_id, target_asset_id, target_port, protocol, valid_from)
);

-- Primary lookup: Find all dependencies for an asset
CREATE INDEX idx_deps_source ON dependencies (source_asset_id, last_seen DESC)
    WHERE NOT is_deleted AND valid_to IS NULL;
CREATE INDEX idx_deps_target ON dependencies (target_asset_id, last_seen DESC)
    WHERE NOT is_deleted AND valid_to IS NULL;

-- Pair lookup: Specific source-target pair
CREATE INDEX idx_deps_pair ON dependencies (source_asset_id, target_asset_id)
    WHERE NOT is_deleted AND valid_to IS NULL;

-- Port-based queries
CREATE INDEX idx_deps_port ON dependencies (target_port, protocol)
    WHERE NOT is_deleted AND valid_to IS NULL;

-- Protocol-based queries
CREATE INDEX idx_deps_app_proto ON dependencies (application_protocol)
    WHERE application_protocol IS NOT NULL AND NOT is_deleted;

-- Traffic class queries
CREATE INDEX idx_deps_traffic_class ON dependencies (traffic_class)
    WHERE traffic_class IS NOT NULL AND NOT is_deleted;

-- Temporal queries
CREATE INDEX idx_deps_temporal ON dependencies (valid_from, valid_to);
CREATE INDEX idx_deps_last_seen ON dependencies (last_seen DESC)
    WHERE NOT is_deleted;

-- Active dependencies only
CREATE INDEX idx_deps_active ON dependencies (source_asset_id, target_asset_id)
    WHERE valid_to IS NULL AND NOT is_deleted AND NOT is_suppressed;

-- High-traffic dependencies
CREATE INDEX idx_deps_high_traffic ON dependencies (bytes_total DESC)
    WHERE valid_to IS NULL AND NOT is_deleted;

-- Tags and metadata
CREATE INDEX idx_deps_tags ON dependencies USING GIN (tags);
```

### 3.2 Dependency History (Temporal Audit)

```sql
-- ============================================================================
-- DEPENDENCY_HISTORY: Audit trail for dependency changes
-- ============================================================================

CREATE TABLE dependency_history (
    id                  BIGSERIAL PRIMARY KEY,

    dependency_id       UUID NOT NULL,        -- Reference to dependencies.id
    operation           VARCHAR(10) NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by          VARCHAR(100),         -- User or system

    -- Snapshot of relevant fields at time of change
    source_asset_id     UUID,
    target_asset_id     UUID,
    target_port         INTEGER,
    protocol            SMALLINT,

    -- Metrics at time of change
    bytes_total         BIGINT,
    flows_total         BIGINT,

    -- Validity at time of change
    valid_from          TIMESTAMPTZ,
    valid_to            TIMESTAMPTZ,

    -- Full row as JSON for complete audit
    row_data            JSONB NOT NULL
);

CREATE INDEX idx_dep_history_dep ON dependency_history (dependency_id, changed_at DESC);
CREATE INDEX idx_dep_history_time ON dependency_history (changed_at DESC);

-- Trigger to maintain history
CREATE OR REPLACE FUNCTION track_dependency_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO dependency_history (
            dependency_id, operation, row_data,
            source_asset_id, target_asset_id, target_port, protocol,
            bytes_total, flows_total, valid_from, valid_to
        ) VALUES (
            OLD.id, 'DELETE', to_jsonb(OLD),
            OLD.source_asset_id, OLD.target_asset_id, OLD.target_port, OLD.protocol,
            OLD.bytes_total, OLD.flows_total, OLD.valid_from, OLD.valid_to
        );
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO dependency_history (
            dependency_id, operation, row_data,
            source_asset_id, target_asset_id, target_port, protocol,
            bytes_total, flows_total, valid_from, valid_to
        ) VALUES (
            NEW.id, 'UPDATE', to_jsonb(NEW),
            NEW.source_asset_id, NEW.target_asset_id, NEW.target_port, NEW.protocol,
            NEW.bytes_total, NEW.flows_total, NEW.valid_from, NEW.valid_to
        );
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO dependency_history (
            dependency_id, operation, row_data,
            source_asset_id, target_asset_id, target_port, protocol,
            bytes_total, flows_total, valid_from, valid_to
        ) VALUES (
            NEW.id, 'INSERT', to_jsonb(NEW),
            NEW.source_asset_id, NEW.target_asset_id, NEW.target_port, NEW.protocol,
            NEW.bytes_total, NEW.flows_total, NEW.valid_from, NEW.valid_to
        );
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER dependency_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON dependencies
FOR EACH ROW EXECUTE FUNCTION track_dependency_changes();
```

### 3.3 Application Dependencies (Higher-Level Edges)

```sql
-- ============================================================================
-- APPLICATION_DEPENDENCIES: Dependencies between business applications
-- Derived from asset-level dependencies, or manually declared
-- ============================================================================

CREATE TABLE application_dependencies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_app_id       UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    target_app_id       UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,

    -- Dependency classification
    dependency_type     VARCHAR(50),          -- 'api', 'database', 'queue', 'file', 'network'
    criticality         VARCHAR(20),          -- 'critical', 'high', 'medium', 'low'
    is_synchronous      BOOLEAN DEFAULT TRUE, -- Sync vs async dependency

    -- Aggregated from underlying asset dependencies
    asset_dependency_count INTEGER DEFAULT 0,

    -- Aggregated traffic
    bytes_total         BIGINT DEFAULT 0,
    bytes_last_24h      BIGINT DEFAULT 0,

    -- Temporal
    first_seen          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,

    -- Source
    discovery_source    VARCHAR(50) DEFAULT 'derived',  -- 'derived', 'manual', 'cmdb'

    -- User metadata
    notes               TEXT,
    tags                JSONB DEFAULT '{}',

    is_deleted          BOOLEAN DEFAULT FALSE,

    CONSTRAINT no_self_app_dep CHECK (source_app_id != target_app_id),
    UNIQUE (source_app_id, target_app_id, valid_from)
);

CREATE INDEX idx_app_deps_source ON application_dependencies (source_app_id)
    WHERE NOT is_deleted AND valid_to IS NULL;
CREATE INDEX idx_app_deps_target ON application_dependencies (target_app_id)
    WHERE NOT is_deleted AND valid_to IS NULL;
```

---

## 4. Graph Traversal Queries

### 4.1 Basic Traversals

```sql
-- ============================================================================
-- QUERY: Direct dependencies (1-hop)
-- ============================================================================

-- Find all assets that a given asset depends on (outgoing)
SELECT
    t.id,
    t.name,
    t.primary_ip,
    t.asset_type,
    d.target_port,
    d.application_protocol,
    d.bytes_last_24h,
    d.last_seen
FROM dependencies d
JOIN assets t ON d.target_asset_id = t.id
WHERE d.source_asset_id = '550e8400-e29b-41d4-a716-446655440000'  -- Source asset UUID
  AND d.valid_to IS NULL
  AND NOT d.is_deleted
  AND NOT t.is_deleted
ORDER BY d.bytes_last_24h DESC;

-- Find all assets that depend on a given asset (incoming)
SELECT
    s.id,
    s.name,
    s.primary_ip,
    s.asset_type,
    d.target_port,
    d.application_protocol,
    d.bytes_last_24h,
    d.last_seen
FROM dependencies d
JOIN assets s ON d.source_asset_id = s.id
WHERE d.target_asset_id = '550e8400-e29b-41d4-a716-446655440000'  -- Target asset UUID
  AND d.valid_to IS NULL
  AND NOT d.is_deleted
  AND NOT s.is_deleted
ORDER BY d.bytes_last_24h DESC;
```

### 4.2 Multi-Hop Traversal (Recursive CTE)

```sql
-- ============================================================================
-- QUERY: Upstream dependencies (what does X depend on, recursively)
-- ============================================================================

WITH RECURSIVE upstream AS (
    -- Base case: direct dependencies of the starting asset
    SELECT
        d.source_asset_id,
        d.target_asset_id,
        d.target_port,
        d.application_protocol,
        d.bytes_last_24h,
        1 AS depth,
        ARRAY[d.source_asset_id] AS path,
        FALSE AS has_cycle
    FROM dependencies d
    WHERE d.source_asset_id = '550e8400-e29b-41d4-a716-446655440000'
      AND d.valid_to IS NULL
      AND NOT d.is_deleted

    UNION ALL

    -- Recursive case: dependencies of dependencies
    SELECT
        d.source_asset_id,
        d.target_asset_id,
        d.target_port,
        d.application_protocol,
        d.bytes_last_24h,
        u.depth + 1,
        u.path || d.source_asset_id,
        d.target_asset_id = ANY(u.path) AS has_cycle
    FROM dependencies d
    JOIN upstream u ON d.source_asset_id = u.target_asset_id
    WHERE u.depth < 10                      -- Max depth limit
      AND NOT u.has_cycle                   -- Prevent infinite loops
      AND d.valid_to IS NULL
      AND NOT d.is_deleted
)
SELECT DISTINCT ON (target_asset_id)
    u.target_asset_id,
    a.name,
    a.primary_ip,
    a.asset_type,
    u.target_port,
    u.application_protocol,
    u.depth,
    u.path
FROM upstream u
JOIN assets a ON u.target_asset_id = a.id
WHERE NOT a.is_deleted
ORDER BY target_asset_id, depth;  -- Shortest path to each asset

-- ============================================================================
-- QUERY: Downstream dependencies (what depends on X, recursively)
-- ============================================================================

WITH RECURSIVE downstream AS (
    -- Base case: assets that directly depend on the starting asset
    SELECT
        d.source_asset_id,
        d.target_asset_id,
        d.target_port,
        d.application_protocol,
        1 AS depth,
        ARRAY[d.target_asset_id] AS path,
        FALSE AS has_cycle
    FROM dependencies d
    WHERE d.target_asset_id = '550e8400-e29b-41d4-a716-446655440000'
      AND d.valid_to IS NULL
      AND NOT d.is_deleted

    UNION ALL

    -- Recursive case: assets that depend on those assets
    SELECT
        d.source_asset_id,
        d.target_asset_id,
        d.target_port,
        d.application_protocol,
        ds.depth + 1,
        ds.path || d.target_asset_id,
        d.source_asset_id = ANY(ds.path) AS has_cycle
    FROM dependencies d
    JOIN downstream ds ON d.target_asset_id = ds.source_asset_id
    WHERE ds.depth < 10
      AND NOT ds.has_cycle
      AND d.valid_to IS NULL
      AND NOT d.is_deleted
)
SELECT DISTINCT ON (source_asset_id)
    ds.source_asset_id,
    a.name,
    a.primary_ip,
    a.asset_type,
    ds.depth,
    ds.path
FROM downstream ds
JOIN assets a ON ds.source_asset_id = a.id
WHERE NOT a.is_deleted
ORDER BY source_asset_id, depth;
```

### 4.3 Blast Radius Calculation

```sql
-- ============================================================================
-- QUERY: Blast radius - all assets affected if target asset fails
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_blast_radius(
    p_asset_id UUID,
    p_max_depth INTEGER DEFAULT 5
)
RETURNS TABLE (
    asset_id UUID,
    asset_name VARCHAR(255),
    primary_ip INET,
    asset_type VARCHAR(50),
    depth INTEGER,
    impact_path UUID[],
    dependency_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE blast_radius AS (
        -- Base case: assets that directly depend on the failing asset
        SELECT
            d.source_asset_id AS affected_asset_id,
            1 AS depth,
            ARRAY[p_asset_id, d.source_asset_id] AS path
        FROM dependencies d
        WHERE d.target_asset_id = p_asset_id
          AND d.valid_to IS NULL
          AND NOT d.is_deleted

        UNION

        -- Recursive case: cascade up the dependency chain
        SELECT
            d.source_asset_id,
            br.depth + 1,
            br.path || d.source_asset_id
        FROM dependencies d
        JOIN blast_radius br ON d.target_asset_id = br.affected_asset_id
        WHERE br.depth < p_max_depth
          AND NOT d.source_asset_id = ANY(br.path)  -- Cycle prevention
          AND d.valid_to IS NULL
          AND NOT d.is_deleted
    )
    SELECT DISTINCT ON (br.affected_asset_id)
        br.affected_asset_id,
        a.name,
        a.primary_ip,
        a.asset_type,
        br.depth,
        br.path,
        (SELECT COUNT(*) FROM dependencies d2
         WHERE d2.source_asset_id = br.affected_asset_id
           AND d2.valid_to IS NULL
           AND NOT d2.is_deleted) as dependency_count
    FROM blast_radius br
    JOIN assets a ON br.affected_asset_id = a.id
    WHERE NOT a.is_deleted
    ORDER BY br.affected_asset_id, br.depth;  -- Shortest path
END;
$$ LANGUAGE plpgsql;

-- Usage:
SELECT * FROM calculate_blast_radius('550e8400-e29b-41d4-a716-446655440000', 3);
```

### 4.4 Shortest Path Between Two Assets

```sql
-- ============================================================================
-- QUERY: Find shortest path between two assets
-- ============================================================================

CREATE OR REPLACE FUNCTION find_dependency_path(
    p_source_id UUID,
    p_target_id UUID,
    p_max_depth INTEGER DEFAULT 10
)
RETURNS TABLE (
    path UUID[],
    path_length INTEGER,
    path_ports INTEGER[],
    path_protocols VARCHAR(50)[]
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE path_search AS (
        -- Start from source
        SELECT
            ARRAY[p_source_id] AS path,
            ARRAY[]::INTEGER[] AS ports,
            ARRAY[]::VARCHAR(50)[] AS protocols,
            p_source_id AS current_node,
            FALSE AS found
        WHERE EXISTS (SELECT 1 FROM assets WHERE id = p_source_id AND NOT is_deleted)

        UNION ALL

        -- Explore edges
        SELECT
            ps.path || d.target_asset_id,
            ps.ports || d.target_port,
            ps.protocols || d.application_protocol,
            d.target_asset_id,
            d.target_asset_id = p_target_id
        FROM path_search ps
        JOIN dependencies d ON d.source_asset_id = ps.current_node
        WHERE array_length(ps.path, 1) < p_max_depth
          AND NOT d.target_asset_id = ANY(ps.path)  -- No cycles
          AND NOT ps.found
          AND d.valid_to IS NULL
          AND NOT d.is_deleted
    )
    SELECT
        ps.path,
        array_length(ps.path, 1) AS path_length,
        ps.ports,
        ps.protocols
    FROM path_search ps
    WHERE ps.found
    ORDER BY array_length(ps.path, 1)
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Usage:
SELECT * FROM find_dependency_path(
    '550e8400-e29b-41d4-a716-446655440000',  -- Source
    '550e8400-e29b-41d4-a716-446655440001'   -- Target
);
```

### 4.5 Single Points of Failure Detection

```sql
-- ============================================================================
-- QUERY: Find single points of failure (high in-degree nodes)
-- ============================================================================

-- Simple SPOF detection: Assets with many dependents
SELECT
    a.id,
    a.name,
    a.primary_ip,
    a.asset_type,
    a.environment,
    COUNT(DISTINCT d.source_asset_id) AS dependent_count,
    SUM(d.bytes_last_24h) AS total_bytes_from_dependents
FROM assets a
JOIN dependencies d ON d.target_asset_id = a.id
WHERE a.valid_to IS NULL
  AND NOT a.is_deleted
  AND d.valid_to IS NULL
  AND NOT d.is_deleted
GROUP BY a.id
HAVING COUNT(DISTINCT d.source_asset_id) >= 5  -- Threshold for SPOF
ORDER BY dependent_count DESC
LIMIT 20;

-- Advanced SPOF: Graph centrality (betweenness approximation)
-- This finds assets that lie on many shortest paths
CREATE OR REPLACE FUNCTION find_critical_nodes(
    p_sample_size INTEGER DEFAULT 100
)
RETURNS TABLE (
    asset_id UUID,
    asset_name VARCHAR(255),
    betweenness_score REAL,
    in_degree INTEGER,
    out_degree INTEGER
) AS $$
DECLARE
    sample_pairs RECORD;
    path_result RECORD;
    centrality JSONB := '{}';
BEGIN
    -- Sample random source-target pairs
    FOR sample_pairs IN
        SELECT
            s.id AS source_id,
            t.id AS target_id
        FROM assets s
        CROSS JOIN assets t
        WHERE s.id != t.id
          AND NOT s.is_deleted
          AND NOT t.is_deleted
          AND s.valid_to IS NULL
          AND t.valid_to IS NULL
        ORDER BY RANDOM()
        LIMIT p_sample_size
    LOOP
        -- Find path between pair
        SELECT * INTO path_result
        FROM find_dependency_path(sample_pairs.source_id, sample_pairs.target_id, 5);

        -- Increment centrality for each node on path
        IF path_result.path IS NOT NULL THEN
            FOR i IN 2..array_length(path_result.path, 1) - 1 LOOP
                centrality := jsonb_set(
                    centrality,
                    ARRAY[path_result.path[i]::text],
                    to_jsonb(COALESCE((centrality->>path_result.path[i]::text)::int, 0) + 1)
                );
            END LOOP;
        END IF;
    END LOOP;

    -- Return results
    RETURN QUERY
    SELECT
        a.id,
        a.name,
        COALESCE((centrality->>a.id::text)::real, 0) / p_sample_size AS betweenness_score,
        a.in_degree,
        a.out_degree
    FROM assets a
    WHERE NOT a.is_deleted
      AND a.valid_to IS NULL
    ORDER BY (centrality->>a.id::text)::real DESC NULLS LAST
    LIMIT 20;
END;
$$ LANGUAGE plpgsql;
```

### 4.6 Point-in-Time Queries (Historical)

```sql
-- ============================================================================
-- QUERY: Dependencies as they existed at a specific point in time
-- ============================================================================

CREATE OR REPLACE FUNCTION get_dependencies_at_time(
    p_asset_id UUID,
    p_timestamp TIMESTAMPTZ,
    p_direction VARCHAR(10) DEFAULT 'both'  -- 'upstream', 'downstream', 'both'
)
RETURNS TABLE (
    dependency_id UUID,
    source_asset_id UUID,
    source_name VARCHAR(255),
    target_asset_id UUID,
    target_name VARCHAR(255),
    target_port INTEGER,
    application_protocol VARCHAR(50),
    bytes_total BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.source_asset_id,
        s.name,
        d.target_asset_id,
        t.name,
        d.target_port,
        d.application_protocol,
        d.bytes_total
    FROM dependencies d
    JOIN assets s ON d.source_asset_id = s.id
    JOIN assets t ON d.target_asset_id = t.id
    WHERE (
        (p_direction IN ('upstream', 'both') AND d.source_asset_id = p_asset_id)
        OR
        (p_direction IN ('downstream', 'both') AND d.target_asset_id = p_asset_id)
    )
    AND d.valid_from <= p_timestamp
    AND (d.valid_to IS NULL OR d.valid_to > p_timestamp)
    AND s.valid_from <= p_timestamp
    AND (s.valid_to IS NULL OR s.valid_to > p_timestamp)
    AND t.valid_from <= p_timestamp
    AND (t.valid_to IS NULL OR t.valid_to > p_timestamp);
END;
$$ LANGUAGE plpgsql;

-- Usage: Get dependencies as they were 1 week ago
SELECT * FROM get_dependencies_at_time(
    '550e8400-e29b-41d4-a716-446655440000',
    NOW() - INTERVAL '7 days',
    'both'
);
```

### 4.7 Dependency Diff (What Changed?)

```sql
-- ============================================================================
-- QUERY: Compare dependencies between two points in time
-- ============================================================================

CREATE OR REPLACE FUNCTION diff_dependencies(
    p_asset_id UUID,
    p_time_before TIMESTAMPTZ,
    p_time_after TIMESTAMPTZ
)
RETURNS TABLE (
    change_type VARCHAR(10),  -- 'added', 'removed', 'modified'
    dependency_id UUID,
    target_asset_id UUID,
    target_name VARCHAR(255),
    target_port INTEGER,
    bytes_before BIGINT,
    bytes_after BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH deps_before AS (
        SELECT d.*, t.name AS target_name
        FROM dependencies d
        JOIN assets t ON d.target_asset_id = t.id
        WHERE d.source_asset_id = p_asset_id
          AND d.valid_from <= p_time_before
          AND (d.valid_to IS NULL OR d.valid_to > p_time_before)
    ),
    deps_after AS (
        SELECT d.*, t.name AS target_name
        FROM dependencies d
        JOIN assets t ON d.target_asset_id = t.id
        WHERE d.source_asset_id = p_asset_id
          AND d.valid_from <= p_time_after
          AND (d.valid_to IS NULL OR d.valid_to > p_time_after)
    )
    -- Added dependencies
    SELECT
        'added'::VARCHAR(10),
        a.id,
        a.target_asset_id,
        a.target_name,
        a.target_port,
        NULL::BIGINT,
        a.bytes_total
    FROM deps_after a
    WHERE NOT EXISTS (
        SELECT 1 FROM deps_before b
        WHERE b.target_asset_id = a.target_asset_id
          AND b.target_port = a.target_port
    )

    UNION ALL

    -- Removed dependencies
    SELECT
        'removed'::VARCHAR(10),
        b.id,
        b.target_asset_id,
        b.target_name,
        b.target_port,
        b.bytes_total,
        NULL::BIGINT
    FROM deps_before b
    WHERE NOT EXISTS (
        SELECT 1 FROM deps_after a
        WHERE a.target_asset_id = b.target_asset_id
          AND a.target_port = b.target_port
    )

    UNION ALL

    -- Modified dependencies (significant traffic change)
    SELECT
        'modified'::VARCHAR(10),
        a.id,
        a.target_asset_id,
        a.target_name,
        a.target_port,
        b.bytes_total,
        a.bytes_total
    FROM deps_after a
    JOIN deps_before b ON (
        a.target_asset_id = b.target_asset_id
        AND a.target_port = b.target_port
    )
    WHERE ABS(a.bytes_total - b.bytes_total) > 1000000000;  -- 1GB change threshold
END;
$$ LANGUAGE plpgsql;

-- Usage: What changed in last 7 days?
SELECT * FROM diff_dependencies(
    '550e8400-e29b-41d4-a716-446655440000',
    NOW() - INTERVAL '7 days',
    NOW()
);
```

---

## 5. Materialized Views for Performance

### 5.1 Active Dependencies View

```sql
-- ============================================================================
-- MATERIALIZED VIEW: Active dependencies (refreshed periodically)
-- ============================================================================

CREATE MATERIALIZED VIEW mv_active_dependencies AS
SELECT
    d.id,
    d.source_asset_id,
    s.name AS source_name,
    s.primary_ip AS source_ip,
    s.asset_type AS source_type,
    d.target_asset_id,
    t.name AS target_name,
    t.primary_ip AS target_ip,
    t.asset_type AS target_type,
    d.target_port,
    d.protocol,
    d.application_protocol,
    d.bytes_total,
    d.bytes_last_24h,
    d.flows_total,
    d.first_seen,
    d.last_seen,
    d.confidence,
    d.is_internal,
    d.traffic_class
FROM dependencies d
JOIN assets s ON d.source_asset_id = s.id
JOIN assets t ON d.target_asset_id = t.id
WHERE d.valid_to IS NULL
  AND NOT d.is_deleted
  AND NOT d.is_suppressed
  AND NOT s.is_deleted
  AND NOT t.is_deleted
  AND s.valid_to IS NULL
  AND t.valid_to IS NULL;

CREATE UNIQUE INDEX idx_mv_active_deps_id ON mv_active_dependencies (id);
CREATE INDEX idx_mv_active_deps_source ON mv_active_dependencies (source_asset_id);
CREATE INDEX idx_mv_active_deps_target ON mv_active_dependencies (target_asset_id);
CREATE INDEX idx_mv_active_deps_port ON mv_active_dependencies (target_port);

-- Refresh function
CREATE OR REPLACE PROCEDURE refresh_active_dependencies()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_active_dependencies;
END;
$$;

-- Schedule refresh every 5 minutes
-- SELECT cron.schedule('*/5 * * * *', 'CALL refresh_active_dependencies()');
```

### 5.2 Topology Graph View

```sql
-- ============================================================================
-- MATERIALIZED VIEW: Graph structure for visualization
-- ============================================================================

CREATE MATERIALIZED VIEW mv_topology_graph AS
WITH nodes AS (
    SELECT
        a.id,
        a.name,
        a.display_name,
        a.primary_ip,
        a.asset_type,
        a.environment,
        a.in_degree,
        a.out_degree,
        a.tags,
        CASE
            WHEN a.last_seen > NOW() - INTERVAL '1 hour' THEN 'active'
            WHEN a.last_seen > NOW() - INTERVAL '24 hours' THEN 'recent'
            ELSE 'stale'
        END AS status
    FROM assets a
    WHERE a.valid_to IS NULL
      AND NOT a.is_deleted
),
edges AS (
    SELECT
        d.id,
        d.source_asset_id,
        d.target_asset_id,
        d.target_port,
        d.application_protocol,
        d.bytes_last_24h,
        d.last_seen,
        CASE
            WHEN d.last_seen > NOW() - INTERVAL '1 hour' THEN 'active'
            WHEN d.last_seen > NOW() - INTERVAL '24 hours' THEN 'recent'
            ELSE 'stale'
        END AS status
    FROM dependencies d
    WHERE d.valid_to IS NULL
      AND NOT d.is_deleted
      AND NOT d.is_suppressed
)
SELECT
    'node' AS element_type,
    n.id::text AS element_id,
    jsonb_build_object(
        'id', n.id,
        'name', n.display_name,
        'ip', n.primary_ip,
        'type', n.asset_type,
        'environment', n.environment,
        'in_degree', n.in_degree,
        'out_degree', n.out_degree,
        'status', n.status,
        'tags', n.tags
    ) AS data
FROM nodes n

UNION ALL

SELECT
    'edge' AS element_type,
    e.id::text AS element_id,
    jsonb_build_object(
        'id', e.id,
        'source', e.source_asset_id,
        'target', e.target_asset_id,
        'port', e.target_port,
        'protocol', e.application_protocol,
        'bytes_24h', e.bytes_last_24h,
        'status', e.status
    ) AS data
FROM edges e;

CREATE INDEX idx_mv_topology_type ON mv_topology_graph (element_type);
CREATE INDEX idx_mv_topology_data ON mv_topology_graph USING GIN (data);
```

---

## 6. Maintenance Procedures

### 6.1 Update Aggregation Fields

```sql
-- ============================================================================
-- PROCEDURE: Update rolling metrics on dependencies
-- ============================================================================

CREATE OR REPLACE PROCEDURE update_dependency_metrics()
LANGUAGE plpgsql AS $$
BEGIN
    -- Update 24-hour rolling metrics
    UPDATE dependencies d
    SET
        bytes_last_24h = agg.bytes_24h,
        packets_last_24h = agg.packets_24h,
        flows_last_24h = agg.flows_24h,
        updated_at = NOW()
    FROM (
        SELECT
            dep.id,
            COALESCE(SUM(fa.bytes_total), 0) AS bytes_24h,
            COALESCE(SUM(fa.packets_total), 0) AS packets_24h,
            COALESCE(SUM(fa.flow_count), 0) AS flows_24h
        FROM dependencies dep
        LEFT JOIN flow_aggregates fa ON (
            fa.src_ip = (SELECT primary_ip FROM assets WHERE id = dep.source_asset_id)
            AND fa.dst_ip = (SELECT primary_ip FROM assets WHERE id = dep.target_asset_id)
            AND fa.dst_port = dep.target_port
            AND fa.ip_protocol = dep.protocol
            AND fa.window_start >= NOW() - INTERVAL '24 hours'
        )
        WHERE dep.valid_to IS NULL
          AND NOT dep.is_deleted
        GROUP BY dep.id
    ) agg
    WHERE d.id = agg.id;

    -- Update degree counts on assets
    UPDATE assets a
    SET
        out_degree = (
            SELECT COUNT(*) FROM dependencies d
            WHERE d.source_asset_id = a.id
              AND d.valid_to IS NULL
              AND NOT d.is_deleted
        ),
        in_degree = (
            SELECT COUNT(*) FROM dependencies d
            WHERE d.target_asset_id = a.id
              AND d.valid_to IS NULL
              AND NOT d.is_deleted
        ),
        updated_at = NOW()
    WHERE a.valid_to IS NULL
      AND NOT a.is_deleted;

    COMMIT;
END;
$$;
```

### 6.2 Mark Stale Dependencies

```sql
-- ============================================================================
-- PROCEDURE: Mark dependencies as stale (no traffic for threshold period)
-- ============================================================================

CREATE OR REPLACE PROCEDURE mark_stale_dependencies(
    p_stale_threshold INTERVAL DEFAULT '7 days'
)
LANGUAGE plpgsql AS $$
DECLARE
    stale_count INTEGER;
BEGIN
    -- Close validity window for stale dependencies
    UPDATE dependencies
    SET
        valid_to = NOW(),
        updated_at = NOW()
    WHERE valid_to IS NULL
      AND last_seen < NOW() - p_stale_threshold
      AND NOT is_deleted
      AND NOT is_manual;  -- Don't auto-stale manual declarations

    GET DIAGNOSTICS stale_count = ROW_COUNT;

    RAISE NOTICE 'Marked % dependencies as stale', stale_count;

    COMMIT;
END;
$$;
```

---

## 7. Example Usage Scenarios

### 7.1 Get Full Dependency Graph for an Asset

```sql
-- Complete upstream and downstream within 3 hops
WITH full_graph AS (
    SELECT * FROM calculate_blast_radius('550e8400-e29b-41d4-a716-446655440000', 3)
    UNION
    SELECT
        u.target_asset_id AS asset_id,
        a.name AS asset_name,
        a.primary_ip,
        a.asset_type,
        u.depth,
        u.path AS impact_path,
        0::BIGINT AS dependency_count
    FROM (
        WITH RECURSIVE upstream AS (
            SELECT target_asset_id, 1 AS depth, ARRAY[source_asset_id] AS path
            FROM dependencies
            WHERE source_asset_id = '550e8400-e29b-41d4-a716-446655440000'
              AND valid_to IS NULL AND NOT is_deleted
            UNION ALL
            SELECT d.target_asset_id, u.depth + 1, u.path || d.source_asset_id
            FROM dependencies d
            JOIN upstream u ON d.source_asset_id = u.target_asset_id
            WHERE u.depth < 3 AND NOT d.target_asset_id = ANY(u.path)
              AND d.valid_to IS NULL AND NOT d.is_deleted
        )
        SELECT DISTINCT ON (target_asset_id) * FROM upstream
    ) u
    JOIN assets a ON u.target_asset_id = a.id
    WHERE NOT a.is_deleted
)
SELECT * FROM full_graph
ORDER BY depth, asset_name;
```

### 7.2 API Response Format

```sql
-- JSON format suitable for API/visualization
SELECT jsonb_build_object(
    'nodes', (
        SELECT jsonb_agg(jsonb_build_object(
            'id', asset_id,
            'label', asset_name,
            'ip', primary_ip,
            'type', asset_type,
            'depth', depth
        ))
        FROM calculate_blast_radius('550e8400-e29b-41d4-a716-446655440000', 3)
    ),
    'edges', (
        SELECT jsonb_agg(jsonb_build_object(
            'id', d.id,
            'source', d.source_asset_id,
            'target', d.target_asset_id,
            'port', d.target_port,
            'protocol', d.application_protocol,
            'bytes', d.bytes_last_24h
        ))
        FROM dependencies d
        WHERE (d.source_asset_id = '550e8400-e29b-41d4-a716-446655440000'
               OR d.target_asset_id = '550e8400-e29b-41d4-a716-446655440000')
          AND d.valid_to IS NULL
          AND NOT d.is_deleted
    )
) AS graph;
```

---

*Document maintained by: Engineering Team*
*Last updated: 2024-12-24*
