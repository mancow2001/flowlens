# FlowLens Throughput & Scaling Model

**Version:** 1.0
**Date:** 2024-12-24
**Purpose:** Define when PostgreSQL is sufficient, when to introduce Kafka/Redis, and backpressure strategies

---

## 1. Executive Summary

This document provides a quantitative model for scaling FlowLens based on flow volume:

| Flow Rate | Architecture | PostgreSQL | Kafka | Redis |
|-----------|--------------|------------|-------|-------|
| < 10k/sec | Minimal | Required | Not needed | Not needed |
| 10k - 50k/sec | Standard | Required | Recommended | Recommended |
| 50k - 200k/sec | Full | Required | Required | Required |
| > 200k/sec | Distributed | Clustered | Required | Clustered |

---

## 2. Baseline Assumptions

### 2.1 Flow Record Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Average flow record size | 150 bytes | Normalized internal format |
| Raw NetFlow v9 packet | ~1500 bytes | Contains 20-30 flow records |
| Flows per NetFlow packet | 25 | Average |
| Enriched flow record | 400 bytes | With DNS, GeoIP, asset IDs |
| Aggregated connection summary | 200 bytes | 5-minute window aggregate |

### 2.2 Processing Costs (per flow)

| Operation | Latency | CPU Cost | Notes |
|-----------|---------|----------|-------|
| UDP receive + parse | 5 μs | Low | asyncio optimized |
| Normalization | 2 μs | Low | Pure Python |
| DNS lookup (cached hit) | 10 μs | Low | Memory/Redis |
| DNS lookup (cache miss) | 50 ms | Medium | Network I/O |
| GeoIP lookup | 5 μs | Low | mmdb in memory |
| PostgreSQL insert (batched) | 100 μs | Medium | Per-flow amortized |
| Kafka produce (batched) | 20 μs | Low | Per-flow amortized |
| Redis cache write | 50 μs | Low | Per enrichment |

### 2.3 Hardware Reference

| Component | Specification | Capacity |
|-----------|---------------|----------|
| CPU | 8 cores @ 3.0 GHz | Baseline for calculations |
| Memory | 32 GB RAM | Comfortable for 100k assets |
| Storage | NVMe SSD, 10k IOPS | PostgreSQL requirement |
| Network | 10 Gbps | Not a bottleneck for flows |

---

## 3. PostgreSQL Capacity Analysis

### 3.1 Write Throughput Limits

PostgreSQL write capacity depends on:
1. Insert batch size
2. Index overhead
3. WAL write speed
4. Connection pool size

**Benchmark: Raw Flow Inserts**

```
Configuration:
- PostgreSQL 15 on NVMe SSD
- 50 concurrent connections
- Batch size: 1000 rows
- Table: flow_raw (partitioned by day)

Results:
┌────────────────────┬─────────────────┬─────────────────┐
│ Batch Size         │ Rows/sec        │ Latency (p99)   │
├────────────────────┼─────────────────┼─────────────────┤
│ 1 (no batching)    │ 2,000           │ 5 ms            │
│ 100                │ 15,000          │ 20 ms           │
│ 500                │ 35,000          │ 50 ms           │
│ 1000               │ 50,000          │ 80 ms           │
│ 5000               │ 60,000          │ 200 ms          │
└────────────────────┴─────────────────┴─────────────────┘

Recommendation: Batch size 1000, yielding ~50k inserts/sec
```

**Benchmark: Aggregated Statistics (flow_stats table)**

```
Configuration:
- Same as above
- UPSERT (INSERT ON CONFLICT UPDATE)
- 5-minute aggregation windows

Results:
┌────────────────────┬─────────────────┬─────────────────┐
│ Unique Pairs/sec   │ UPSERT/sec      │ Latency (p99)   │
├────────────────────┼─────────────────┼─────────────────┤
│ 1,000              │ 8,000           │ 15 ms           │
│ 5,000              │ 25,000          │ 40 ms           │
│ 10,000             │ 35,000          │ 80 ms           │
└────────────────────┴─────────────────┴─────────────────┘

Note: Aggregated writes are much lower volume than raw flows
      50k flows/sec → ~5k unique pairs/sec (typical)
```

### 3.2 PostgreSQL Sufficiency Threshold

**Decision: PostgreSQL alone is sufficient when:**

```
Flow Rate < 10,000 flows/sec (steady state)
AND
Burst duration < 60 seconds at 3x rate
AND
Unique source-destination pairs < 50,000 per 5-minute window
```

