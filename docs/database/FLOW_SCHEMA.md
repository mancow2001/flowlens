# FlowLens: Canonical Flow Table Design

**Version:** 1.0
**Date:** 2024-12-24
**Purpose:** PostgreSQL schema for normalized flow storage supporting NetFlow, sFlow, and IPFIX

---

## 1. Design Overview

### 1.1 Design Goals

1. **Protocol Agnostic:** Single normalized schema supporting NetFlow v5/v9, sFlow v5, and IPFIX
2. **Time-Partitioned:** Automatic partitioning for efficient time-range queries and data retention
3. **Vendor Extensible:** JSONB columns for vendor-specific and optional fields
4. **Query Optimized:** Indexes designed for common access patterns (src/dst lookups, time ranges)
5. **Space Efficient:** Appropriate data types, compression, and aggregation strategies

### 1.2 Storage Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLOW DATA STORAGE TIERS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TIER 1: Raw Flows (flow_records)                                           │
│  ├── Retention: 7 days                                                      │
│  ├── Partitioned: Hourly                                                    │
│  ├── Use case: Forensics, debugging, replay                                │
│  └── Volume: ~13 GB/day at 10k flows/sec                                   │
│                                                                              │
│  TIER 2: Aggregated Flows (flow_aggregates)                                 │
│  ├── Retention: 90 days                                                     │
│  ├── Partitioned: Daily                                                     │
│  ├── Aggregation: 5-minute windows by src/dst/port/protocol                │
│  ├── Use case: Dependency mapping, trend analysis                          │
│  └── Volume: ~500 MB/day (50:1 compression ratio typical)                  │
│                                                                              │
│  TIER 3: Dependency Statistics (dependency_stats)                           │
│  ├── Retention: 2 years                                                     │
│  ├── Partitioned: Monthly                                                   │
│  ├── Aggregation: Daily rollups per dependency edge                        │
│  ├── Use case: Historical trends, capacity planning                        │
│  └── Volume: ~10 MB/day                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Schema DDL

### 2.1 Prerequisites and Extensions

```sql
-- Required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Trigram search
CREATE EXTENSION IF NOT EXISTS "btree_gist";     -- GiST indexes for ranges
CREATE EXTENSION IF NOT EXISTS "pg_partman";     -- Partition management (optional)

-- Custom types for protocol classification
CREATE TYPE flow_protocol_type AS ENUM (
    'netflow_v5',
    'netflow_v9',
    'ipfix',
    'sflow_v5'
);

CREATE TYPE ip_protocol AS ENUM (
    'tcp',      -- 6
    'udp',      -- 17
    'icmp',     -- 1
    'icmpv6',   -- 58
    'gre',      -- 47
    'esp',      -- 50
    'other'
);

-- Function to convert IP protocol number to enum
CREATE OR REPLACE FUNCTION ip_protocol_from_number(proto_num INTEGER)
RETURNS ip_protocol AS $$
BEGIN
    RETURN CASE proto_num
        WHEN 6 THEN 'tcp'::ip_protocol
        WHEN 17 THEN 'udp'::ip_protocol
        WHEN 1 THEN 'icmp'::ip_protocol
        WHEN 58 THEN 'icmpv6'::ip_protocol
        WHEN 47 THEN 'gre'::ip_protocol
        WHEN 50 THEN 'esp'::ip_protocol
        ELSE 'other'::ip_protocol
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 2.2 Tier 1: Raw Flow Records

```sql
-- ============================================================================
-- TIER 1: RAW FLOW RECORDS
-- Stores individual flow records as received from exporters
-- Partitioned hourly, retained for 7 days
-- ============================================================================

