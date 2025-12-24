"""Flow aggregation for dependency resolution.

Aggregates flow records into time windows for efficient
dependency analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import ResolutionSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import AGGREGATION_WINDOW_DURATION
from flowlens.models.flow import FlowAggregate, FlowRecord

logger = get_logger(__name__)


@dataclass
class AggregationKey:
    """Key for aggregating flows."""

    src_ip: str
    dst_ip: str
    dst_port: int
    protocol: int

    def __hash__(self) -> int:
        return hash((self.src_ip, self.dst_ip, self.dst_port, self.protocol))


@dataclass
class AggregationBucket:
    """Bucket for accumulating flow statistics."""

    bytes_total: int = 0
    packets_total: int = 0
    flows_count: int = 0
    bytes_min: int = field(default_factory=lambda: float("inf"))
    bytes_max: int = 0
    unique_sources: set = field(default_factory=set)
    unique_destinations: set = field(default_factory=set)
    src_asset_id: UUID | None = None
    dst_asset_id: UUID | None = None

    def add(
        self,
        bytes_count: int,
        packets_count: int,
        src_ip: str,
        dst_ip: str,
        src_asset_id: UUID | None = None,
        dst_asset_id: UUID | None = None,
    ) -> None:
        """Add flow to bucket."""
        self.bytes_total += bytes_count
        self.packets_total += packets_count
        self.flows_count += 1
        self.bytes_min = min(self.bytes_min, bytes_count)
        self.bytes_max = max(self.bytes_max, bytes_count)
        self.unique_sources.add(src_ip)
        self.unique_destinations.add(dst_ip)

        if src_asset_id:
            self.src_asset_id = src_asset_id
        if dst_asset_id:
            self.dst_asset_id = dst_asset_id

    @property
    def bytes_avg(self) -> float:
        """Average bytes per flow."""
        if self.flows_count == 0:
            return 0.0
        return self.bytes_total / self.flows_count


class FlowAggregator:
    """Aggregates flows into time windows.

    Creates FlowAggregate records from raw FlowRecords,
    grouping by source IP, destination IP, destination port,
    and protocol within configurable time windows.
    """

    def __init__(self, settings: ResolutionSettings | None = None) -> None:
        """Initialize aggregator.

        Args:
            settings: Resolution settings.
        """
        if settings is None:
            settings = get_settings().resolution

        self._window_size_minutes = settings.window_size_minutes
        self._batch_size = settings.batch_size

    def get_window_bounds(
        self,
        timestamp: datetime,
    ) -> tuple[datetime, datetime]:
        """Get window start and end for a timestamp.

        Args:
            timestamp: Timestamp to get window for.

        Returns:
            Tuple of (window_start, window_end).
        """
        # Truncate to window boundary
        minutes = timestamp.minute - (timestamp.minute % self._window_size_minutes)
        window_start = timestamp.replace(
            minute=minutes,
            second=0,
            microsecond=0,
        )
        window_end = window_start + timedelta(minutes=self._window_size_minutes)
        return window_start, window_end

    async def aggregate_window(
        self,
        db: AsyncSession,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        """Aggregate flows within a time window.

        Args:
            db: Database session.
            window_start: Window start time.
            window_end: Window end time.

        Returns:
            Number of aggregates created/updated.
        """
        import time
        start_time = time.perf_counter()

        logger.debug(
            "Aggregating window",
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
        )

        # Fetch processed but unaggregated flows in the window
        result = await db.execute(
            select(FlowRecord)
            .where(
                FlowRecord.timestamp >= window_start,
                FlowRecord.timestamp < window_end,
                FlowRecord.is_enriched == True,
                FlowRecord.is_processed == False,
            )
            .limit(self._batch_size)
        )
        flows = result.scalars().all()

        if not flows:
            return 0

        # Build aggregation buckets
        buckets: dict[AggregationKey, AggregationBucket] = {}

        for flow in flows:
            key = AggregationKey(
                src_ip=str(flow.src_ip),
                dst_ip=str(flow.dst_ip),
                dst_port=flow.dst_port,
                protocol=flow.protocol,
            )

            if key not in buckets:
                buckets[key] = AggregationBucket()

            # Extract asset IDs from enrichment data
            src_asset_id = None
            dst_asset_id = None
            if flow.extended_fields and "enrichment" in flow.extended_fields:
                enrichment = flow.extended_fields["enrichment"]
                if enrichment.get("src_asset_id"):
                    src_asset_id = UUID(enrichment["src_asset_id"])
                if enrichment.get("dst_asset_id"):
                    dst_asset_id = UUID(enrichment["dst_asset_id"])

            buckets[key].add(
                bytes_count=flow.bytes_count,
                packets_count=flow.packets_count,
                src_ip=str(flow.src_ip),
                dst_ip=str(flow.dst_ip),
                src_asset_id=src_asset_id,
                dst_asset_id=dst_asset_id,
            )

        # Upsert aggregates
        window_size = f"{self._window_size_minutes}min"

        for key, bucket in buckets.items():
            await self._upsert_aggregate(
                db,
                window_start=window_start,
                window_end=window_end,
                window_size=window_size,
                key=key,
                bucket=bucket,
            )

        # Mark flows as processed
        flow_ids = [(f.id, f.timestamp) for f in flows]
        for flow_id, flow_ts in flow_ids:
            await db.execute(
                update(FlowRecord)
                .where(
                    FlowRecord.id == flow_id,
                    FlowRecord.timestamp == flow_ts,
                )
                .values(is_processed=True)
            )

        duration = time.perf_counter() - start_time
        AGGREGATION_WINDOW_DURATION.observe(duration)

        logger.debug(
            "Window aggregation complete",
            flows_processed=len(flows),
            aggregates_created=len(buckets),
            duration_ms=round(duration * 1000, 2),
        )

        return len(buckets)

    async def _upsert_aggregate(
        self,
        db: AsyncSession,
        window_start: datetime,
        window_end: datetime,
        window_size: str,
        key: AggregationKey,
        bucket: AggregationBucket,
    ) -> None:
        """Upsert a flow aggregate.

        Args:
            db: Database session.
            window_start: Window start time.
            window_end: Window end time.
            window_size: Window size string.
            key: Aggregation key.
            bucket: Aggregated data.
        """
        # Build insert statement with ON CONFLICT UPDATE
        stmt = insert(FlowAggregate).values(
            id=uuid4(),
            window_start=window_start,
            window_end=window_end,
            window_size=window_size,
            src_ip=key.src_ip,
            dst_ip=key.dst_ip,
            dst_port=key.dst_port,
            protocol=key.protocol,
            bytes_total=bucket.bytes_total,
            packets_total=bucket.packets_total,
            flows_count=bucket.flows_count,
            bytes_min=bucket.bytes_min if bucket.bytes_min != float("inf") else 0,
            bytes_max=bucket.bytes_max,
            bytes_avg=bucket.bytes_avg,
            unique_sources=len(bucket.unique_sources),
            unique_destinations=len(bucket.unique_destinations),
            src_asset_id=bucket.src_asset_id,
            dst_asset_id=bucket.dst_asset_id,
        )

        # On conflict, update counters
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "src_ip", "dst_ip", "dst_port", "protocol",
                "window_start", "window_size",
            ],
            set_={
                "bytes_total": FlowAggregate.bytes_total + bucket.bytes_total,
                "packets_total": FlowAggregate.packets_total + bucket.packets_total,
                "flows_count": FlowAggregate.flows_count + bucket.flows_count,
                "bytes_max": func.greatest(FlowAggregate.bytes_max, bucket.bytes_max),
                "bytes_min": func.least(FlowAggregate.bytes_min, bucket.bytes_min),
                "src_asset_id": bucket.src_asset_id,
                "dst_asset_id": bucket.dst_asset_id,
            },
        )

        await db.execute(stmt)

    async def get_pending_windows(
        self,
        db: AsyncSession,
        lookback_hours: int = 1,
    ) -> list[tuple[datetime, datetime]]:
        """Get windows that have unprocessed flows.

        Args:
            db: Database session.
            lookback_hours: How far back to look.

        Returns:
            List of (window_start, window_end) tuples.
        """
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)

        # Find distinct windows with unprocessed flows
        result = await db.execute(
            select(
                func.date_trunc("minute", FlowRecord.timestamp)
            )
            .where(
                FlowRecord.timestamp >= cutoff,
                FlowRecord.is_enriched == True,
                FlowRecord.is_processed == False,
            )
            .distinct()
            .order_by(func.date_trunc("minute", FlowRecord.timestamp))
            .limit(100)
        )

        windows = []
        seen_windows = set()

        for (ts,) in result.fetchall():
            window_start, window_end = self.get_window_bounds(ts)
            window_key = window_start

            if window_key not in seen_windows:
                seen_windows.add(window_key)
                windows.append((window_start, window_end))

        return windows