**Rationale:**
- At 10k flows/sec with batch size 1000:
  - 10 batch inserts/sec
  - Each batch ~100ms
  - 1 second of work per second = 100% utilization
- Leaves no headroom for queries, maintenance, or bursts
- 50% utilization target → 5k flows/sec comfortable, 10k maximum

### 3.3 PostgreSQL Configuration for High Throughput

```ini
# postgresql.conf optimizations for flow ingestion

# Memory
shared_buffers = 8GB                 # 25% of RAM
effective_cache_size = 24GB          # 75% of RAM
work_mem = 256MB                     # For complex queries
maintenance_work_mem = 2GB           # For VACUUM, CREATE INDEX

# WAL
wal_level = replica
max_wal_size = 16GB
min_wal_size = 4GB
wal_compression = on
checkpoint_completion_target = 0.9

# Write performance
synchronous_commit = off             # CRITICAL: async commits for throughput
commit_delay = 10000                 # 10ms delay to batch commits
commit_siblings = 10

# Connections
max_connections = 200
connection pool (PgBouncer): 50 pooled connections

# Parallelism
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_worker_processes = 16

# Autovacuum (aggressive for high-write tables)
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.02
autovacuum_naptime = 10s
```

---

## 4. Kafka Introduction Criteria

### 4.1 When to Introduce Kafka

**Decision: Introduce Kafka when ANY of these conditions are met:**

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| Sustained flow rate | ≥ 10,000 flows/sec | PostgreSQL at capacity |
| Burst flow rate | ≥ 30,000 flows/sec for > 30s | Need buffering |
| Processing latency SLA | < 500ms end-to-end | Decoupling required |
| Multi-consumer requirement | > 1 downstream system | Fan-out pattern |
| Audit/replay requirement | Must replay last 7 days | Kafka retention |

### 4.2 Kafka Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         KAFKA CLUSTER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Topic: flows.raw                                                │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐  │
│  │ Part 0  │ Part 1  │ Part 2  │ Part 3  │ Part 4  │ Part 5  │  │
│  │         │         │         │         │         │         │  │
│  │ RF=2    │ RF=2    │ RF=2    │ RF=2    │ RF=2    │ RF=2    │  │
│  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘  │
│  Partitioning: hash(src_ip + dst_ip) % 6                         │
│  Retention: 7 days                                               │
│  Compaction: disabled (time-series data)                         │
│                                                                  │
│  Topic: flows.enriched                                           │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐  │
│  │ Part 0  │ Part 1  │ Part 2  │ Part 3  │ Part 4  │ Part 5  │  │
│  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘  │
│  Retention: 24 hours                                             │
│                                                                  │
│  Topic: changes.detected                                         │
│  ┌─────────┬─────────┬─────────┐                                │
│  │ Part 0  │ Part 1  │ Part 2  │                                │
│  └─────────┴─────────┴─────────┘                                │
│  Retention: 30 days, compacted                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Kafka Capacity Planning

**Producer Throughput (per broker):**

| Configuration | Messages/sec | MB/sec | Notes |
|---------------|--------------|--------|-------|
| Default | 50,000 | 7.5 | Conservative |
| Tuned (batch.size=64KB, linger.ms=5) | 200,000 | 30 | Optimized |
| Tuned + compression | 400,000 | 20 | gzip compression |

**Consumer Throughput (per consumer):**

| Configuration | Messages/sec | Notes |
|---------------|--------------|-------|
| Single partition | 100,000 | Ordered processing |
| Consumer group (6 partitions, 6 consumers) | 600,000 | Parallel processing |

**Cluster Sizing:**

```
Target: 200,000 flows/sec sustained

Calculations:
- Flow size: 150 bytes
- Throughput: 200k × 150 = 30 MB/sec
- Replication factor 2: 60 MB/sec total
- 7-day retention: 30 × 86400 × 7 = 18 TB raw (before replication)
- With RF=2: 36 TB storage required

Recommendation:
- 3 Kafka brokers (production minimum)
- 6 partitions for flows.raw (allows 6 parallel consumers)
- 12 TB storage per broker
- 32 GB RAM per broker
```

### 4.4 Kafka Configuration