CREATE TABLE flow_records (
    -- Primary key (composite for partitioning)
    id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Flow timing (from exporter)
    flow_start          TIMESTAMPTZ NOT NULL,
    flow_end            TIMESTAMPTZ NOT NULL,

    -- Source information
    exporter_ip         INET NOT NULL,
    exporter_id         INTEGER,                    -- SNMP ifIndex or similar
    protocol_type       flow_protocol_type NOT NULL,

    -- 5-tuple (normalized across all flow types)
    src_ip              INET NOT NULL,
    dst_ip              INET NOT NULL,
    src_port            INTEGER NOT NULL DEFAULT 0,  -- 0 for ICMP
    dst_port            INTEGER NOT NULL DEFAULT 0,
    ip_protocol         SMALLINT NOT NULL,          -- IP protocol number (6=TCP, 17=UDP, etc.)

    -- Traffic metrics (common to all flow types)
    bytes_total         BIGINT NOT NULL DEFAULT 0,
    packets_total       BIGINT NOT NULL DEFAULT 0,

    -- TCP-specific (NULL for non-TCP)
    tcp_flags           SMALLINT,                   -- Cumulative TCP flags

    -- Interface information
    input_interface     INTEGER,                    -- SNMP ifIndex
    output_interface    INTEGER,

    -- Routing information
    src_as              INTEGER,                    -- Autonomous System Number
    dst_as              INTEGER,
    next_hop            INET,

    -- VLAN tagging
    src_vlan            SMALLINT,
    dst_vlan            SMALLINT,

    -- QoS
    tos                 SMALLINT,                   -- Type of Service / DSCP

    -- Direction (if reported by exporter)
    direction           SMALLINT,                   -- 0=ingress, 1=egress

    -- Sampling information
    sampling_rate       INTEGER DEFAULT 1,          -- 1:N sampling (1 = no sampling)

    -- Vendor-specific and optional fields
    -- This JSONB column captures protocol-specific fields not in the normalized schema
    extended_fields     JSONB DEFAULT '{}',

    -- Processing metadata
    processed           BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,

    -- Partition key
    PRIMARY KEY (received_at, id)

) PARTITION BY RANGE (received_at);

-- Create hourly partitions (managed by pg_partman or manually)
-- Example: Create partitions for the next 7 days
DO $$
DECLARE
    start_time TIMESTAMPTZ := DATE_TRUNC('hour', NOW());
    end_time TIMESTAMPTZ;
    partition_name TEXT;
BEGIN
    FOR i IN 0..167 LOOP  -- 7 days * 24 hours
        end_time := start_time + INTERVAL '1 hour';
        partition_name := 'flow_records_' || TO_CHAR(start_time, 'YYYYMMDDHH24');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF flow_records
             FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_time, end_time
        );

        start_time := end_time;
    END LOOP;
END $$;

-- Default partition for out-of-range data
CREATE TABLE flow_records_default PARTITION OF flow_records DEFAULT;
```

### 2.3 JSONB Extended Fields Structure

```sql
-- ============================================================================
-- EXTENDED FIELDS JSONB SCHEMA DOCUMENTATION
-- ============================================================================

/*
The extended_fields JSONB column stores protocol-specific data that doesn't
fit the normalized schema. Structure varies by protocol_type:

NetFlow v5:
{
    "engine_type": 1,
    "engine_id": 0
}

NetFlow v9 / IPFIX:
{
    "template_id": 256,
    "observation_domain_id": 1,
    "application_id": "13:443",           -- NBAR application ID
    "application_name": "HTTPS",          -- If resolved
    "http_url": "/api/v1/resource",       -- If DPI enabled
    "http_host": "api.example.com",
    "ssl_common_name": "*.example.com",
    "user_name": "jdoe",                  -- If AAA integration
    "nat_src_ip": "203.0.113.1",
    "nat_src_port": 54321,
    "nat_dst_ip": "198.51.100.1",
    "nat_dst_port": 443,
    "flow_label": 12345,                  -- IPv6 flow label
    "mpls_labels": [100, 200, 300],
    "bgp_communities": ["65000:100"],
    "vendor": {
        "cisco": {
            "connection_id": 12345,
            "firewall_event": 2
        }
    }
}

sFlow v5:
{
    "sample_pool": 1000,                  -- Total packets in sampling pool
    "drops": 0,
    "input_format": 0,                    -- 0=ifIndex, 1=VLAN
    "output_format": 0,
    "header_protocol": 1,                 -- 1=Ethernet
    "frame_length": 1518,
    "stripped": 4,                        -- Bytes stripped
    "extended_switch": {
        "src_vlan": 100,
        "src_priority": 0,
        "dst_vlan": 200,
        "dst_priority": 0
    },
    "extended_router": {
        "next_hop": "10.0.0.1",
        "src_mask": 24,
        "dst_mask": 16
    },
    "extended_gateway": {
        "as_path": [65001, 65002, 65003],
        "communities": ["65000:100"]
    },
    "extended_user": {
        "src_user": "src_username",
        "dst_user": "dst_username"
    }
}
*/

