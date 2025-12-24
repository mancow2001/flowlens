"""Flow routing to storage backends.

Supports direct PostgreSQL writes and optional Kafka routing
for high-scale deployments.
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from flowlens.common.config import get_settings
from flowlens.common.database import get_session
from flowlens.common.logging import get_logger
from flowlens.common.metrics import (
    INGESTION_BATCH_SIZE,
    INGESTION_LATENCY,
)
from flowlens.ingestion.parsers.base import FlowRecord

logger = get_logger(__name__)


class FlowRouter(ABC):
    """Abstract base class for flow routing."""

    @abstractmethod
    async def route(self, records: list[FlowRecord]) -> int:
        """Route flow records to storage.

        Args:
            records: List of flow records to store.

        Returns:
            Number of records successfully stored.
        """
        ...

    @abstractmethod
    async def flush(self) -> None:
        """Flush any buffered records."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the router and release resources."""
        ...


class PostgreSQLRouter(FlowRouter):
    """Route flows directly to PostgreSQL.

    Uses batch inserts with asyncpg COPY for optimal performance.
    Suitable for <10k flows/sec.
    """

    def __init__(self, batch_size: int = 1000) -> None:
        """Initialize PostgreSQL router.

        Args:
            batch_size: Number of records per batch insert.
        """
        self._batch_size = batch_size
        self._buffer: list[FlowRecord] = []
        self._lock = asyncio.Lock()

    async def route(self, records: list[FlowRecord]) -> int:
        """Route records to PostgreSQL.

        Args:
            records: Flow records to store.

        Returns:
            Number of records stored.
        """
        async with self._lock:
            self._buffer.extend(records)

            stored = 0
            while len(self._buffer) >= self._batch_size:
                batch = self._buffer[:self._batch_size]
                self._buffer = self._buffer[self._batch_size:]
                stored += await self._insert_batch(batch)

            return stored

    async def flush(self) -> None:
        """Flush remaining buffered records."""
        async with self._lock:
            if self._buffer:
                await self._insert_batch(self._buffer)
                self._buffer = []

    async def close(self) -> None:
        """Close router after flushing."""
        await self.flush()

    async def _insert_batch(self, records: list[FlowRecord]) -> int:
        """Insert batch of records using bulk insert.

        Args:
            records: Records to insert.

        Returns:
            Number of records inserted.
        """
        if not records:
            return 0

        import time
        start = time.perf_counter()

        try:
            async with get_session() as session:
                # Build INSERT statement with multiple value sets
                # Using raw SQL for performance
                values = []
                params: dict[str, Any] = {}

                for i, record in enumerate(records):
                    record_id = uuid.uuid4()
                    prefix = f"r{i}_"

                    values.append(f"""(
                        :{prefix}id,
                        :{prefix}timestamp,
                        :{prefix}src_ip,
                        :{prefix}src_port,
                        :{prefix}dst_ip,
                        :{prefix}dst_port,
                        :{prefix}protocol,
                        :{prefix}bytes_count,
                        :{prefix}packets_count,
                        :{prefix}tcp_flags,
                        :{prefix}flow_start,
                        :{prefix}flow_end,
                        :{prefix}flow_duration_ms,
                        :{prefix}exporter_ip,
                        :{prefix}exporter_id,
                        :{prefix}sampling_rate,
                        :{prefix}flow_source,
                        :{prefix}input_interface,
                        :{prefix}output_interface,
                        :{prefix}tos,
                        :{prefix}extended_fields
                    )""")

                    params[f"{prefix}id"] = record_id
                    params[f"{prefix}timestamp"] = record.timestamp
                    params[f"{prefix}src_ip"] = str(record.src_ip)
                    params[f"{prefix}src_port"] = record.src_port
                    params[f"{prefix}dst_ip"] = str(record.dst_ip)
                    params[f"{prefix}dst_port"] = record.dst_port
                    params[f"{prefix}protocol"] = record.protocol
                    params[f"{prefix}bytes_count"] = record.bytes_count
                    params[f"{prefix}packets_count"] = record.packets_count
                    params[f"{prefix}tcp_flags"] = record.tcp_flags
                    params[f"{prefix}flow_start"] = record.flow_start
                    params[f"{prefix}flow_end"] = record.flow_end
                    params[f"{prefix}flow_duration_ms"] = record.flow_duration_ms
                    params[f"{prefix}exporter_ip"] = str(record.exporter_ip)
                    params[f"{prefix}exporter_id"] = record.exporter_id
                    params[f"{prefix}sampling_rate"] = record.sampling_rate
                    params[f"{prefix}flow_source"] = record.flow_source
                    params[f"{prefix}input_interface"] = record.input_interface
                    params[f"{prefix}output_interface"] = record.output_interface
                    params[f"{prefix}tos"] = record.tos
                    params[f"{prefix}extended_fields"] = (
                        json.dumps(record.extended_fields) if record.extended_fields else None
                    )

                sql = f"""
                    INSERT INTO flow_records (
                        id, timestamp, src_ip, src_port, dst_ip, dst_port,
                        protocol, bytes_count, packets_count, tcp_flags,
                        flow_start, flow_end, flow_duration_ms,
                        exporter_ip, exporter_id, sampling_rate, flow_source,
                        input_interface, output_interface, tos, extended_fields
                    ) VALUES {', '.join(values)}
                """

                from sqlalchemy import text
                await session.execute(text(sql), params)

            duration = time.perf_counter() - start
            INGESTION_LATENCY.observe(duration)
            INGESTION_BATCH_SIZE.observe(len(records))

            logger.debug(
                "Inserted flow batch",
                count=len(records),
                duration_ms=round(duration * 1000, 2),
            )

            return len(records)

        except Exception as e:
            logger.error(
                "Failed to insert flow batch",
                error=str(e),
                count=len(records),
            )
            raise