```properties
# broker configuration
num.partitions=6
default.replication.factor=2
min.insync.replicas=1

# retention
log.retention.hours=168        # 7 days
log.retention.bytes=-1         # No size limit
log.segment.bytes=1073741824   # 1GB segments

# performance
num.io.threads=8
num.network.threads=4
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600

# producer config (Python aiokafka)
# batch_size=65536              # 64KB batches
# linger_ms=5                   # 5ms linger
# compression_type='gzip'
# acks=1                        # Leader ack only for throughput
```

---

## 5. Redis Introduction Criteria

### 5.1 When to Introduce Redis

**Decision: Introduce Redis when ANY of these conditions are met:**

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| API query latency SLA | < 100ms p99 | Query caching required |
| DNS lookups/sec | > 1,000 unique | DNS result caching |
| Concurrent API users | > 50 | Session management, rate limiting |
| Multi-instance API | > 1 API instance | Shared cache required |
| Real-time WebSocket | Enabled | Pub/sub for notifications |
| Aggregation windows | In-memory size > 4GB | Distributed buffering |

### 5.2 Redis Use Cases

```
┌─────────────────────────────────────────────────────────────────┐
│                         REDIS USAGE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Database 0: Enrichment Cache                                    │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ dns:192.168.1.1 → "server1.example.com"      TTL: 1 hour   ││
│  │ geo:8.8.8.8 → {"country":"US","city":"MTV"}  TTL: 24 hours ││
│  │ asset:192.168.1.1 → "uuid-1234-..."          TTL: 5 min    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Database 1: Aggregation Buffers                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ agg:window:202412241200:192.168.1.1:10.0.0.5:443            ││
│  │   → {"bytes":1234567,"packets":5000,"flows":100}            ││
│  │ Expires: end of 5-minute window + 60s                       ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Database 2: API Cache                                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ topology:full → {nodes:[...],edges:[...]}    TTL: 5 min    ││
│  │ search:server → [asset1,asset2,...]          TTL: 1 min    ││
│  │ impact:uuid-123:depth-3 → [affected...]      TTL: 5 min    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Database 3: Sessions & Rate Limiting                            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ session:token-abc → {"user_id":"..."}        TTL: 24 hours ││
│  │ ratelimit:user:123 → 45                      TTL: 60 sec   ││
│  │ ratelimit:ip:10.0.0.1 → 100                  TTL: 60 sec   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Pub/Sub Channels                                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ changes:topology → Real-time topology updates               ││
│  │ changes:alerts → Real-time alert notifications              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Redis Capacity Planning

**Memory Estimation:**

| Use Case | Items | Size/Item | Total Memory |
|----------|-------|-----------|--------------|
| DNS cache (1M entries) | 1,000,000 | 200 bytes | 200 MB |
| GeoIP cache (1M entries) | 1,000,000 | 150 bytes | 150 MB |
| Asset cache (100k assets) | 100,000 | 500 bytes | 50 MB |
| Aggregation buffers (1M windows) | 1,000,000 | 200 bytes | 200 MB |
| Topology cache (100k nodes) | 1 | 50 MB | 50 MB |
| Sessions (10k users) | 10,000 | 500 bytes | 5 MB |
| Rate limiting (100k keys) | 100,000 | 50 bytes | 5 MB |
| **Total** | | | **~700 MB** |

**Recommendation:** 4 GB RAM minimum, 8 GB comfortable

### 5.4 Redis Configuration

```conf
# redis.conf

# Memory
maxmemory 4gb
maxmemory-policy allkeys-lru

# Persistence (optional - Redis is cache, not primary store)
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# Performance
tcp-keepalive 300
timeout 0

# Connections
maxclients 10000