-- Validate extended_fields structure (optional constraint)
ALTER TABLE flow_records ADD CONSTRAINT extended_fields_is_object
    CHECK (jsonb_typeof(extended_fields) = 'object');
```

### 2.4 Tier 1 Indexes

```sql
-- ============================================================================
-- TIER 1 INDEXES: Optimized for common query patterns
-- ============================================================================

-- Primary lookup patterns: Source IP queries
CREATE INDEX idx_flow_records_src_ip
    ON flow_records (src_ip, received_at DESC);

-- Primary lookup patterns: Destination IP queries
CREATE INDEX idx_flow_records_dst_ip
    ON flow_records (dst_ip, received_at DESC);

-- Combined source/destination for specific pair analysis
CREATE INDEX idx_flow_records_src_dst
    ON flow_records (src_ip, dst_ip, received_at DESC);

-- Exporter-based queries (troubleshooting specific devices)
CREATE INDEX idx_flow_records_exporter
    ON flow_records (exporter_ip, received_at DESC);

-- Port-based queries (service analysis)
CREATE INDEX idx_flow_records_dst_port
    ON flow_records (dst_port, received_at DESC)
    WHERE dst_port > 0;

-- Protocol-based queries
CREATE INDEX idx_flow_records_protocol
    ON flow_records (ip_protocol, received_at DESC);

-- Unprocessed flows (for enrichment pipeline)
CREATE INDEX idx_flow_records_unprocessed
    ON flow_records (received_at)
    WHERE processed = FALSE;

-- JSONB indexes for extended field queries
-- GIN index for containment queries (@>, ?, ?|, ?&)
CREATE INDEX idx_flow_records_extended_gin
    ON flow_records USING GIN (extended_fields jsonb_path_ops);

-- Specific JSONB field indexes (create as needed based on query patterns)
CREATE INDEX idx_flow_records_app_name
    ON flow_records ((extended_fields->>'application_name'))
    WHERE extended_fields->>'application_name' IS NOT NULL;

-- BRIN index for time-series data (very efficient for time-ordered data)
CREATE INDEX idx_flow_records_received_brin
    ON flow_records USING BRIN (received_at)
    WITH (pages_per_range = 32);
```

### 2.5 Tier 2: Aggregated Flows

```sql
-- ============================================================================
-- TIER 2: AGGREGATED FLOWS
-- 5-minute aggregation windows, retained for 90 days
-- ============================================================================

CREATE TABLE flow_aggregates (
    -- Time window
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,

    -- Aggregation key (5-tuple + exporter)
    exporter_ip         INET NOT NULL,
    src_ip              INET NOT NULL,
    dst_ip              INET NOT NULL,
    src_port            INTEGER NOT NULL,
    dst_port            INTEGER NOT NULL,
    ip_protocol         SMALLINT NOT NULL,

    -- Aggregated metrics
    flow_count          BIGINT NOT NULL DEFAULT 0,
    bytes_total         BIGINT NOT NULL DEFAULT 0,
    packets_total       BIGINT NOT NULL DEFAULT 0,

    -- TCP flag aggregation (OR of all observed flags)
    tcp_flags_observed  SMALLINT DEFAULT 0,

    -- Session metrics
    active_sessions     INTEGER DEFAULT 0,          -- Concurrent connections (estimated)
    new_sessions        INTEGER DEFAULT 0,          -- SYN count for TCP
    closed_sessions     INTEGER DEFAULT 0,          -- FIN/RST count for TCP

    -- Timing statistics
    min_duration_ms     INTEGER,                    -- Shortest flow in window
    max_duration_ms     INTEGER,                    -- Longest flow in window
    avg_duration_ms     INTEGER,                    -- Average flow duration

    -- Sampling-adjusted totals
    bytes_sampled       BIGINT NOT NULL DEFAULT 0,  -- Pre-sampling-adjustment
    sampling_rate       INTEGER DEFAULT 1,

    -- Source protocol mix (percentage of each source)
    protocol_sources    JSONB DEFAULT '{}',         -- {"netflow_v9": 80, "sflow_v5": 20}

    -- Interface aggregation
    interfaces          JSONB DEFAULT '{}',         -- {"input": [1,2], "output": [3]}

    -- Derived fields
    is_internal         BOOLEAN,                    -- Both IPs are RFC1918
    traffic_direction   VARCHAR(10),                -- 'internal', 'egress', 'ingress'

    -- Partition key
    PRIMARY KEY (window_start, src_ip, dst_ip, dst_port, ip_protocol)

) PARTITION BY RANGE (window_start);