class MemoryRouter(FlowRouter):
    """In-memory router for testing.

    Stores records in memory without persistence.
    """

    def __init__(self) -> None:
        self._records: list[FlowRecord] = []
        self._lock = asyncio.Lock()

    @property
    def records(self) -> list[FlowRecord]:
        """Get stored records."""
        return self._records.copy()

    async def route(self, records: list[FlowRecord]) -> int:
        """Store records in memory."""
        async with self._lock:
            self._records.extend(records)
            return len(records)

    async def flush(self) -> None:
        """No-op for memory router."""
        pass

    async def close(self) -> None:
        """Clear stored records."""
        async with self._lock:
            self._records.clear()


class AdaptiveRouter(FlowRouter):
    """Adaptive router that switches between PostgreSQL and Kafka.

    Monitors throughput and switches to Kafka when rate exceeds threshold.
    """

    def __init__(
        self,
        kafka_threshold: int = 10000,
        measurement_window: float = 10.0,
    ) -> None:
        """Initialize adaptive router.

        Args:
            kafka_threshold: Flows/sec threshold for Kafka routing.
            measurement_window: Window for throughput calculation.
        """
        self._kafka_threshold = kafka_threshold
        self._measurement_window = measurement_window

        self._postgres_router = PostgreSQLRouter()
        self._kafka_router: FlowRouter | None = None

        self._flow_count = 0
        self._window_start = datetime.utcnow()
        self._current_throughput = 0.0
        self._use_kafka = False

        self._lock = asyncio.Lock()

    @property
    def current_throughput(self) -> float:
        """Current throughput in flows/sec."""
        return self._current_throughput

    @property
    def using_kafka(self) -> bool:
        """Whether Kafka routing is active."""
        return self._use_kafka

    async def route(self, records: list[FlowRecord]) -> int:
        """Route records based on current throughput.

        Args:
            records: Flow records to route.

        Returns:
            Number of records routed.
        """
        async with self._lock:
            self._flow_count += len(records)

            # Check if measurement window elapsed
            now = datetime.utcnow()
            elapsed = (now - self._window_start).total_seconds()

            if elapsed >= self._measurement_window:
                self._current_throughput = self._flow_count / elapsed
                self._flow_count = 0
                self._window_start = now

                # Decide which router to use
                should_use_kafka = self._current_throughput >= self._kafka_threshold

                if should_use_kafka != self._use_kafka:
                    logger.info(
                        "Switching router",
                        from_router="kafka" if self._use_kafka else "postgres",
                        to_router="kafka" if should_use_kafka else "postgres",
                        throughput=round(self._current_throughput, 2),
                    )
                    self._use_kafka = should_use_kafka

        # Route to appropriate backend
        if self._use_kafka and self._kafka_router:
            return await self._kafka_router.route(records)
        else:
            return await self._postgres_router.route(records)

    async def flush(self) -> None:
        """Flush both routers."""
        await self._postgres_router.flush()
        if self._kafka_router:
            await self._kafka_router.flush()

    async def close(self) -> None:
        """Close both routers."""
        await self._postgres_router.close()
        if self._kafka_router:
            await self._kafka_router.close()
