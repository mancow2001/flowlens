"""Settings API schemas.

Provides response models for the settings management API with
field metadata for frontend form generation.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    """Field input types for frontend rendering."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SECRET = "secret"
    SELECT = "select"
    LIST = "list"
    PATH = "path"
    IP_ADDRESS = "ip_address"


class FieldMetadata(BaseModel):
    """Metadata for a settings field."""

    name: str
    label: str
    description: str | None = None
    field_type: FieldType
    required: bool = True
    default: Any = None
    min_value: int | float | None = None
    max_value: int | float | None = None
    options: list[str] | None = None  # For select fields
    env_var: str  # Environment variable name
    restart_required: bool = True
    is_secret: bool = False


class SettingsSectionInfo(BaseModel):
    """Information about a settings section."""

    key: str
    name: str
    description: str
    icon: str
    fields: list[FieldMetadata]
    restart_required: bool = True
    has_connection_test: bool = False


class SettingsValue(BaseModel):
    """A single setting value."""

    name: str
    value: Any
    is_default: bool = False


class SettingsSectionData(BaseModel):
    """Data for a settings section."""

    key: str
    values: list[SettingsValue]


class SettingsResponse(BaseModel):
    """Response containing all settings sections info."""

    sections: list[SettingsSectionInfo]
    restart_required: bool = False


class SettingsSectionResponse(BaseModel):
    """Response for a specific settings section."""

    section: SettingsSectionInfo
    data: SettingsSectionData
    restart_required: bool = False


class SettingsUpdateRequest(BaseModel):
    """Request to update settings in a section."""

    values: dict[str, Any]


class SettingsUpdateResponse(BaseModel):
    """Response after updating settings."""

    success: bool
    message: str
    restart_required: bool = False
    updated_fields: list[str] = Field(default_factory=list)
    docker_mode: bool = False  # True if running in Docker (env file not writable)


class ConnectionTestRequest(BaseModel):
    """Request to test a service connection."""

    # Optional override values for testing before saving
    test_values: dict[str, Any] | None = None


class ConnectionTestResponse(BaseModel):
    """Response from connection test."""

    success: bool
    message: str
    details: dict[str, Any] | None = None


class RestartResponse(BaseModel):
    """Response from restart request."""

    success: bool
    message: str
    method: Literal["docker", "manual"] | None = None


