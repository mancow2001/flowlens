"""Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env files.
Supports service-specific settings with shared base configuration.
"""

from functools import lru_cache
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str = "localhost"
    port: int = 5432
    user: str = "flowlens"
    password: SecretStr = SecretStr("flowlens")
    database: str = "flowlens"

    # Connection pool settings
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    pool_timeout: int = Field(default=30, ge=1)
    pool_recycle: int = Field(default=1800, ge=60)

    # Performance tuning
    echo: bool = False
    echo_pool: bool = False

    @property
    def async_url(self) -> str:
        """Construct async PostgreSQL connection URL."""
        password = self.password.get_secret_value()
        return f"postgresql+asyncpg://{self.user}:{password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        """Construct sync PostgreSQL connection URL (for Alembic)."""
        password = self.password.get_secret_value()
        return f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.database}"


class RedisSettings(BaseSettings):
    """Redis configuration (optional, for scaling)."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    enabled: bool = False
    host: str = "localhost"
    port: int = 6379
    password: SecretStr | None = None
    database: int = 0
    ssl: bool = False

    # Connection pool
    pool_size: int = Field(default=10, ge=1, le=100)
    socket_timeout: float = Field(default=5.0, ge=0.1)

    @property
    def url(self) -> str:
        """Construct Redis connection URL."""
        auth = ""
        if self.password:
            auth = f":{self.password.get_secret_value()}@"
        scheme = "rediss" if self.ssl else "redis"
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.database}"


class KafkaSettings(BaseSettings):
    """Kafka configuration (optional, for high-scale ingestion)."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_")

    enabled: bool = False
    bootstrap_servers: str = "localhost:9092"
    topic_flows: str = "flowlens.flows.raw"
    topic_enriched: str = "flowlens.flows.enriched"
    consumer_group: str = "flowlens"

    # Producer settings
    batch_size: int = Field(default=16384, ge=1024)
    linger_ms: int = Field(default=10, ge=0)
    compression: Literal["none", "gzip", "snappy", "lz4", "zstd"] = "lz4"

    # Consumer settings
    auto_offset_reset: Literal["earliest", "latest"] = "latest"
    max_poll_records: int = Field(default=500, ge=1)


class IngestionSettings(BaseSettings):
    """Flow Ingestion Service configuration."""

    model_config = SettingsConfigDict(env_prefix="INGESTION_")

    # UDP listener
    bind_address: IPv4Address = IPv4Address("0.0.0.0")
    netflow_port: int = Field(default=2055, ge=1, le=65535)
    sflow_port: int = Field(default=6343, ge=1, le=65535)

    # Batching
    batch_size: int = Field(default=1000, ge=100, le=10000)
    batch_timeout_ms: int = Field(default=1000, ge=100)

    # Backpressure
    queue_max_size: int = Field(default=100000, ge=1000)
    sample_threshold: int = Field(default=50000, ge=1000)
    drop_threshold: int = Field(default=80000, ge=1000)
    sample_rate: int = Field(default=10, ge=2)

    @field_validator("drop_threshold")
    @classmethod
    def validate_thresholds(cls, v: int, info) -> int:
        """Ensure drop threshold is higher than sample threshold."""
        sample = info.data.get("sample_threshold", 50000)
        if v <= sample:
            raise ValueError("drop_threshold must be greater than sample_threshold")
        return v


class EnrichmentSettings(BaseSettings):
    """Enrichment Service configuration."""

    model_config = SettingsConfigDict(env_prefix="ENRICHMENT_")

    # Worker settings
    batch_size: int = Field(default=500, ge=50, le=5000)
    poll_interval_ms: int = Field(default=100, ge=10)
    worker_count: int = Field(default=4, ge=1, le=32)

    # DNS resolver
    dns_timeout: float = Field(default=2.0, ge=0.1)
    dns_cache_ttl: int = Field(default=3600, ge=60)
    dns_cache_size: int = Field(default=10000, ge=100)
    dns_servers: list[str] = Field(default_factory=list)

    # GeoIP
    geoip_database_path: Path | None = None


class ResolutionSettings(BaseSettings):
    """Dependency Resolution Service configuration."""

    model_config = SettingsConfigDict(env_prefix="RESOLUTION_")

    # Aggregation windows
    window_size_minutes: int = Field(default=5, ge=1, le=60)

    # Worker settings
    worker_count: int = Field(default=1, ge=1, le=16)
    batch_size: int = Field(default=1000, ge=100)
    poll_interval_ms: int = Field(default=500, ge=100)

    # Dependency detection
    detection_interval_minutes: int = Field(default=5, ge=1, le=60)
    stale_threshold_hours: int = Field(default=24, ge=1)
    new_dependency_lookback_minutes: int = Field(default=30, ge=5)


class APISettings(BaseSettings):
    """Query/API Service configuration."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = Field(default=4, ge=1, le=32)
    reload: bool = False

    # Security
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    rate_limit_requests: int = Field(default=100, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # Pagination
    default_page_size: int = Field(default=50, ge=1, le=1000)
    max_page_size: int = Field(default=1000, ge=1, le=10000)


class AuthSettings(BaseSettings):
    """Authentication configuration."""

    model_config = SettingsConfigDict(env_prefix="AUTH_")

    enabled: bool = True
    secret_key: SecretStr = SecretStr("change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "json"
    include_timestamp: bool = True
    include_caller: bool = True


class EmailSettings(BaseSettings):
    """Email notification configuration."""

    model_config = SettingsConfigDict(env_prefix="EMAIL_")

    enabled: bool = False
    host: str = "localhost"
    port: int = 587
    username: str | None = None
    password: SecretStr | None = None
    use_tls: bool = True
    start_tls: bool = True
    from_address: str = "flowlens@localhost"
    from_name: str = "FlowLens"
    timeout: int = 30
    validate_certs: bool = True

    # Default recipients for alerts
    alert_recipients: list[str] = Field(default_factory=list)


class NotificationSettings(BaseSettings):
    """Notification system configuration."""

    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_")

    # Global enable/disable
    enabled: bool = True

    # Channel-specific settings
    email: EmailSettings = Field(default_factory=EmailSettings)

    # Alert routing rules (severity -> channels)
    critical_channels: list[str] = Field(default_factory=lambda: ["email"])
    high_channels: list[str] = Field(default_factory=lambda: ["email"])
    warning_channels: list[str] = Field(default_factory=list)
    info_channels: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    """Main application settings aggregating all configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Application info
    app_name: str = "FlowLens"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    enrichment: EnrichmentSettings = Field(default_factory=EnrichmentSettings)
    resolution: ResolutionSettings = Field(default_factory=ResolutionSettings)
    api: APISettings = Field(default_factory=APISettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
