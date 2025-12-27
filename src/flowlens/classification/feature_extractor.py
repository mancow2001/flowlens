"""Feature extraction for asset classification.

Computes behavioral features from flow_aggregates data for classification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.classification.constants import (
    BUSINESS_HOURS_END,
    BUSINESS_HOURS_START,
    DATABASE_PORTS,
    EPHEMERAL_PORT_MIN,
    SSH_PORTS,
    STORAGE_PORTS,
    WEB_PORTS,
    WELL_KNOWN_PORT_MAX,
)
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.models.flow import FlowAggregate

logger = get_logger(__name__)


@dataclass
class BehavioralFeatures:
    """Computed behavioral features for an IP address.

    These features are extracted from flow aggregate data and used
    by the scoring engine to classify asset types.
    """

    ip_address: str
    window_size: str
    computed_at: datetime

    # Traffic directionality
    inbound_flows: int = 0
    outbound_flows: int = 0
    inbound_bytes: int = 0
    outbound_bytes: int = 0
    fan_in_count: int = 0  # Unique sources connecting to this IP
    fan_out_count: int = 0  # Unique destinations this IP connects to
    fan_in_ratio: float | None = None

    # Port & protocol behavior
    unique_dst_ports: int = 0  # Ports this IP connects to
    unique_src_ports: int = 0  # Ports others connect to on this IP (listening)
    well_known_port_ratio: float | None = None
    ephemeral_port_ratio: float | None = None
    persistent_listener_ports: list[int] = field(default_factory=list)
    protocol_distribution: dict[int, int] = field(default_factory=dict)

    # Flow characteristics
    avg_flow_duration_ms: float | None = None
    avg_packets_per_flow: float | None = None
    avg_bytes_per_packet: float | None = None
    connection_churn_rate: float | None = None
    total_flows: int = 0

    # Temporal patterns
    active_hours_count: int | None = None
    business_hours_ratio: float | None = None
    traffic_variance: float | None = None

    # Port-specific flags
    has_db_ports: bool = False
    has_storage_ports: bool = False
    has_web_ports: bool = False
    has_ssh_ports: bool = False

    def to_dict(self) -> dict:
        """Convert features to dictionary for storage."""
        return {
            "ip_address": self.ip_address,
            "window_size": self.window_size,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "inbound_flows": self.inbound_flows,
            "outbound_flows": self.outbound_flows,
            "inbound_bytes": self.inbound_bytes,
            "outbound_bytes": self.outbound_bytes,
            "fan_in_count": self.fan_in_count,
            "fan_out_count": self.fan_out_count,
            "fan_in_ratio": self.fan_in_ratio,
            "unique_dst_ports": self.unique_dst_ports,
            "unique_src_ports": self.unique_src_ports,
            "well_known_port_ratio": self.well_known_port_ratio,
            "ephemeral_port_ratio": self.ephemeral_port_ratio,
            "persistent_listener_ports": self.persistent_listener_ports,
            "protocol_distribution": self.protocol_distribution,
            "avg_flow_duration_ms": self.avg_flow_duration_ms,
            "avg_packets_per_flow": self.avg_packets_per_flow,
            "avg_bytes_per_packet": self.avg_bytes_per_packet,
            "connection_churn_rate": self.connection_churn_rate,
            "total_flows": self.total_flows,
            "active_hours_count": self.active_hours_count,
            "business_hours_ratio": self.business_hours_ratio,
            "traffic_variance": self.traffic_variance,
            "has_db_ports": self.has_db_ports,
            "has_storage_ports": self.has_storage_ports,
            "has_web_ports": self.has_web_ports,
            "has_ssh_ports": self.has_ssh_ports,
        }


class FeatureExtractor:
    """Extracts behavioral features from flow data for classification."""

    def __init__(self, session: AsyncSession):
        """Initialize the feature extractor.

        Args:
            session: Async database session.
        """
        self.session = session
        self.settings = get_settings().classification

    async def extract_features(
        self,
        ip_address: str,
        window_size: str = "5min",
        lookback_hours: int | None = None,
    ) -> BehavioralFeatures:
        """Extract behavioral features for an IP address.

        Args:
            ip_address: IP address to analyze.
            window_size: Aggregation window size to query ('5min', '1hour', '24hour').
            lookback_hours: How far back to look. Defaults to config value.

        Returns:
            BehavioralFeatures containing computed metrics.
        """
        if lookback_hours is None:
            lookback_hours = self.settings.min_observation_hours

        now = datetime.utcnow()
        cutoff = now - timedelta(hours=lookback_hours)

        # Ensure ip_address is a string for database queries
        # (may come in as IPv4Address/IPv4Network from SQLAlchemy INET type)
        ip_str = str(ip_address)

        features = BehavioralFeatures(
            ip_address=ip_str,
            window_size=window_size,
            computed_at=now,
        )

        # Run queries in parallel for efficiency
        await self._extract_inbound_metrics(features, ip_str, window_size, cutoff)
        await self._extract_outbound_metrics(features, ip_str, window_size, cutoff)
        await self._extract_port_behavior(features, ip_str, window_size, cutoff)
        await self._extract_temporal_patterns(features, ip_str, window_size, cutoff)
        await self._extract_protocol_distribution(features, ip_str, window_size, cutoff)

        # Compute derived metrics
        self._compute_derived_metrics(features)

        return features

    async def _extract_inbound_metrics(
        self,
        features: BehavioralFeatures,
        ip_address: str,
        window_size: str,
        cutoff: datetime,
    ) -> None:
        """Extract metrics for traffic where this IP is the destination."""
        # Count flows, bytes, and unique sources (fan-in)
        query = select(
            func.sum(FlowAggregate.flows_count).label("flows"),
            func.sum(FlowAggregate.bytes_total).label("bytes"),
            func.count(func.distinct(FlowAggregate.src_ip)).label("fan_in"),
        ).where(
            FlowAggregate.dst_ip == ip_address,
            FlowAggregate.window_start >= cutoff,
            FlowAggregate.window_size == window_size,
        )

        result = await self.session.execute(query)
        row = result.one_or_none()

        if row and row.flows:
            features.inbound_flows = int(row.flows or 0)
            features.inbound_bytes = int(row.bytes or 0)
            features.fan_in_count = int(row.fan_in or 0)

    async def _extract_outbound_metrics(
        self,
        features: BehavioralFeatures,
        ip_address: str,
        window_size: str,
        cutoff: datetime,
    ) -> None:
        """Extract metrics for traffic where this IP is the source."""
        # Count flows, bytes, and unique destinations (fan-out)
        query = select(
            func.sum(FlowAggregate.flows_count).label("flows"),
            func.sum(FlowAggregate.bytes_total).label("bytes"),
            func.count(func.distinct(FlowAggregate.dst_ip)).label("fan_out"),
        ).where(
            FlowAggregate.src_ip == ip_address,
            FlowAggregate.window_start >= cutoff,
            FlowAggregate.window_size == window_size,
        )

        result = await self.session.execute(query)
        row = result.one_or_none()

        if row and row.flows:
            features.outbound_flows = int(row.flows or 0)
            features.outbound_bytes = int(row.bytes or 0)
            features.fan_out_count = int(row.fan_out or 0)

    async def _extract_port_behavior(
        self,
        features: BehavioralFeatures,
        ip_address: str,
        window_size: str,
        cutoff: datetime,
    ) -> None:
        """Extract port usage patterns."""
        # Ports this IP listens on (dst_port when dst_ip = our IP)
        listener_query = select(
            FlowAggregate.dst_port,
            func.sum(FlowAggregate.flows_count).label("flow_count"),
        ).where(
            FlowAggregate.dst_ip == ip_address,
            FlowAggregate.window_start >= cutoff,
            FlowAggregate.window_size == window_size,
        ).group_by(
            FlowAggregate.dst_port
        ).order_by(
            func.sum(FlowAggregate.flows_count).desc()
        )

        result = await self.session.execute(listener_query)
        listener_ports = result.fetchall()

        if listener_ports:
            features.unique_src_ports = len(listener_ports)

            # Top 10 most active listening ports
            features.persistent_listener_ports = [
                int(row.dst_port) for row in listener_ports[:10]
            ]

            # Check for special port categories
            all_ports = {int(row.dst_port) for row in listener_ports}
            features.has_db_ports = bool(all_ports & DATABASE_PORTS)
            features.has_storage_ports = bool(all_ports & STORAGE_PORTS)
            features.has_web_ports = bool(all_ports & WEB_PORTS)
            features.has_ssh_ports = bool(all_ports & SSH_PORTS)

            # Calculate well-known and ephemeral port ratios
            well_known_count = sum(
                1 for row in listener_ports if row.dst_port <= WELL_KNOWN_PORT_MAX
            )
            ephemeral_count = sum(
                1 for row in listener_ports if row.dst_port >= EPHEMERAL_PORT_MIN
            )
            total_ports = len(listener_ports)

            features.well_known_port_ratio = well_known_count / total_ports if total_ports > 0 else None
            features.ephemeral_port_ratio = ephemeral_count / total_ports if total_ports > 0 else None

        # Ports this IP connects to (dst_port when src_ip = our IP)
        client_query = select(
            func.count(func.distinct(FlowAggregate.dst_port)).label("port_count"),
        ).where(
            FlowAggregate.src_ip == ip_address,
            FlowAggregate.window_start >= cutoff,
            FlowAggregate.window_size == window_size,
        )

        result = await self.session.execute(client_query)
        row = result.one_or_none()

        if row:
            features.unique_dst_ports = int(row.port_count or 0)

    async def _extract_temporal_patterns(
        self,
        features: BehavioralFeatures,
        ip_address: str,
        window_size: str,
        cutoff: datetime,
    ) -> None:
        """Extract temporal patterns (active hours, business hours ratio)."""
        # Extract hour of day from window_start for activity analysis
        # This uses PostgreSQL's EXTRACT function
        query = text("""
            SELECT
                EXTRACT(HOUR FROM window_start) as hour,
                SUM(flows_count) as flow_count
            FROM flow_aggregates
            WHERE (src_ip = :ip OR dst_ip = :ip)
              AND window_start >= :cutoff
              AND window_size = :window_size
            GROUP BY EXTRACT(HOUR FROM window_start)
            ORDER BY hour
        """)

        result = await self.session.execute(
            query,
            {"ip": ip_address, "cutoff": cutoff, "window_size": window_size}
        )
        hourly_data = result.fetchall()

        if hourly_data:
            # Count active hours
            features.active_hours_count = len(hourly_data)

            # Calculate business hours ratio
            total_flows = sum(int(row.flow_count) for row in hourly_data)
            business_flows = sum(
                int(row.flow_count)
                for row in hourly_data
                if BUSINESS_HOURS_START <= int(row.hour) < BUSINESS_HOURS_END
            )

            if total_flows > 0:
                features.business_hours_ratio = business_flows / total_flows

            # Calculate traffic variance (normalized standard deviation)
            if len(hourly_data) > 1:
                flow_counts = [int(row.flow_count) for row in hourly_data]
                mean = sum(flow_counts) / len(flow_counts)
                if mean > 0:
                    variance = sum((x - mean) ** 2 for x in flow_counts) / len(flow_counts)
                    std_dev = variance ** 0.5
                    features.traffic_variance = std_dev / mean  # Coefficient of variation

    async def _extract_protocol_distribution(
        self,
        features: BehavioralFeatures,
        ip_address: str,
        window_size: str,
        cutoff: datetime,
    ) -> None:
        """Extract protocol distribution (TCP/UDP/etc.)."""
        query = select(
            FlowAggregate.protocol,
            func.sum(FlowAggregate.flows_count).label("flow_count"),
        ).where(
            ((FlowAggregate.src_ip == ip_address) | (FlowAggregate.dst_ip == ip_address)),
            FlowAggregate.window_start >= cutoff,
            FlowAggregate.window_size == window_size,
        ).group_by(
            FlowAggregate.protocol
        )

        result = await self.session.execute(query)
        protocol_data = result.fetchall()

        features.protocol_distribution = {
            int(row.protocol): int(row.flow_count)
            for row in protocol_data
        }

    def _compute_derived_metrics(self, features: BehavioralFeatures) -> None:
        """Compute metrics derived from raw counts."""
        # Fan-in ratio
        total_connections = features.fan_in_count + features.fan_out_count
        if total_connections > 0:
            features.fan_in_ratio = features.fan_in_count / total_connections

        # Total flows
        features.total_flows = features.inbound_flows + features.outbound_flows

        # Average bytes per packet (if we have packet data)
        total_bytes = features.inbound_bytes + features.outbound_bytes
        if features.total_flows > 0:
            features.avg_bytes_per_packet = total_bytes / features.total_flows

        # Log feature extraction
        logger.debug(
            "Extracted features",
            ip=features.ip_address,
            total_flows=features.total_flows,
            fan_in=features.fan_in_count,
            fan_out=features.fan_out_count,
        )


async def extract_features_for_asset(
    session: AsyncSession,
    ip_address: str,
    window_size: str = "5min",
    lookback_hours: int | None = None,
) -> BehavioralFeatures:
    """Convenience function to extract features for an asset.

    Args:
        session: Database session.
        ip_address: IP address to analyze.
        window_size: Aggregation window size.
        lookback_hours: Optional lookback period.

    Returns:
        Extracted behavioral features.
    """
    extractor = FeatureExtractor(session)
    return await extractor.extract_features(ip_address, window_size, lookback_hours)