-- Create daily partitions (90 days retention)
DO $$
DECLARE
    start_date DATE := CURRENT_DATE;
    end_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..89 LOOP
        end_date := start_date + INTERVAL '1 day';
        partition_name := 'flow_aggregates_' || TO_CHAR(start_date, 'YYYYMMDD');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF flow_aggregates
             FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );

        start_date := end_date;
    END LOOP;
END $$;

CREATE TABLE flow_aggregates_default PARTITION OF flow_aggregates DEFAULT;

-- Indexes for aggregated flows
CREATE INDEX idx_flow_agg_src_ip ON flow_aggregates (src_ip, window_start DESC);
CREATE INDEX idx_flow_agg_dst_ip ON flow_aggregates (dst_ip, window_start DESC);
CREATE INDEX idx_flow_agg_pair ON flow_aggregates (src_ip, dst_ip, window_start DESC);
CREATE INDEX idx_flow_agg_port ON flow_aggregates (dst_port, window_start DESC);
CREATE INDEX idx_flow_agg_internal ON flow_aggregates (is_internal, window_start DESC);
```

### 2.6 Tier 3: Dependency Statistics (Daily Rollups)

```sql
-- ============================================================================
-- TIER 3: DEPENDENCY STATISTICS
-- Daily rollups per dependency edge, retained for 2 years
-- ============================================================================

CREATE TABLE dependency_stats (
    -- Date dimension
    stat_date           DATE NOT NULL,

    -- Dependency edge reference
    dependency_id       UUID NOT NULL,

    -- Daily aggregated metrics
    bytes_total         BIGINT NOT NULL DEFAULT 0,
    packets_total       BIGINT NOT NULL DEFAULT 0,
    flow_count          BIGINT NOT NULL DEFAULT 0,

    -- Connection patterns
    sessions_total      INTEGER DEFAULT 0,
    sessions_peak       INTEGER DEFAULT 0,          -- Max concurrent in any 5-min window

    -- Timing
    first_seen_today    TIMESTAMPTZ,
    last_seen_today     TIMESTAMPTZ,
    active_minutes      INTEGER DEFAULT 0,          -- Minutes with traffic

    -- Traffic patterns
    bytes_per_hour      BIGINT[] DEFAULT ARRAY[]::BIGINT[],  -- 24-element array

    -- Percentiles (for capacity planning)
    bytes_p50           BIGINT,                     -- Median 5-min bytes
    bytes_p95           BIGINT,                     -- 95th percentile
    bytes_p99           BIGINT,                     -- 99th percentile

    PRIMARY KEY (stat_date, dependency_id)

) PARTITION BY RANGE (stat_date);

-- Create monthly partitions (24 months retention)
DO $$
DECLARE
    start_date DATE := DATE_TRUNC('month', CURRENT_DATE);
    end_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..23 LOOP
        end_date := start_date + INTERVAL '1 month';
        partition_name := 'dependency_stats_' || TO_CHAR(start_date, 'YYYYMM');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF dependency_stats
             FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );

        start_date := end_date;
    END LOOP;
END $$;

CREATE TABLE dependency_stats_default PARTITION OF dependency_stats DEFAULT;

-- Indexes
CREATE INDEX idx_dep_stats_dependency ON dependency_stats (dependency_id, stat_date DESC);
```

---

## 3. Aggregation Functions

### 3.1 5-Minute Aggregation Procedure

```sql
-- ============================================================================
-- AGGREGATION: Raw flows → 5-minute windows
-- ============================================================================