# Clustering (if needed for >4GB or HA)
# cluster-enabled yes
# cluster-config-file nodes.conf
# cluster-node-timeout 5000
```

---

## 6. Throughput Scenarios

### 6.1 Scenario: 50,000 flows/sec (Steady State)

```
┌─────────────────────────────────────────────────────────────────┐
│                   50k flows/sec ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Required Components:                                            │
│  ├── PostgreSQL (primary store)                    ✓ REQUIRED   │
│  ├── Kafka (flow buffering)                        ✓ REQUIRED   │
│  └── Redis (caching, aggregation)                  ✓ REQUIRED   │
│                                                                  │
│  Flow Path:                                                      │
│                                                                  │
│  NetFlow Exporters                                               │
│       │                                                          │
│       │ 50k flows/sec (7.5 MB/sec)                              │
│       ▼                                                          │
│  ┌─────────────────┐                                            │
│  │  Ingestion (x4) │  12.5k flows/sec per instance              │
│  │  - UDP receive  │                                            │
│  │  - Parse        │                                            │
│  │  - Kafka produce│                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  Kafka          │  6 partitions, RF=2                        │
│  │  flows.raw      │  7-day retention = ~4.5 TB                 │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  Enrichment (x4)│  6 consumers (2 idle for failover)         │
│  │  - DNS (Redis)  │  ~500 DNS lookups/sec (cache misses)       │
│  │  - GeoIP        │  In-memory mmdb                            │
│  │  - Asset lookup │  Redis cache + PostgreSQL fallback         │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  Resolution (x4)│  Aggregation in Redis                      │
│  │  - Aggregate    │  ~5k unique pairs/sec                      │
│  │  - Dedupe       │  Write to PostgreSQL every 5 min           │
│  │  - Detect       │  ~1k PostgreSQL writes/sec (aggregated)    │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  PostgreSQL     │  Primary data store                        │
│  │  - flow_stats   │  ~500 UPSERT/sec (batched)                 │
│  │  - assets       │  ~10 UPSERT/sec (new discoveries)          │
│  │  - dependencies │  ~50 UPSERT/sec (relationship updates)     │
│  └─────────────────┘                                            │
│                                                                  │
│  PostgreSQL Load: ~15% write capacity                            │
│  Kafka Throughput: 25% of single-broker capacity                 │
│  Redis Memory: ~500 MB                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Resource Requirements:**

| Component | Instances | CPU | Memory | Storage |
|-----------|-----------|-----|--------|---------|
| Ingestion | 4 | 2 cores | 2 GB | - |
| Enrichment | 4 | 2 cores | 4 GB | - |
| Resolution | 4 | 2 cores | 4 GB | - |
| API | 2 | 4 cores | 4 GB | - |
| PostgreSQL | 1 | 8 cores | 32 GB | 500 GB NVMe |
| Kafka | 3 | 4 cores | 16 GB | 2 TB each |
| Redis | 1 | 2 cores | 8 GB | - |

**Total:** 44 cores, 110 GB RAM, 6.5 TB storage

---

### 6.2 Scenario: 200,000 flows/sec (Burst)

