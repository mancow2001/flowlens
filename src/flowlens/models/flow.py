"""Flow record and aggregate models.

FlowRecord stores individual flow records with partitioning.
FlowAggregate stores pre-aggregated flow statistics.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import Base


class FlowRecord(Base):
    """Individual flow record from NetFlow/sFlow/IPFIX.

    Partitioned by timestamp for efficient time-range queries
    and automatic data retention.

    Retention: 7 days (configurable via partition management)
    """

    __tablename__ = "flow_records"

    # Primary key (composite with timestamp for partitioning)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Timestamp (part of primary key for partitioning)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        index=True,
    )

    # Source endpoint
    src_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    src_port: Mapped[int] = mapped_column(
        nullable=False,
    )

    # Destination endpoint
    dst_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    dst_port: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )

    # Protocol
    protocol: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        index=True,
    )

    # Traffic metrics
    bytes_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    packets_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # TCP flags (if TCP)
    tcp_flags: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    # Flow timing
    flow_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    flow_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    flow_duration_ms: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # Exporter info
    exporter_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    exporter_id: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # Sampling info
    sampling_rate: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
    )

    # Protocol-specific source info
    flow_source: Mapped[str] = mapped_column(
        String(20),  # netflow_v5, netflow_v9, ipfix, sflow
        nullable=False,
    )

    # Interface info
    input_interface: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    output_interface: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # TOS/DSCP
    tos: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    # Extended fields for protocol-specific data
    extended_fields: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Processing status
    is_enriched: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    is_processed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    # Ingestion timestamp
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_flows_src_dst_time", "src_ip", "dst_ip", "timestamp"),
        Index("ix_flows_dst_port_time", "dst_ip", "dst_port", "timestamp"),
        # For unprocessed flow queries
        Index(
            "ix_flows_unenriched",
            "timestamp",
            postgresql_where="is_enriched = false",
        ),
        Index(
            "ix_flows_unprocessed",
            "timestamp",
            postgresql_where="is_processed = false",
        ),
        # Port constraints
        CheckConstraint("src_port >= 0 AND src_port <= 65535"),
        CheckConstraint("dst_port >= 0 AND dst_port <= 65535"),
        CheckConstraint("protocol >= 0 AND protocol <= 255"),
        # Note: Partitioning is configured via migration
        # PARTITION BY RANGE (timestamp)
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    def __repr__(self) -> str:
        return f"<FlowRecord {self.src_ip}:{self.src_port} -> {self.dst_ip}:{self.dst_port}>"


class FlowAggregate(Base):
    """Pre-aggregated flow statistics.

    Aggregates flows into time windows (5-minute, hourly, daily)
    for efficient querying and long-term storage.

    Retention: 90 days for 5-minute, 2 years for hourly/daily
    """

    __tablename__ = "flow_aggregates"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Time window
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    window_size: Mapped[str] = mapped_column(
        String(20),  # 5min, 1hour, 1day
        nullable=False,
        index=True,
    )

    # Aggregation key
    src_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    dst_ip: Mapped[str] = mapped_column(
        INET,
        nullable=False,
        index=True,
    )

    dst_port: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )

    protocol: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    # Aggregated metrics
    bytes_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    packets_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    flows_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Statistical metrics
    bytes_min: Mapped[int] = mapped_column(
        BigInteger,
        nullable=True,
    )

    bytes_max: Mapped[int] = mapped_column(
        BigInteger,
        nullable=True,
    )

    bytes_avg: Mapped[float] = mapped_column(
        nullable=True,
    )

    # Unique sources/destinations in window
    unique_sources: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    unique_destinations: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Linked asset IDs (populated during resolution)
    src_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    dst_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Gateway information (populated during aggregation)
    primary_gateway_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
        index=True,
    )

    exporter_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )

    # Processing status
    is_processed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    # Processing metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Composite unique constraint
        Index(
            "ix_agg_key_window",
            "src_ip", "dst_ip", "dst_port", "protocol", "window_start", "window_size",
            unique=True,
        ),
        # For dependency resolution
        Index("ix_agg_assets_window", "src_asset_id", "dst_asset_id", "window_start"),
        # For unprocessed aggregate queries
        Index(
            "ix_agg_unprocessed",
            "window_start",
            postgresql_where="is_processed = false",
        ),
        # Port constraint
        CheckConstraint("dst_port >= 0 AND dst_port <= 65535"),
        CheckConstraint("protocol >= 0 AND protocol <= 255"),
    )

    def __repr__(self) -> str:
        return f"<FlowAggregate {self.src_ip} -> {self.dst_ip}:{self.dst_port} [{self.window_start}]>"


class DependencyStats(Base):
    """Long-term dependency statistics.

    Daily rollups of dependency traffic for trend analysis
    and capacity planning.

    Retention: 2 years
    """

    __tablename__ = "dependency_stats"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Date dimension
    stat_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Dependency reference
    dependency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Asset references (denormalized for query efficiency)
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    target_port: Mapped[int] = mapped_column(
        nullable=False,
    )

    protocol: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    # Daily aggregates
    bytes_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    packets_total: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    flows_total: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Hourly breakdown for pattern analysis
    bytes_by_hour: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Statistical metrics
    peak_bytes_per_sec: Mapped[int] = mapped_column(
        BigInteger,
        nullable=True,
    )

    avg_bytes_per_sec: Mapped[float] = mapped_column(
        nullable=True,
    )

    # Connection patterns
    active_hours: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Created timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Unique per dependency per day
        Index(
            "ix_stats_dep_date",
            "dependency_id", "stat_date",
            unique=True,
        ),
        # For time-range queries
        Index("ix_stats_date_source", "stat_date", "source_asset_id"),
        Index("ix_stats_date_target", "stat_date", "target_asset_id"),
    )

    def __repr__(self) -> str:
        return f"<DependencyStats {self.dependency_id} [{self.stat_date}]>"