# Section definitions with field metadata
SETTINGS_SECTIONS: list[SettingsSectionInfo] = [
    SettingsSectionInfo(
        key="application",
        name="Application",
        description="Core application settings",
        icon="Cog6ToothIcon",
        restart_required=True,
        fields=[
            FieldMetadata(
                name="app_name",
                label="Application Name",
                description="Display name for the application",
                field_type=FieldType.STRING,
                env_var="APP_NAME",
                default="FlowLens",
            ),
            FieldMetadata(
                name="app_version",
                label="Version",
                description="Application version (read-only)",
                field_type=FieldType.STRING,
                env_var="APP_VERSION",
                default="0.1.0",
                required=False,
            ),
            FieldMetadata(
                name="environment",
                label="Environment",
                description="Deployment environment",
                field_type=FieldType.SELECT,
                options=["development", "staging", "production"],
                env_var="ENVIRONMENT",
                default="development",
            ),
            FieldMetadata(
                name="debug",
                label="Debug Mode",
                description="Enable debug logging and features",
                field_type=FieldType.BOOLEAN,
                env_var="DEBUG",
                default=False,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="database",
        name="Database",
        description="PostgreSQL database connection settings",
        icon="CircleStackIcon",
        restart_required=True,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="host",
                label="Host",
                description="PostgreSQL server hostname or IP",
                field_type=FieldType.STRING,
                env_var="POSTGRES_HOST",
                default="localhost",
            ),
            FieldMetadata(
                name="port",
                label="Port",
                description="PostgreSQL server port",
                field_type=FieldType.INTEGER,
                env_var="POSTGRES_PORT",
                default=5432,
                min_value=1,
                max_value=65535,
            ),
            FieldMetadata(
                name="user",
                label="Username",
                description="Database username",
                field_type=FieldType.STRING,
                env_var="POSTGRES_USER",
                default="flowlens",
            ),
            FieldMetadata(
                name="password",
                label="Password",
                description="Database password",
                field_type=FieldType.SECRET,
                env_var="POSTGRES_PASSWORD",
                default="flowlens",
                is_secret=True,
            ),
            FieldMetadata(
                name="database",
                label="Database Name",
                description="PostgreSQL database name",
                field_type=FieldType.STRING,
                env_var="POSTGRES_DATABASE",
                default="flowlens",
            ),
            FieldMetadata(
                name="pool_size",
                label="Pool Size",
                description="Number of connections to maintain in the pool",
                field_type=FieldType.INTEGER,
                env_var="POSTGRES_POOL_SIZE",
                default=20,
                min_value=1,
                max_value=100,
            ),
            FieldMetadata(
                name="max_overflow",
                label="Max Overflow",
                description="Maximum overflow connections beyond pool size",
                field_type=FieldType.INTEGER,
                env_var="POSTGRES_MAX_OVERFLOW",
                default=10,
                min_value=0,
                max_value=50,
            ),
            FieldMetadata(
                name="pool_timeout",
                label="Pool Timeout",
                description="Seconds to wait for connection from pool",
                field_type=FieldType.INTEGER,
                env_var="POSTGRES_POOL_TIMEOUT",
                default=30,
                min_value=1,
            ),
            FieldMetadata(
                name="pool_recycle",
                label="Pool Recycle",
                description="Seconds before recycling connections",
                field_type=FieldType.INTEGER,
                env_var="POSTGRES_POOL_RECYCLE",
                default=1800,
                min_value=60,
            ),
            FieldMetadata(
                name="echo",
                label="Echo SQL",
                description="Log all SQL statements (debug)",
                field_type=FieldType.BOOLEAN,
                env_var="POSTGRES_ECHO",
                default=False,
            ),
            FieldMetadata(
                name="echo_pool",
                label="Echo Pool",
                description="Log connection pool activity (debug)",
                field_type=FieldType.BOOLEAN,
                env_var="POSTGRES_ECHO_POOL",
                default=False,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="redis",
        name="Redis",
        description="Redis cache configuration (optional, for scaling)",
        icon="BoltIcon",
        restart_required=True,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable Redis caching",
                field_type=FieldType.BOOLEAN,
                env_var="REDIS_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="host",
                label="Host",
                description="Redis server hostname",
                field_type=FieldType.STRING,
                env_var="REDIS_HOST",
                default="localhost",
            ),
            FieldMetadata(
                name="port",
                label="Port",
                description="Redis server port",
                field_type=FieldType.INTEGER,
                env_var="REDIS_PORT",
                default=6379,
                min_value=1,
                max_value=65535,
            ),
            FieldMetadata(
                name="password",
                label="Password",
                description="Redis password (optional)",
                field_type=FieldType.SECRET,
                env_var="REDIS_PASSWORD",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="database",
                label="Database",
                description="Redis database number",
                field_type=FieldType.INTEGER,
                env_var="REDIS_DATABASE",
                default=0,
                min_value=0,
                max_value=15,
            ),
            FieldMetadata(
                name="ssl",
                label="Use SSL/TLS",
                description="Enable TLS encryption",
                field_type=FieldType.BOOLEAN,
                env_var="REDIS_SSL",
                default=False,
            ),
            FieldMetadata(
                name="pool_size",
                label="Pool Size",
                description="Connection pool size",
                field_type=FieldType.INTEGER,
                env_var="REDIS_POOL_SIZE",
                default=10,
                min_value=1,
                max_value=100,
            ),
            FieldMetadata(
                name="socket_timeout",
                label="Socket Timeout",
                description="Socket timeout in seconds",
                field_type=FieldType.FLOAT,
                env_var="REDIS_SOCKET_TIMEOUT",
                default=5.0,
                min_value=0.1,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="kafka",
        name="Kafka",
        description="Kafka message queue (optional, for high-scale ingestion)",
        icon="ArrowsRightLeftIcon",
        restart_required=True,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable Kafka integration",
                field_type=FieldType.BOOLEAN,
                env_var="KAFKA_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="bootstrap_servers",
                label="Bootstrap Servers",
                description="Comma-separated list of Kafka brokers",
                field_type=FieldType.STRING,
                env_var="KAFKA_BOOTSTRAP_SERVERS",
                default="localhost:9092",
            ),
            FieldMetadata(
                name="topic_flows",
                label="Raw Flows Topic",
                description="Topic for raw flow data",
                field_type=FieldType.STRING,
                env_var="KAFKA_TOPIC_FLOWS",
                default="flowlens.flows.raw",
            ),
            FieldMetadata(
                name="topic_enriched",
                label="Enriched Flows Topic",
                description="Topic for enriched flow data",
                field_type=FieldType.STRING,
                env_var="KAFKA_TOPIC_ENRICHED",
                default="flowlens.flows.enriched",
            ),
            FieldMetadata(
                name="consumer_group",
                label="Consumer Group",
                description="Kafka consumer group ID",
                field_type=FieldType.STRING,
                env_var="KAFKA_CONSUMER_GROUP",
                default="flowlens",
            ),
            FieldMetadata(
                name="batch_size",
                label="Batch Size",
                description="Producer batch size in bytes",
                field_type=FieldType.INTEGER,
                env_var="KAFKA_BATCH_SIZE",
                default=16384,
                min_value=1024,
            ),
            FieldMetadata(
                name="linger_ms",
                label="Linger (ms)",
                description="Time to wait before sending batch",
                field_type=FieldType.INTEGER,
                env_var="KAFKA_LINGER_MS",
                default=10,
                min_value=0,
            ),
            FieldMetadata(
                name="compression",
                label="Compression",
                description="Message compression algorithm",
                field_type=FieldType.SELECT,
                options=["none", "gzip", "snappy", "lz4", "zstd"],
                env_var="KAFKA_COMPRESSION",
                default="lz4",
            ),
            FieldMetadata(
                name="auto_offset_reset",
                label="Auto Offset Reset",
                description="Where to start consuming when no offset exists",
                field_type=FieldType.SELECT,
                options=["earliest", "latest"],
                env_var="KAFKA_AUTO_OFFSET_RESET",
                default="latest",
            ),
            FieldMetadata(
                name="max_poll_records",
                label="Max Poll Records",
                description="Maximum records per poll",
                field_type=FieldType.INTEGER,
                env_var="KAFKA_MAX_POLL_RECORDS",
                default=500,
                min_value=1,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="ingestion",
        name="Ingestion",
        description="Flow ingestion service settings",
        icon="ArrowDownTrayIcon",
        restart_required=True,
        fields=[
            FieldMetadata(
                name="bind_address",
                label="Bind Address",
                description="IP address to bind UDP listeners",
                field_type=FieldType.IP_ADDRESS,
                env_var="INGESTION_BIND_ADDRESS",
                default="0.0.0.0",
            ),
            FieldMetadata(
                name="netflow_port",
                label="NetFlow Port",
                description="UDP port for NetFlow/IPFIX",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_NETFLOW_PORT",
                default=2055,
                min_value=1,
                max_value=65535,
            ),
            FieldMetadata(
                name="sflow_port",
                label="sFlow Port",
                description="UDP port for sFlow",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_SFLOW_PORT",
                default=6343,
                min_value=1,
                max_value=65535,
            ),
            FieldMetadata(
                name="batch_size",
                label="Batch Size",
                description="Flows per batch for processing",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_BATCH_SIZE",
                default=1000,
                min_value=100,
                max_value=10000,
            ),
            FieldMetadata(
                name="batch_timeout_ms",
                label="Batch Timeout (ms)",
                description="Max time to wait for full batch",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_BATCH_TIMEOUT_MS",
                default=1000,
                min_value=100,
            ),
            FieldMetadata(
                name="queue_max_size",
                label="Max Queue Size",
                description="Maximum flows in processing queue",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_QUEUE_MAX_SIZE",
                default=100000,
                min_value=1000,
            ),
            FieldMetadata(
                name="sample_threshold",
                label="Sample Threshold",
                description="Queue size to start sampling",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_SAMPLE_THRESHOLD",
                default=50000,
                min_value=1000,
            ),
            FieldMetadata(
                name="drop_threshold",
                label="Drop Threshold",
                description="Queue size to start dropping (must be > sample threshold)",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_DROP_THRESHOLD",
                default=80000,
                min_value=1000,
            ),
            FieldMetadata(
                name="sample_rate",
                label="Sample Rate",
                description="Keep 1 in N flows when sampling",
                field_type=FieldType.INTEGER,
                env_var="INGESTION_SAMPLE_RATE",
                default=10,
                min_value=2,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="enrichment",
        name="Enrichment",
        description="Flow enrichment service settings",
        icon="SparklesIcon",
        restart_required=True,
        fields=[
            FieldMetadata(
                name="batch_size",
                label="Batch Size",
                description="Flows per enrichment batch",
                field_type=FieldType.INTEGER,
                env_var="ENRICHMENT_BATCH_SIZE",
                default=500,
                min_value=50,
                max_value=5000,
            ),
            FieldMetadata(
                name="poll_interval_ms",
                label="Poll Interval (ms)",
                description="Time between queue polls",
                field_type=FieldType.INTEGER,
                env_var="ENRICHMENT_POLL_INTERVAL_MS",
                default=100,
                min_value=10,
            ),
            FieldMetadata(
                name="worker_count",
                label="Worker Count",
                description="Number of enrichment workers",
                field_type=FieldType.INTEGER,
                env_var="ENRICHMENT_WORKER_COUNT",
                default=4,
                min_value=1,
                max_value=32,
            ),
            FieldMetadata(
                name="dns_timeout",
                label="DNS Timeout",
                description="DNS lookup timeout in seconds",
                field_type=FieldType.FLOAT,
                env_var="ENRICHMENT_DNS_TIMEOUT",
                default=2.0,
                min_value=0.1,
            ),
            FieldMetadata(
                name="dns_cache_ttl",
                label="DNS Cache TTL",
                description="DNS cache entry lifetime in seconds",
                field_type=FieldType.INTEGER,
                env_var="ENRICHMENT_DNS_CACHE_TTL",
                default=3600,
                min_value=60,
            ),
            FieldMetadata(
                name="dns_cache_size",
                label="DNS Cache Size",
                description="Maximum DNS cache entries",
                field_type=FieldType.INTEGER,
                env_var="ENRICHMENT_DNS_CACHE_SIZE",
                default=10000,
                min_value=100,
            ),
            FieldMetadata(
                name="dns_servers",
                label="DNS Servers",
                description="Custom DNS servers (comma-separated)",
                field_type=FieldType.STRING,
                env_var="ENRICHMENT_DNS_SERVERS",
                required=False,
            ),
            FieldMetadata(
                name="geoip_database_path",
                label="GeoIP Database Path",
                description="Path to MaxMind GeoLite2 database",
                field_type=FieldType.PATH,
                env_var="ENRICHMENT_GEOIP_DATABASE_PATH",
                required=False,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="resolution",
        name="Resolution",
        description="Dependency resolution service settings",
        icon="ShareIcon",
        restart_required=False,
        fields=[
            FieldMetadata(
                name="window_size_minutes",
                label="Aggregation Window",
                description="Flow aggregation window in minutes",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_WINDOW_SIZE_MINUTES",
                default=5,
                min_value=1,
                max_value=60,
            ),
            FieldMetadata(
                name="worker_count",
                label="Worker Count",
                description="Number of resolution workers",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_WORKER_COUNT",
                default=1,
                min_value=1,
                max_value=16,
            ),
            FieldMetadata(
                name="batch_size",
                label="Batch Size",
                description="Aggregates per batch",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_BATCH_SIZE",
                default=1000,
                min_value=100,
            ),
            FieldMetadata(
                name="poll_interval_ms",
                label="Poll Interval (ms)",
                description="Time between aggregate polls",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_POLL_INTERVAL_MS",
                default=500,
                min_value=100,
            ),
            FieldMetadata(
                name="detection_interval_minutes",
                label="Detection Interval",
                description="Minutes between dependency detection runs",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_DETECTION_INTERVAL_MINUTES",
                default=5,
                min_value=1,
                max_value=60,
            ),
            FieldMetadata(
                name="stale_threshold_hours",
                label="Stale Threshold",
                description="Hours before marking dependency as stale",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_STALE_THRESHOLD_HOURS",
                default=24,
                min_value=1,
            ),
            FieldMetadata(
                name="new_dependency_lookback_minutes",
                label="Lookback Window",
                description="Minutes to look back for new dependencies",
                field_type=FieldType.INTEGER,
                env_var="RESOLUTION_NEW_DEPENDENCY_LOOKBACK_MINUTES",
                default=30,
                min_value=5,
            ),
            FieldMetadata(
                name="discard_external_flows",
                label="Discard External Flows",
                description="Discard all flows involving external (non-RFC1918/non-private IPv6) IPs. External flows will not be mapped as dependencies. When enabled, the options below are hidden.",
                field_type=FieldType.BOOLEAN,
                env_var="RESOLUTION_DISCARD_EXTERNAL_FLOWS",
                default=True,
            ),
            FieldMetadata(
                name="exclude_external_ips",
                label="Exclude External IPs",
                description="Exclude non-private IPs from dependencies (only applies when 'Discard External Flows' is disabled)",
                field_type=FieldType.BOOLEAN,
                env_var="RESOLUTION_EXCLUDE_EXTERNAL_IPS",
                default=False,
            ),
            FieldMetadata(
                name="exclude_external_sources",
                label="Exclude External Sources",
                description="Exclude dependencies with external sources (only applies when 'Discard External Flows' is disabled)",
                field_type=FieldType.BOOLEAN,
                env_var="RESOLUTION_EXCLUDE_EXTERNAL_SOURCES",
                default=False,
            ),
            FieldMetadata(
                name="exclude_external_targets",
                label="Exclude External Targets",
                description="Exclude dependencies with external targets (only applies when 'Discard External Flows' is disabled)",
                field_type=FieldType.BOOLEAN,
                env_var="RESOLUTION_EXCLUDE_EXTERNAL_TARGETS",
                default=False,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="classification",
        name="Classification",
        description="Asset auto-classification engine settings",
        icon="SparklesIcon",
        restart_required=True,
        fields=[
            FieldMetadata(
                name="poll_interval_ms",
                label="Poll Interval (ms)",
                description="Time between classification runs",
                field_type=FieldType.INTEGER,
                env_var="CLASSIFICATION_POLL_INTERVAL_MS",
                default=30000,
                min_value=1000,
                max_value=300000,
            ),
            FieldMetadata(
                name="batch_size",
                label="Batch Size",
                description="Assets to classify per batch",
                field_type=FieldType.INTEGER,
                env_var="CLASSIFICATION_BATCH_SIZE",
                default=100,
                min_value=10,
                max_value=1000,
            ),
            FieldMetadata(
                name="worker_count",
                label="Worker Count",
                description="Number of classification workers",
                field_type=FieldType.INTEGER,
                env_var="CLASSIFICATION_WORKER_COUNT",
                default=1,
                min_value=1,
                max_value=8,
            ),
            FieldMetadata(
                name="min_observation_hours",
                label="Min Observation Hours",
                description="Minimum hours of traffic data before classifying",
                field_type=FieldType.INTEGER,
                env_var="CLASSIFICATION_MIN_OBSERVATION_HOURS",
                default=24,
                min_value=1,
                max_value=168,
            ),
            FieldMetadata(
                name="min_flows_required",
                label="Min Flows Required",
                description="Minimum flow count before classifying",
                field_type=FieldType.INTEGER,
                env_var="CLASSIFICATION_MIN_FLOWS_REQUIRED",
                default=100,
                min_value=10,
                max_value=10000,
            ),
            FieldMetadata(
                name="auto_update_confidence_threshold",
                label="Auto-Update Threshold",
                description="Confidence threshold for auto-updating asset type (0.0-1.0)",
                field_type=FieldType.FLOAT,
                env_var="CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD",
                default=0.70,
                min_value=0.0,
                max_value=1.0,
            ),
            FieldMetadata(
                name="high_confidence_threshold",
                label="High Confidence Threshold",
                description="Threshold for high confidence classification (0.0-1.0)",
                field_type=FieldType.FLOAT,
                env_var="CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD",
                default=0.85,
                min_value=0.0,
                max_value=1.0,
            ),
            FieldMetadata(
                name="reclassify_interval_hours",
                label="Reclassify Interval (hours)",
                description="Hours between reclassification attempts",
                field_type=FieldType.INTEGER,
                env_var="CLASSIFICATION_RECLASSIFY_INTERVAL_HOURS",
                default=24,
                min_value=1,
                max_value=168,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="api",
        name="API",
        description="REST API server settings",
        icon="GlobeAltIcon",
        restart_required=True,
        fields=[
            FieldMetadata(
                name="host",
                label="Host",
                description="API server bind address",
                field_type=FieldType.STRING,
                env_var="API_HOST",
                default="0.0.0.0",
            ),
            FieldMetadata(
                name="port",
                label="Port",
                description="API server port",
                field_type=FieldType.INTEGER,
                env_var="API_PORT",
                default=8000,
                min_value=1,
                max_value=65535,
            ),
            FieldMetadata(
                name="workers",
                label="Workers",
                description="Number of API workers",
                field_type=FieldType.INTEGER,
                env_var="API_WORKERS",
                default=4,
                min_value=1,
                max_value=32,
            ),
            FieldMetadata(
                name="reload",
                label="Auto Reload",
                description="Reload on code changes (development only)",
                field_type=FieldType.BOOLEAN,
                env_var="API_RELOAD",
                default=False,
            ),
            FieldMetadata(
                name="cors_origins",
                label="CORS Origins",
                description="Allowed CORS origins (comma-separated, or * for all)",
                field_type=FieldType.STRING,
                env_var="API_CORS_ORIGINS",
                default="*",
            ),
            FieldMetadata(
                name="rate_limit_requests",
                label="Rate Limit",
                description="Max requests per rate limit window",
                field_type=FieldType.INTEGER,
                env_var="API_RATE_LIMIT_REQUESTS",
                default=100,
                min_value=1,
            ),
            FieldMetadata(
                name="rate_limit_window_seconds",
                label="Rate Limit Window",
                description="Rate limit window in seconds",
                field_type=FieldType.INTEGER,
                env_var="API_RATE_LIMIT_WINDOW_SECONDS",
                default=60,
                min_value=1,
            ),
            FieldMetadata(
                name="default_page_size",
                label="Default Page Size",
                description="Default pagination size",
                field_type=FieldType.INTEGER,
                env_var="API_DEFAULT_PAGE_SIZE",
                default=50,
                min_value=1,
                max_value=1000,
            ),
            FieldMetadata(
                name="max_page_size",
                label="Max Page Size",
                description="Maximum pagination size",
                field_type=FieldType.INTEGER,
                env_var="API_MAX_PAGE_SIZE",
                default=1000,
                min_value=1,
                max_value=10000,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="auth",
        name="Authentication",
        description="Authentication and security settings",
        icon="LockClosedIcon",
        restart_required=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable authentication",
                field_type=FieldType.BOOLEAN,
                env_var="AUTH_ENABLED",
                default=True,
            ),
            FieldMetadata(
                name="secret_key",
                label="Secret Key",
                description="JWT signing secret (keep secure!)",
                field_type=FieldType.SECRET,
                env_var="AUTH_SECRET_KEY",
                is_secret=True,
            ),
            FieldMetadata(
                name="algorithm",
                label="Algorithm",
                description="JWT signing algorithm",
                field_type=FieldType.SELECT,
                options=["HS256", "HS384", "HS512"],
                env_var="AUTH_ALGORITHM",
                default="HS256",
            ),
            FieldMetadata(
                name="access_token_expire_minutes",
                label="Access Token Expiry",
                description="Access token lifetime in minutes",
                field_type=FieldType.INTEGER,
                env_var="AUTH_ACCESS_TOKEN_EXPIRE_MINUTES",
                default=30,
                min_value=1,
            ),
            FieldMetadata(
                name="refresh_token_expire_days",
                label="Refresh Token Expiry",
                description="Refresh token lifetime in days",
                field_type=FieldType.INTEGER,
                env_var="AUTH_REFRESH_TOKEN_EXPIRE_DAYS",
                default=7,
                min_value=1,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="logging",
        name="Logging",
        description="Application logging settings",
        icon="DocumentTextIcon",
        restart_required=False,
        fields=[
            FieldMetadata(
                name="level",
                label="Log Level",
                description="Minimum log level to output",
                field_type=FieldType.SELECT,
                options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                env_var="LOG_LEVEL",
                default="INFO",
            ),
            FieldMetadata(
                name="format",
                label="Log Format",
                description="Log output format",
                field_type=FieldType.SELECT,
                options=["json", "console"],
                env_var="LOG_FORMAT",
                default="json",
            ),
            FieldMetadata(
                name="include_timestamp",
                label="Include Timestamp",
                description="Add timestamps to log entries",
                field_type=FieldType.BOOLEAN,
                env_var="LOG_INCLUDE_TIMESTAMP",
                default=True,
            ),
            FieldMetadata(
                name="include_caller",
                label="Include Caller",
                description="Add caller info to log entries",
                field_type=FieldType.BOOLEAN,
                env_var="LOG_INCLUDE_CALLER",
                default=True,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="email",
        name="Email",
        description="Email notification settings",
        icon="EnvelopeIcon",
        restart_required=False,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable email notifications",
                field_type=FieldType.BOOLEAN,
                env_var="EMAIL_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="host",
                label="SMTP Host",
                description="SMTP server hostname",
                field_type=FieldType.STRING,
                env_var="EMAIL_HOST",
                default="localhost",
            ),
            FieldMetadata(
                name="port",
                label="SMTP Port",
                description="SMTP server port",
                field_type=FieldType.INTEGER,
                env_var="EMAIL_PORT",
                default=587,
                min_value=1,
                max_value=65535,
            ),
            FieldMetadata(
                name="username",
                label="Username",
                description="SMTP authentication username",
                field_type=FieldType.STRING,
                env_var="EMAIL_USERNAME",
                required=False,
            ),
            FieldMetadata(
                name="password",
                label="Password",
                description="SMTP authentication password",
                field_type=FieldType.SECRET,
                env_var="EMAIL_PASSWORD",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="use_tls",
                label="Use TLS",
                description="Use TLS encryption",
                field_type=FieldType.BOOLEAN,
                env_var="EMAIL_USE_TLS",
                default=True,
            ),
            FieldMetadata(
                name="start_tls",
                label="STARTTLS",
                description="Use STARTTLS upgrade",
                field_type=FieldType.BOOLEAN,
                env_var="EMAIL_START_TLS",
                default=True,
            ),
            FieldMetadata(
                name="from_address",
                label="From Address",
                description="Sender email address",
                field_type=FieldType.STRING,
                env_var="EMAIL_FROM_ADDRESS",
                default="flowlens@localhost",
            ),
            FieldMetadata(
                name="from_name",
                label="From Name",
                description="Sender display name",
                field_type=FieldType.STRING,
                env_var="EMAIL_FROM_NAME",
                default="FlowLens",
            ),
            FieldMetadata(
                name="timeout",
                label="Timeout",
                description="Connection timeout in seconds",
                field_type=FieldType.INTEGER,
                env_var="EMAIL_TIMEOUT",
                default=30,
                min_value=1,
            ),
            FieldMetadata(
                name="validate_certs",
                label="Validate Certificates",
                description="Verify SSL/TLS certificates",
                field_type=FieldType.BOOLEAN,
                env_var="EMAIL_VALIDATE_CERTS",
                default=True,
            ),
            FieldMetadata(
                name="alert_recipients",
                label="Alert Recipients",
                description="Default alert email recipients (comma-separated)",
                field_type=FieldType.STRING,
                env_var="EMAIL_ALERT_RECIPIENTS",
                required=False,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="webhook",
        name="Webhook",
        description="Webhook notification settings",
        icon="LinkIcon",
        restart_required=False,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable webhook notifications",
                field_type=FieldType.BOOLEAN,
                env_var="WEBHOOK_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="url",
                label="Webhook URL",
                description="Webhook endpoint URL",
                field_type=FieldType.STRING,
                env_var="WEBHOOK_URL",
                required=False,
            ),
            FieldMetadata(
                name="secret",
                label="HMAC Secret",
                description="Secret for HMAC signature verification",
                field_type=FieldType.SECRET,
                env_var="WEBHOOK_SECRET",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="timeout",
                label="Timeout",
                description="Request timeout in seconds",
                field_type=FieldType.INTEGER,
                env_var="WEBHOOK_TIMEOUT",
                default=30,
                min_value=1,
                max_value=120,
            ),
            FieldMetadata(
                name="retry_count",
                label="Retry Count",
                description="Number of retry attempts",
                field_type=FieldType.INTEGER,
                env_var="WEBHOOK_RETRY_COUNT",
                default=3,
                min_value=0,
                max_value=10,
            ),
            FieldMetadata(
                name="retry_delay",
                label="Retry Delay",
                description="Base delay between retries (seconds)",
                field_type=FieldType.FLOAT,
                env_var="WEBHOOK_RETRY_DELAY",
                default=1.0,
                min_value=0.1,
                max_value=30.0,
            ),
            FieldMetadata(
                name="headers_json",
                label="Custom Headers",
                description="Custom headers as JSON object",
                field_type=FieldType.STRING,
                env_var="WEBHOOK_HEADERS_JSON",
                required=False,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="slack",
        name="Slack",
        description="Slack notification settings",
        icon="ChatBubbleLeftRightIcon",
        restart_required=False,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable Slack notifications",
                field_type=FieldType.BOOLEAN,
                env_var="SLACK_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="webhook_url",
                label="Webhook URL",
                description="Slack incoming webhook URL",
                field_type=FieldType.SECRET,
                env_var="SLACK_WEBHOOK_URL",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="default_channel",
                label="Default Channel",
                description="Channel override (optional)",
                field_type=FieldType.STRING,
                env_var="SLACK_DEFAULT_CHANNEL",
                required=False,
            ),
            FieldMetadata(
                name="username",
                label="Bot Username",
                description="Display name for messages",
                field_type=FieldType.STRING,
                env_var="SLACK_USERNAME",
                default="FlowLens",
            ),
            FieldMetadata(
                name="icon_emoji",
                label="Bot Emoji",
                description="Emoji icon for messages",
                field_type=FieldType.STRING,
                env_var="SLACK_ICON_EMOJI",
                default=":bell:",
            ),
            FieldMetadata(
                name="timeout",
                label="Timeout",
                description="Request timeout in seconds",
                field_type=FieldType.INTEGER,
                env_var="SLACK_TIMEOUT",
                default=30,
                min_value=1,
                max_value=120,
            ),
            FieldMetadata(
                name="retry_count",
                label="Retry Count",
                description="Number of retry attempts",
                field_type=FieldType.INTEGER,
                env_var="SLACK_RETRY_COUNT",
                default=3,
                min_value=0,
                max_value=10,
            ),
            FieldMetadata(
                name="retry_delay",
                label="Retry Delay",
                description="Base delay between retries (seconds)",
                field_type=FieldType.FLOAT,
                env_var="SLACK_RETRY_DELAY",
                default=1.0,
                min_value=0.1,
                max_value=30.0,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="teams",
        name="Microsoft Teams",
        description="Microsoft Teams notification settings",
        icon="ChatBubbleOvalLeftIcon",
        restart_required=False,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable Teams notifications",
                field_type=FieldType.BOOLEAN,
                env_var="TEAMS_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="webhook_url",
                label="Webhook URL",
                description="Teams incoming webhook URL",
                field_type=FieldType.SECRET,
                env_var="TEAMS_WEBHOOK_URL",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="timeout",
                label="Timeout",
                description="Request timeout in seconds",
                field_type=FieldType.INTEGER,
                env_var="TEAMS_TIMEOUT",
                default=30,
                min_value=1,
                max_value=120,
            ),
            FieldMetadata(
                name="retry_count",
                label="Retry Count",
                description="Number of retry attempts",
                field_type=FieldType.INTEGER,
                env_var="TEAMS_RETRY_COUNT",
                default=3,
                min_value=0,
                max_value=10,
            ),
            FieldMetadata(
                name="retry_delay",
                label="Retry Delay",
                description="Base delay between retries (seconds)",
                field_type=FieldType.FLOAT,
                env_var="TEAMS_RETRY_DELAY",
                default=1.0,
                min_value=0.1,
                max_value=30.0,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="pagerduty",
        name="PagerDuty",
        description="PagerDuty notification settings",
        icon="BellAlertIcon",
        restart_required=False,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable PagerDuty notifications",
                field_type=FieldType.BOOLEAN,
                env_var="PAGERDUTY_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="routing_key",
                label="Routing Key",
                description="PagerDuty integration/routing key",
                field_type=FieldType.SECRET,
                env_var="PAGERDUTY_ROUTING_KEY",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="service_name",
                label="Service Name",
                description="Service name in PagerDuty",
                field_type=FieldType.STRING,
                env_var="PAGERDUTY_SERVICE_NAME",
                default="FlowLens",
            ),
            FieldMetadata(
                name="timeout",
                label="Timeout",
                description="Request timeout in seconds",
                field_type=FieldType.INTEGER,
                env_var="PAGERDUTY_TIMEOUT",
                default=30,
                min_value=1,
                max_value=120,
            ),
            FieldMetadata(
                name="retry_count",
                label="Retry Count",
                description="Number of retry attempts",
                field_type=FieldType.INTEGER,
                env_var="PAGERDUTY_RETRY_COUNT",
                default=3,
                min_value=0,
                max_value=10,
            ),
            FieldMetadata(
                name="retry_delay",
                label="Retry Delay",
                description="Base delay between retries (seconds)",
                field_type=FieldType.FLOAT,
                env_var="PAGERDUTY_RETRY_DELAY",
                default=1.0,
                min_value=0.1,
                max_value=30.0,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="kubernetes",
        name="Kubernetes",
        description="Kubernetes cluster discovery for asset enrichment",
        icon="ShareIcon",
        restart_required=True,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable Kubernetes discovery",
                field_type=FieldType.BOOLEAN,
                env_var="K8S_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="api_server",
                label="API Server",
                description="Kubernetes API server URL",
                field_type=FieldType.STRING,
                env_var="K8S_API_SERVER",
                default="https://kubernetes.default.svc",
            ),
            FieldMetadata(
                name="cluster_name",
                label="Cluster Name",
                description="Name to identify this cluster",
                field_type=FieldType.STRING,
                env_var="K8S_CLUSTER_NAME",
                default="default-cluster",
            ),
            FieldMetadata(
                name="namespace",
                label="Namespace",
                description="Limit discovery to specific namespace (blank for all)",
                field_type=FieldType.STRING,
                env_var="K8S_NAMESPACE",
                required=False,
            ),
            FieldMetadata(
                name="token",
                label="Service Account Token",
                description="Bearer token for API authentication",
                field_type=FieldType.SECRET,
                env_var="K8S_TOKEN",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="token_file",
                label="Token File Path",
                description="Path to token file (for in-cluster auth)",
                field_type=FieldType.PATH,
                env_var="K8S_TOKEN_FILE",
                default="/var/run/secrets/kubernetes.io/serviceaccount/token",
                required=False,
            ),
            FieldMetadata(
                name="ca_cert_path",
                label="CA Certificate Path",
                description="Path to CA certificate for TLS verification",
                field_type=FieldType.PATH,
                env_var="K8S_CA_CERT_PATH",
                default="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
                required=False,
            ),
            FieldMetadata(
                name="verify_ssl",
                label="Verify SSL",
                description="Verify TLS certificates",
                field_type=FieldType.BOOLEAN,
                env_var="K8S_VERIFY_SSL",
                default=True,
            ),
            FieldMetadata(
                name="timeout_seconds",
                label="Timeout (seconds)",
                description="API request timeout",
                field_type=FieldType.FLOAT,
                env_var="K8S_TIMEOUT_SECONDS",
                default=10.0,
                min_value=1.0,
                max_value=60.0,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="vcenter",
        name="VMware vCenter",
        description="VMware vCenter discovery for VM asset enrichment",
        icon="ShareIcon",
        restart_required=True,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable vCenter discovery",
                field_type=FieldType.BOOLEAN,
                env_var="VCENTER_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="api_url",
                label="API URL",
                description="vCenter server URL",
                field_type=FieldType.STRING,
                env_var="VCENTER_API_URL",
                default="https://vcenter.local",
            ),
            FieldMetadata(
                name="username",
                label="Username",
                description="vCenter username",
                field_type=FieldType.STRING,
                env_var="VCENTER_USERNAME",
                required=False,
            ),
            FieldMetadata(
                name="password",
                label="Password",
                description="vCenter password",
                field_type=FieldType.SECRET,
                env_var="VCENTER_PASSWORD",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="verify_ssl",
                label="Verify SSL",
                description="Verify TLS certificates",
                field_type=FieldType.BOOLEAN,
                env_var="VCENTER_VERIFY_SSL",
                default=True,
            ),
            FieldMetadata(
                name="timeout_seconds",
                label="Timeout (seconds)",
                description="API request timeout",
                field_type=FieldType.FLOAT,
                env_var="VCENTER_TIMEOUT_SECONDS",
                default=15.0,
                min_value=1.0,
                max_value=60.0,
            ),
            FieldMetadata(
                name="include_tags",
                label="Include Tags",
                description="Fetch and sync vSphere tags",
                field_type=FieldType.BOOLEAN,
                env_var="VCENTER_INCLUDE_TAGS",
                default=True,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="nutanix",
        name="Nutanix Prism",
        description="Nutanix Prism discovery for VM asset enrichment",
        icon="ShareIcon",
        restart_required=True,
        has_connection_test=True,
        fields=[
            FieldMetadata(
                name="enabled",
                label="Enabled",
                description="Enable Nutanix discovery",
                field_type=FieldType.BOOLEAN,
                env_var="NUTANIX_ENABLED",
                default=False,
            ),
            FieldMetadata(
                name="api_url",
                label="API URL",
                description="Nutanix Prism Central URL",
                field_type=FieldType.STRING,
                env_var="NUTANIX_API_URL",
                default="https://nutanix.local:9440",
            ),
            FieldMetadata(
                name="username",
                label="Username",
                description="Nutanix username",
                field_type=FieldType.STRING,
                env_var="NUTANIX_USERNAME",
                required=False,
            ),
            FieldMetadata(
                name="password",
                label="Password",
                description="Nutanix password",
                field_type=FieldType.SECRET,
                env_var="NUTANIX_PASSWORD",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="verify_ssl",
                label="Verify SSL",
                description="Verify TLS certificates",
                field_type=FieldType.BOOLEAN,
                env_var="NUTANIX_VERIFY_SSL",
                default=True,
            ),
            FieldMetadata(
                name="timeout_seconds",
                label="Timeout (seconds)",
                description="API request timeout",
                field_type=FieldType.FLOAT,
                env_var="NUTANIX_TIMEOUT_SECONDS",
                default=15.0,
                min_value=1.0,
                max_value=60.0,
            ),
        ],
    ),
    SettingsSectionInfo(
        key="llm",
        name="AI/LLM Configuration",
        description="Configure AI-powered features like layout suggestions",
        icon="SparklesIcon",
        restart_required=False,
        fields=[
            FieldMetadata(
                name="provider",
                label="LLM Provider",
                description="Select the AI provider for layout suggestions",
                field_type=FieldType.SELECT,
                options=["anthropic", "openai"],
                env_var="LLM_PROVIDER",
                default="anthropic",
            ),
            FieldMetadata(
                name="api_key",
                label="API Key",
                description="Your API key for the selected provider",
                field_type=FieldType.SECRET,
                env_var="LLM_API_KEY",
                required=False,
                is_secret=True,
            ),
            FieldMetadata(
                name="model",
                label="Model (Optional)",
                description="Override the default model (leave empty to use provider default)",
                field_type=FieldType.STRING,
                env_var="LLM_MODEL",
                required=False,
            ),
        ],
    ),
]

# Discovery provider sections are hidden from System Settings
# since configuration is now managed via Discovery Providers page
HIDDEN_SECTIONS: set[str] = {"kubernetes", "vcenter", "nutanix"}


def get_section_by_key(key: str) -> SettingsSectionInfo | None:
    """Get a settings section by its key.

    Returns None for hidden sections (discovery providers).
    """
    if key in HIDDEN_SECTIONS:
        return None
    for section in SETTINGS_SECTIONS:
        if section.key == key:
            return section
    return None


def get_all_sections() -> list[SettingsSectionInfo]:
    """Get all settings sections.

    Excludes hidden discovery provider sections (kubernetes, vcenter, nutanix)
    which are now configured via the Discovery Providers page.
    """
    return [s for s in SETTINGS_SECTIONS if s.key not in HIDDEN_SECTIONS]