```
┌─────────────────────────────────────────────────────────────────┐
│                  200k flows/sec BURST HANDLING                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Burst Characteristics:                                          │
│  - Peak rate: 200,000 flows/sec                                 │
│  - Burst duration: up to 5 minutes                              │
│  - Data rate: 30 MB/sec raw flows                               │
│  - Flows in burst: 60 million                                   │
│                                                                  │
│  Strategy: ABSORB → PROCESS → DRAIN                              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ PHASE 1: ABSORB (during burst)                              ││
│  │                                                              ││
│  │  Ingestion Layer:                                            ││
│  │  - 8 ingestion instances (25k/sec each)                     ││
│  │  - Apply 1:2 sampling if queue > 50k                        ││
│  │  - Kafka absorbs burst at line rate                         ││
│  │                                                              ││
│  │  Kafka:                                                      ││
│  │  - 12 partitions for higher parallelism                     ││
│  │  - Consumer lag grows: ~10M messages over 5 min             ││
│  │  - Lag = (200k - 100k) × 300s = 30M messages               ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ PHASE 2: PROCESS (during + after burst)                     ││
│  │                                                              ││
│  │  Enrichment + Resolution:                                    ││
│  │  - Process at maximum sustainable rate (100k/sec)           ││
│  │  - 8 enrichment instances                                   ││
│  │  - 8 resolution instances                                   ││
│  │                                                              ││
│  │  Redis:                                                      ││
│  │  - Aggregation buffers grow to ~2 GB                        ││
│  │  - Cache hit rate decreases (new IPs during burst)          ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ PHASE 3: DRAIN (after burst ends)                           ││
│  │                                                              ││
│  │  Timeline:                                                   ││
│  │  - Burst ends, rate returns to 50k/sec                      ││
│  │  - Surplus processing capacity: 50k/sec                     ││
│  │  - Lag drain time: 30M / 50k = 600 seconds (10 minutes)     ││
│  │                                                              ││
│  │  Total burst recovery: ~15 minutes                          ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Burst Resource Requirements:**

| Component | Burst Instances | Notes |
|-----------|-----------------|-------|
| Ingestion | 8 | Scale up 2x during burst |
| Enrichment | 8 | Pre-scaled |
| Resolution | 8 | Pre-scaled |
| Kafka | 3 brokers | Handles burst natively |
| Redis | 1 (8 GB) | Increase memory if needed |
| PostgreSQL | 1 | Not impacted (aggregated writes) |

---

## 7. Decision Thresholds

### 7.1 Summary Decision Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DECISION THRESHOLDS                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  FLOW RATE THRESHOLDS                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │  0 ─────── 5k ─────── 10k ─────── 50k ─────── 100k ─────── 200k+       ││
│  │  │         │          │           │           │            │           ││
│  │  │ PG Only │ PG Only  │ PG+Kafka  │ Full      │ Full       │ Cluster   ││
│  │  │         │ (tuned)  │ +Redis    │ Stack     │ (scaled)   │           ││
│  │  │         │          │           │           │            │           ││
│  │  └─────────┴──────────┴───────────┴───────────┴────────────┴───────────││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  API LATENCY THRESHOLDS                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │  p99 < 500ms        → PostgreSQL direct queries OK                     ││
│  │  p99 100-500ms      → Add Redis query caching                          ││
│  │  p99 < 100ms        → Redis required, consider read replicas           ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  CONCURRENT USERS                                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │  < 20 users         → In-memory session storage OK                     ││
│  │  20-100 users       → Redis for sessions + rate limiting               ││
│  │  > 100 users        → Redis required, multiple API instances           ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Configuration Knobs Reference

```yaml
# Master configuration with thresholds
flowlens:
  # Automatic mode selection
  mode: auto  # 'minimal', 'standard', 'full', or 'auto'

  thresholds:
    # Kafka activation
    kafka:
      enable_at_flows_per_sec: 10000
      disable_at_flows_per_sec: 5000  # Hysteresis
      burst_threshold_flows_per_sec: 30000
      burst_duration_trigger_seconds: 30

    # Redis activation
    redis:
      enable_at_flows_per_sec: 10000
      enable_at_concurrent_users: 20
      enable_at_api_p99_ms: 200
      enable_for_websocket: true  # Always if WebSocket enabled

    # PostgreSQL tuning triggers
    postgresql:
      enable_async_commit_at_flows_per_sec: 5000
      enable_batching_at_flows_per_sec: 1000
      batch_size_low: 100
      batch_size_high: 1000
      batch_timeout_ms: 100

  # Backpressure configuration
  backpressure:
    # Ingestion layer
    ingestion:
      max_queue_depth: 100000
      sample_at_queue_depth: 50000
      sample_rate: 10  # 1:10
      drop_at_queue_depth: 100000

    # Kafka consumer lag
    kafka:
      max_acceptable_lag_seconds: 300  # 5 minutes
      pause_at_lag_seconds: 600        # 10 minutes
      alert_at_lag_seconds: 180        # 3 minutes

    # PostgreSQL connection pool
    postgresql:
      pool_size: 50
      pool_overflow: 20
      pool_timeout_seconds: 30

  # Scaling triggers (for auto-scaling environments)
  autoscaling:
    ingestion:
      scale_up_at_cpu_percent: 70
      scale_down_at_cpu_percent: 30
      min_instances: 2
      max_instances: 16

    enrichment:
      scale_up_at_lag_seconds: 60
      scale_down_at_lag_seconds: 10
      min_instances: 2
      max_instances: 16

    api:
      scale_up_at_latency_p99_ms: 500
      scale_down_at_latency_p99_ms: 100
      min_instances: 2
      max_instances: 8
```

---

## 8. Backpressure Strategies

### 8.1 Ingestion Layer Backpressure

```python
class IngestionBackpressure:
    """
    Backpressure handling at the ingestion layer.

    Strategy:
    1. Monitor internal queue depth
    2. Apply sampling when queue grows
    3. Drop packets only as last resort
    4. Emit metrics for observability
    """

    def __init__(self, config: BackpressureConfig):
        self.queue = asyncio.Queue(maxsize=config.max_queue_depth)
        self.sample_threshold = config.sample_at_queue_depth
        self.drop_threshold = config.drop_at_queue_depth
        self.sample_rate = config.sample_rate
        self.sample_counter = 0

        # Metrics
        self.flows_received = Counter('flows_received_total')
        self.flows_sampled = Counter('flows_sampled_total')
        self.flows_dropped = Counter('flows_dropped_total')
        self.queue_depth = Gauge('ingestion_queue_depth')

    async def handle_flow(self, flow: FlowRecord) -> bool:
        """Returns True if flow was accepted, False if dropped."""
        queue_size = self.queue.qsize()
        self.queue_depth.set(queue_size)
        self.flows_received.inc()

        # Level 1: Normal operation
        if queue_size < self.sample_threshold:
            await self.queue.put(flow)
            return True

        # Level 2: Sampling mode
        elif queue_size < self.drop_threshold:
            self.sample_counter += 1
            if self.sample_counter % self.sample_rate == 0:
                await self.queue.put(flow)
                return True
            else:
                self.flows_sampled.inc()
                return False

        # Level 3: Drop mode
        else:
            self.flows_dropped.inc()
            return False
