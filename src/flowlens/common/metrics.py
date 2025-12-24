"""Prometheus metrics for FlowLens services.

Provides pre-defined metrics for monitoring flow ingestion, processing,
and API performance.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# Application info
APP_INFO = Info(
    "flowlens",
    "FlowLens application information",
)

# Flow ingestion metrics
FLOWS_RECEIVED = Counter(
    "flowlens_flows_received_total",
    "Total number of flow records received",
    ["protocol", "exporter"],
)

FLOWS_PARSED = Counter(
    "flowlens_flows_parsed_total",
    "Total number of flow records successfully parsed",
    ["protocol"],
)

FLOWS_PARSE_ERRORS = Counter(
    "flowlens_flows_parse_errors_total",
    "Total number of flow parse errors",
    ["protocol", "error_type"],
)

FLOWS_DROPPED = Counter(
    "flowlens_flows_dropped_total",
    "Total number of flow records dropped due to backpressure",
    ["reason"],
)

FLOWS_SAMPLED = Counter(
    "flowlens_flows_sampled_total",
    "Total number of flow records sampled (skipped) due to backpressure",
)

INGESTION_QUEUE_SIZE = Gauge(
    "flowlens_ingestion_queue_size",
    "Current size of the ingestion queue",
)

INGESTION_BATCH_SIZE = Histogram(
    "flowlens_ingestion_batch_size",
    "Size of ingestion batches",
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
)

INGESTION_LATENCY = Histogram(
    "flowlens_ingestion_latency_seconds",
    "Time to process and store a batch of flows",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# Enrichment metrics
ENRICHMENT_PROCESSED = Counter(
    "flowlens_enrichment_processed_total",
    "Total number of flows enriched",
)

ENRICHMENT_ERRORS = Counter(
    "flowlens_enrichment_errors_total",
    "Total number of enrichment errors",
    ["error_type"],
)

DNS_LOOKUPS = Counter(
    "flowlens_dns_lookups_total",
    "Total number of DNS lookups performed",
    ["status"],
)

DNS_CACHE_HITS = Counter(
    "flowlens_dns_cache_hits_total",
    "Total number of DNS cache hits",
)

DNS_CACHE_SIZE = Gauge(
    "flowlens_dns_cache_size",
    "Current size of DNS cache",
)

GEOIP_LOOKUPS = Counter(
    "flowlens_geoip_lookups_total",
    "Total number of GeoIP lookups",
    ["status"],
)

# Dependency resolution metrics
DEPENDENCIES_CREATED = Counter(
    "flowlens_dependencies_created_total",
    "Total number of new dependencies created",
)

DEPENDENCIES_UPDATED = Counter(
    "flowlens_dependencies_updated_total",
    "Total number of dependencies updated",
)

ASSETS_DISCOVERED = Counter(
    "flowlens_assets_discovered_total",
    "Total number of new assets discovered",
    ["asset_type"],
)

AGGREGATION_WINDOW_DURATION = Histogram(
    "flowlens_aggregation_window_duration_seconds",
    "Time to process an aggregation window",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# API metrics
API_REQUESTS = Counter(
    "flowlens_api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
)

API_REQUEST_DURATION = Histogram(
    "flowlens_api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

API_ACTIVE_REQUESTS = Gauge(
    "flowlens_api_active_requests",
    "Number of active API requests",
)

WEBSOCKET_CONNECTIONS = Gauge(
    "flowlens_websocket_connections",
    "Number of active WebSocket connections",
)

# Database metrics
DB_CONNECTIONS_ACTIVE = Gauge(
    "flowlens_db_connections_active",
    "Number of active database connections",
)

DB_CONNECTIONS_IDLE = Gauge(
    "flowlens_db_connections_idle",
    "Number of idle database connections",
)

DB_QUERY_DURATION = Histogram(
    "flowlens_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# Graph traversal metrics
GRAPH_TRAVERSAL_DURATION = Histogram(
    "flowlens_graph_traversal_duration_seconds",
    "Graph traversal query duration",
    ["operation"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

GRAPH_TRAVERSAL_NODES = Histogram(
    "flowlens_graph_traversal_nodes",
    "Number of nodes visited in graph traversal",
    ["operation"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
)

# Kafka metrics (when enabled)
KAFKA_MESSAGES_PRODUCED = Counter(
    "flowlens_kafka_messages_produced_total",
    "Total number of Kafka messages produced",
    ["topic"],
)

KAFKA_MESSAGES_CONSUMED = Counter(
    "flowlens_kafka_messages_consumed_total",
    "Total number of Kafka messages consumed",
    ["topic", "consumer_group"],
)

KAFKA_CONSUMER_LAG = Gauge(
    "flowlens_kafka_consumer_lag",
    "Kafka consumer lag",
    ["topic", "partition"],
)

# Redis metrics (when enabled)
REDIS_OPERATIONS = Counter(
    "flowlens_redis_operations_total",
    "Total number of Redis operations",
    ["operation", "status"],
)

REDIS_CACHE_HITS = Counter(
    "flowlens_redis_cache_hits_total",
    "Total number of Redis cache hits",
    ["cache_name"],
)

REDIS_CACHE_MISSES = Counter(
    "flowlens_redis_cache_misses_total",
    "Total number of Redis cache misses",
    ["cache_name"],
)


def set_app_info(version: str, environment: str, build_hash: str = "") -> None:
    """Set application info metric.

    Args:
        version: Application version.
        environment: Deployment environment.
        build_hash: Git commit hash or build identifier.
    """
    APP_INFO.info({
        "version": version,
        "environment": environment,
        "build_hash": build_hash,
    })