CREATE OR REPLACE PROCEDURE aggregate_flows_to_windows(
    p_window_start TIMESTAMPTZ,
    p_window_end TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO flow_aggregates (
        window_start,
        window_end,
        exporter_ip,
        src_ip,
        dst_ip,
        src_port,
        dst_port,
        ip_protocol,
        flow_count,
        bytes_total,
        packets_total,
        tcp_flags_observed,
        bytes_sampled,
        sampling_rate,
        is_internal,
        traffic_direction
    )
    SELECT
        p_window_start,
        p_window_end,
        exporter_ip,
        src_ip,
        dst_ip,
        src_port,
        dst_port,
        ip_protocol,
        COUNT(*) as flow_count,
        SUM(bytes_total * COALESCE(sampling_rate, 1)) as bytes_total,
        SUM(packets_total * COALESCE(sampling_rate, 1)) as packets_total,
        BIT_OR(tcp_flags) as tcp_flags_observed,
        SUM(bytes_total) as bytes_sampled,
        MAX(sampling_rate) as sampling_rate,
        -- RFC1918 check for internal traffic
        (src_ip << '10.0.0.0/8'::inet OR src_ip << '172.16.0.0/12'::inet OR src_ip << '192.168.0.0/16'::inet)
        AND
        (dst_ip << '10.0.0.0/8'::inet OR dst_ip << '172.16.0.0/12'::inet OR dst_ip << '192.168.0.0/16'::inet)
        as is_internal,
        CASE
            WHEN (src_ip << '10.0.0.0/8'::inet OR src_ip << '172.16.0.0/12'::inet OR src_ip << '192.168.0.0/16'::inet)
                 AND NOT (dst_ip << '10.0.0.0/8'::inet OR dst_ip << '172.16.0.0/12'::inet OR dst_ip << '192.168.0.0/16'::inet)
            THEN 'egress'
            WHEN NOT (src_ip << '10.0.0.0/8'::inet OR src_ip << '172.16.0.0/12'::inet OR src_ip << '192.168.0.0/16'::inet)
                 AND (dst_ip << '10.0.0.0/8'::inet OR dst_ip << '172.16.0.0/12'::inet OR dst_ip << '192.168.0.0/16'::inet)
            THEN 'ingress'
            ELSE 'internal'
        END as traffic_direction
    FROM flow_records
    WHERE received_at >= p_window_start
      AND received_at < p_window_end
      AND processed = FALSE
    GROUP BY
        exporter_ip, src_ip, dst_ip, src_port, dst_port, ip_protocol
    ON CONFLICT (window_start, src_ip, dst_ip, dst_port, ip_protocol)
    DO UPDATE SET
        flow_count = flow_aggregates.flow_count + EXCLUDED.flow_count,
        bytes_total = flow_aggregates.bytes_total + EXCLUDED.bytes_total,
        packets_total = flow_aggregates.packets_total + EXCLUDED.packets_total,
        tcp_flags_observed = flow_aggregates.tcp_flags_observed | EXCLUDED.tcp_flags_observed;

    -- Mark flows as processed
    UPDATE flow_records
    SET processed = TRUE, processed_at = NOW()
    WHERE received_at >= p_window_start
      AND received_at < p_window_end
      AND processed = FALSE;

    COMMIT;
END;
$$;
```

### 3.2 Daily Rollup Procedure

```sql
-- ============================================================================
-- AGGREGATION: 5-minute windows → Daily dependency stats
-- ============================================================================

CREATE OR REPLACE PROCEDURE rollup_daily_dependency_stats(
    p_date DATE
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dependency_stats (
        stat_date,
        dependency_id,
        bytes_total,
        packets_total,
        flow_count,
        first_seen_today,
        last_seen_today,
        active_minutes
    )
    SELECT
        p_date,
        d.id as dependency_id,
        SUM(fa.bytes_total) as bytes_total,
        SUM(fa.packets_total) as packets_total,
        SUM(fa.flow_count) as flow_count,
        MIN(fa.window_start) as first_seen_today,
        MAX(fa.window_end) as last_seen_today,
        COUNT(DISTINCT DATE_TRUNC('minute', fa.window_start)) * 5 as active_minutes
    FROM flow_aggregates fa
    JOIN dependencies d ON (
        d.source_ip = fa.src_ip
        AND d.target_ip = fa.dst_ip
        AND d.port = fa.dst_port
        AND d.protocol = fa.ip_protocol
    )
    WHERE fa.window_start >= p_date::timestamptz
      AND fa.window_start < (p_date + 1)::timestamptz
    GROUP BY d.id
    ON CONFLICT (stat_date, dependency_id)
    DO UPDATE SET
        bytes_total = EXCLUDED.bytes_total,
        packets_total = EXCLUDED.packets_total,
        flow_count = EXCLUDED.flow_count,
        first_seen_today = EXCLUDED.first_seen_today,
        last_seen_today = EXCLUDED.last_seen_today,
        active_minutes = EXCLUDED.active_minutes;

    COMMIT;
END;
$$;
```

---

## 4. Partition Management

### 4.1 Automated Partition Creation

```sql
-- ============================================================================
-- PARTITION MANAGEMENT: Create future partitions, drop old ones
-- ============================================================================

CREATE OR REPLACE PROCEDURE manage_flow_partitions()
LANGUAGE plpgsql
AS $$
DECLARE
    partition_name TEXT;
    start_time TIMESTAMPTZ;
    end_time TIMESTAMPTZ;
    retention_cutoff TIMESTAMPTZ;
BEGIN
    -- Create hourly partitions for next 24 hours
    start_time := DATE_TRUNC('hour', NOW() + INTERVAL '1 hour');
    FOR i IN 1..24 LOOP
        end_time := start_time + INTERVAL '1 hour';
        partition_name := 'flow_records_' || TO_CHAR(start_time, 'YYYYMMDDHH24');

        -- Check if partition exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE tablename = partition_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF flow_records
                 FOR VALUES FROM (%L) TO (%L)',
                partition_name, start_time, end_time
            );
            RAISE NOTICE 'Created partition: %', partition_name;
        END IF;

        start_time := end_time;
    END LOOP;

    -- Drop partitions older than 7 days
    retention_cutoff := DATE_TRUNC('hour', NOW() - INTERVAL '7 days');

    FOR partition_name IN
        SELECT tablename
        FROM pg_tables
        WHERE tablename LIKE 'flow_records_%'
          AND tablename != 'flow_records_default'
          AND TO_TIMESTAMP(SUBSTRING(tablename FROM 'flow_records_(\d{10})'), 'YYYYMMDDHH24') < retention_cutoff
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS %I', partition_name);
        RAISE NOTICE 'Dropped partition: %', partition_name;
    END LOOP;

    COMMIT;
END;
$$;

-- Schedule partition management (run hourly via pg_cron or external scheduler)
-- SELECT cron.schedule('0 * * * *', 'CALL manage_flow_partitions()');
```

### 4.2 pg_partman Configuration (Alternative)

```sql
-- ============================================================================
-- PARTITION MANAGEMENT: Using pg_partman (recommended for production)
-- ============================================================================

-- Configure pg_partman for flow_records
SELECT partman.create_parent(
    p_parent_table := 'public.flow_records',
    p_control := 'received_at',
    p_type := 'native',
    p_interval := 'hourly',
    p_premake := 24,                    -- Pre-create 24 hours of partitions
    p_start_partition := NOW()::text
);

-- Configure retention
UPDATE partman.part_config
SET retention = '7 days',
    retention_keep_table = false,       -- Drop old partitions (not just detach)
    retention_keep_index = false
WHERE parent_table = 'public.flow_records';

-- Configure pg_partman for flow_aggregates
SELECT partman.create_parent(
    p_parent_table := 'public.flow_aggregates',
    p_control := 'window_start',
    p_type := 'native',
    p_interval := 'daily',
    p_premake := 7,
    p_start_partition := NOW()::text
);

UPDATE partman.part_config
SET retention = '90 days',
    retention_keep_table = false
WHERE parent_table = 'public.flow_aggregates';

-- Run maintenance (schedule via pg_cron)
-- SELECT cron.schedule('maintenance', '0 * * * *', 'SELECT partman.run_maintenance()');
```

---

## 5. Query Examples

### 5.1 Common Queries

```sql
-- ============================================================================
-- QUERY EXAMPLES
-- ============================================================================

-- Query 1: Get all flows from a specific source IP in last hour
SELECT
    received_at,
    src_ip,
    dst_ip,
    dst_port,
    ip_protocol,
    bytes_total,
    packets_total
FROM flow_records
WHERE src_ip = '192.168.1.100'::inet
  AND received_at >= NOW() - INTERVAL '1 hour'
ORDER BY received_at DESC
LIMIT 100;

-- Query 2: Top destinations by traffic volume
SELECT
    dst_ip,
    dst_port,
    SUM(bytes_total) as total_bytes,
    SUM(packets_total) as total_packets,
    COUNT(*) as flow_count
FROM flow_aggregates
WHERE window_start >= NOW() - INTERVAL '24 hours'
  AND src_ip << '10.0.0.0/8'::inet  -- From internal network
GROUP BY dst_ip, dst_port
ORDER BY total_bytes DESC
LIMIT 20;

-- Query 3: Find all flows with specific application (from extended_fields)
SELECT
    src_ip,
    dst_ip,
    extended_fields->>'application_name' as app_name,
    bytes_total
FROM flow_records
WHERE extended_fields->>'application_name' = 'HTTPS'
  AND received_at >= NOW() - INTERVAL '1 hour';

-- Query 4: Traffic between two subnets
SELECT
    DATE_TRUNC('hour', window_start) as hour,
    SUM(bytes_total) as bytes,
    SUM(flow_count) as flows
FROM flow_aggregates
WHERE src_ip << '10.1.0.0/16'::inet
  AND dst_ip << '10.2.0.0/16'::inet
  AND window_start >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', window_start)
ORDER BY hour;

-- Query 5: Unusual TCP flags (potential scan detection)
SELECT
    src_ip,
    COUNT(DISTINCT dst_ip) as unique_destinations,
    COUNT(DISTINCT dst_port) as unique_ports,
    BIT_OR(tcp_flags) as flags_seen
FROM flow_records
WHERE received_at >= NOW() - INTERVAL '5 minutes'
  AND ip_protocol = 6  -- TCP
  AND tcp_flags & 2 = 2  -- SYN flag set
GROUP BY src_ip
HAVING COUNT(DISTINCT dst_port) > 100  -- Port scan threshold
ORDER BY unique_ports DESC;

-- Query 6: Traffic from specific exporter with vendor extensions
SELECT
    received_at,
    src_ip,
    dst_ip,
    extended_fields->'vendor'->'cisco'->>'firewall_event' as fw_event
FROM flow_records
WHERE exporter_ip = '10.0.0.1'::inet
  AND extended_fields->'vendor'->'cisco'->>'firewall_event' IS NOT NULL
  AND received_at >= NOW() - INTERVAL '1 hour';
```

---

## 6. Performance Considerations

### 6.1 Index Usage Guidelines

| Query Pattern | Recommended Index | Notes |
|---------------|-------------------|-------|
| Single source IP lookup | `idx_flow_records_src_ip` | Include time filter for partition pruning |
| Single destination IP | `idx_flow_records_dst_ip` | Most common query pattern |
| Source-destination pair | `idx_flow_records_src_dst` | For specific connection analysis |
| Port-based analysis | `idx_flow_records_dst_port` | Useful for service discovery |
| Time-range only | `idx_flow_records_received_brin` | BRIN is very space-efficient |
| JSONB field lookup | `idx_flow_records_extended_gin` | For @> containment queries |
| Specific JSONB path | Create expression index | For frequently queried fields |

### 6.2 Query Optimization Tips

```sql
-- Always include time bounds for partition pruning
-- GOOD: Partition pruning activates
SELECT * FROM flow_records
WHERE src_ip = '10.0.0.1'
  AND received_at >= NOW() - INTERVAL '1 hour';

-- BAD: Scans all partitions
SELECT * FROM flow_records
WHERE src_ip = '10.0.0.1';

-- Use EXPLAIN ANALYZE to verify partition pruning
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM flow_records
WHERE received_at >= NOW() - INTERVAL '1 hour';
-- Should show "Partitions selected: 1" or similar

-- For JSONB, use containment operator for index usage
-- GOOD: Uses GIN index
SELECT * FROM flow_records
WHERE extended_fields @> '{"application_name": "HTTPS"}';

-- BAD: Cannot use GIN index efficiently
SELECT * FROM flow_records
WHERE extended_fields->>'application_name' LIKE 'HTTP%';
```

### 6.3 Storage Estimation

```
Flow rate: 10,000 flows/sec
Row size (estimated): 150 bytes normalized + 100 bytes indexes

Tier 1 (Raw, 7 days):
  10,000 × 250 bytes × 86,400 sec × 7 days = ~1.5 TB

Tier 2 (Aggregated, 90 days):
  ~10:1 compression ratio → 150 GB

Tier 3 (Daily stats, 2 years):
  ~100:1 compression ratio → 15 GB

Total storage requirement: ~1.7 TB
```

---

*Document maintained by: Engineering Team*
*Last updated: 2024-12-24*