```

### 8.2 Kafka Consumer Backpressure

```python
class KafkaConsumerBackpressure:
    """
    Backpressure handling for Kafka consumers.

    Strategy:
    1. Monitor consumer lag
    2. Pause consumption if lag too high
    3. Resume when lag decreases
    4. Alert on sustained lag
    """

    def __init__(self, config: KafkaBackpressureConfig):
        self.consumer = AIOKafkaConsumer(...)
        self.max_lag = config.max_acceptable_lag_seconds
        self.pause_lag = config.pause_at_lag_seconds
        self.alert_lag = config.alert_at_lag_seconds
        self.paused = False

    async def check_lag(self):
        """Periodically check and respond to lag."""
        while True:
            lag_seconds = await self.calculate_lag_seconds()

            if lag_seconds > self.pause_lag and not self.paused:
                logger.warning(f"Pausing consumer: lag={lag_seconds}s")
                self.consumer.pause()
                self.paused = True
                await self.emit_alert("consumer_paused", lag_seconds)

            elif lag_seconds < self.max_lag and self.paused:
                logger.info(f"Resuming consumer: lag={lag_seconds}s")
                self.consumer.resume()
                self.paused = False

            elif lag_seconds > self.alert_lag:
                await self.emit_alert("high_lag", lag_seconds)

            await asyncio.sleep(10)

    async def calculate_lag_seconds(self) -> float:
        """Calculate lag in seconds based on timestamps."""
        # Get latest message timestamp from Kafka
        # Compare to current time
        # Return difference in seconds
        ...
```

### 8.3 PostgreSQL Backpressure

```python
class PostgreSQLBackpressure:
    """
    Backpressure handling for PostgreSQL writes.

    Strategy:
    1. Use connection pool with bounded size
    2. Queue writes with bounded depth
    3. Increase batch size under pressure
    4. Apply exponential backoff on failures
    """

    def __init__(self, pool: asyncpg.Pool, config: PostgresBackpressureConfig):
        self.pool = pool
        self.write_queue = asyncio.Queue(maxsize=config.max_queue_depth)
        self.batch_size = config.batch_size_low
        self.batch_size_high = config.batch_size_high
        self.backoff_seconds = 0.1
        self.max_backoff = 30.0

    async def write_batch(self, records: list[dict]) -> bool:
        """Write batch with backpressure handling."""
        while True:
            try:
                async with self.pool.acquire(timeout=30) as conn:
                    async with conn.transaction():
                        await self._insert_batch(conn, records)

                # Success - reset backoff
                self.backoff_seconds = 0.1
                return True

            except asyncpg.TooManyConnectionsError:
                # Pool exhausted - wait and retry
                logger.warning(f"Pool exhausted, backing off {self.backoff_seconds}s")
                await asyncio.sleep(self.backoff_seconds)
                self.backoff_seconds = min(
                    self.backoff_seconds * 2,
                    self.max_backoff
                )

            except Exception as e:
                logger.error(f"Write failed: {e}")
                await asyncio.sleep(self.backoff_seconds)
                self.backoff_seconds = min(
                    self.backoff_seconds * 2,
                    self.max_backoff
                )

    def adjust_batch_size(self, queue_depth: int, max_depth: int):
        """Dynamically adjust batch size based on queue pressure."""
        pressure = queue_depth / max_depth

        if pressure > 0.8:
            self.batch_size = self.batch_size_high
        elif pressure > 0.5:
            self.batch_size = (self.batch_size_low + self.batch_size_high) // 2
        else:
            self.batch_size = self.batch_size_low
```

---

## 9. Monitoring & Alerting

### 9.1 Key Metrics

```yaml
# Prometheus metrics to monitor

# Ingestion
flowlens_flows_received_total{exporter, protocol}
flowlens_flows_processed_total{service}
flowlens_flows_dropped_total{reason}  # "backpressure", "parse_error"
flowlens_flows_sampled_total
flowlens_ingestion_queue_depth
flowlens_ingestion_latency_seconds{quantile}

# Kafka
flowlens_kafka_consumer_lag_seconds{topic, partition, consumer_group}
flowlens_kafka_messages_produced_total{topic}
flowlens_kafka_messages_consumed_total{topic}

# PostgreSQL
flowlens_pg_connections_active
flowlens_pg_connections_waiting
flowlens_pg_write_latency_seconds{table, quantile}
flowlens_pg_writes_total{table}

# Redis
flowlens_redis_cache_hits_total{cache}
flowlens_redis_cache_misses_total{cache}
flowlens_redis_memory_used_bytes

# API
flowlens_api_requests_total{endpoint, method, status}
flowlens_api_latency_seconds{endpoint, quantile}
flowlens_websocket_connections_active
```

### 9.2 Alert Rules

```yaml
# Prometheus alerting rules

groups:
  - name: flowlens-ingestion
    rules:
      - alert: HighFlowDropRate
        expr: rate(flowlens_flows_dropped_total[5m]) > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High flow drop rate"
          description: "Dropping >1000 flows/sec for 5+ minutes"

      - alert: IngestionQueueFull
        expr: flowlens_ingestion_queue_depth > 80000
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Ingestion queue near capacity"

  - name: flowlens-kafka
    rules:
      - alert: KafkaConsumerLag
        expr: flowlens_kafka_consumer_lag_seconds > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Kafka consumer lag > 5 minutes"

      - alert: KafkaConsumerStalled
        expr: rate(flowlens_kafka_messages_consumed_total[5m]) == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Kafka consumer not processing messages"

  - name: flowlens-postgresql
    rules:
      - alert: PostgreSQLConnectionPoolExhausted
        expr: flowlens_pg_connections_waiting > 10
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Queries waiting for PostgreSQL connections"

      - alert: PostgreSQLWriteLatency
        expr: flowlens_pg_write_latency_seconds{quantile="0.99"} > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL p99 write latency > 1s"

  - name: flowlens-api
    rules:
      - alert: APIHighLatency
        expr: flowlens_api_latency_seconds{quantile="0.99"} > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API p99 latency > 2s"

      - alert: APIErrorRate
        expr: rate(flowlens_api_requests_total{status=~"5.."}[5m]) / rate(flowlens_api_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "API error rate > 5%"
```

---

## 10. Summary

### 10.1 Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────┐
│              FLOWLENS SCALING QUICK REFERENCE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  WHEN TO USE POSTGRESQL ONLY (Minimal Mode):                    │
│  ✓ Flow rate < 10,000/sec                                       │
│  ✓ Concurrent users < 20                                        │
│  ✓ API latency SLA > 500ms                                      │
│  ✓ No WebSocket requirement                                     │
│                                                                  │
│  WHEN TO ADD KAFKA:                                              │
│  ✓ Flow rate ≥ 10,000/sec                                       │
│  ✓ Burst handling required (> 3x sustained rate)                │
│  ✓ Multi-consumer (SIEM export, etc.)                           │
│  ✓ 7-day replay requirement                                     │
│                                                                  │
│  WHEN TO ADD REDIS:                                              │
│  ✓ Flow rate ≥ 10,000/sec (aggregation buffers)                 │
│  ✓ API latency SLA < 200ms                                      │
│  ✓ Concurrent users ≥ 20                                        │
│  ✓ Multiple API instances                                       │
│  ✓ WebSocket enabled                                            │
│                                                                  │
│  BACKPRESSURE DEFAULTS:                                          │
│  • Sample at 50k queue depth (1:10)                             │
│  • Drop at 100k queue depth                                      │
│  • Kafka lag alert at 3 min, pause at 10 min                    │
│  • PostgreSQL batch size: 100-1000 (auto-adjust)                │
│                                                                  │
│  CAPACITY RULES OF THUMB:                                        │
│  • 1 ingestion instance = 25k flows/sec                         │
│  • 1 Kafka broker = 200k flows/sec                              │
│  • 1 PostgreSQL = 50k aggregated writes/sec                     │
│  • 1 Redis (8GB) = 1M cached entries                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

*Document maintained by: Engineering Team*
*Last updated: 2024-12-24*
