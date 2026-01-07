"""Async UDP server for flow ingestion.

Listens for NetFlow/sFlow/IPFIX packets and routes them to
the appropriate parser and storage backend.
"""

import asyncio
from ipaddress import IPv4Address
from typing import Any

from flowlens.common.config import IngestionSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import (
    FLOWS_PARSE_ERRORS,
    FLOWS_PARSED,
    FLOWS_RECEIVED,
)
from flowlens.ingestion.backpressure import BackpressureQueue
from flowlens.ingestion.parsers.base import FlowParser, FlowRecord
from flowlens.ingestion.parsers.ipfix import IPFIXParser
from flowlens.ingestion.parsers.netflow_v5 import NetFlowV5Parser
from flowlens.ingestion.parsers.netflow_v9 import NetFlowV9Parser
from flowlens.ingestion.parsers.sflow import SFlowParser
from flowlens.ingestion.router import FlowRouter, PostgreSQLRouter

logger = get_logger(__name__)


class FlowProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler for flow packets."""

    def __init__(
        self,
        queue: BackpressureQueue[tuple[bytes, str]],
        protocol_name: str,
    ) -> None:
        """Initialize protocol handler.

        Args:
            queue: Backpressure queue for received packets.
            protocol_name: Name of the expected protocol (for logging).
        """
        self._queue = queue
        self._protocol_name = protocol_name
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        """Called when transport is ready."""
        self._transport = transport
        logger.info(
            "UDP listener started",
            protocol=self._protocol_name,
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Called when a datagram is received.

        Args:
            data: Raw packet data.
            addr: (host, port) tuple of sender.
        """
        exporter_ip = addr[0]
        logger.debug(
            "Received packet",
            protocol=self._protocol_name,
            exporter=exporter_ip,
            size=len(data),
        )
        FLOWS_RECEIVED.labels(
            protocol=self._protocol_name,
            exporter=exporter_ip,
        ).inc()

        # Non-blocking put to queue (include protocol name for routing)
        asyncio.create_task(self._queue.put((data, exporter_ip, self._protocol_name)))

    def error_received(self, exc: Exception) -> None:
        """Called when a send/receive operation fails."""
        logger.error(
            "UDP error",
            protocol=self._protocol_name,
            error=str(exc),
        )

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when the connection is lost or closed."""
        if exc:
            logger.error(
                "UDP connection lost",
                protocol=self._protocol_name,
                error=str(exc),
            )
        else:
            logger.info(
                "UDP listener stopped",
                protocol=self._protocol_name,
            )


class FlowCollector:
    """Main flow collection service.

    Manages UDP listeners, parsers, and routing to storage.
    """

    def __init__(
        self,
        settings: IngestionSettings | None = None,
        router: FlowRouter | None = None,
    ) -> None:
        """Initialize flow collector.

        Args:
            settings: Ingestion settings.
            router: Flow router. Creates PostgreSQLRouter if not provided.
        """
        self._settings = settings or get_settings().ingestion
        self._router = router or PostgreSQLRouter(
            batch_size=self._settings.batch_size,
        )

        # Packet queue (data, exporter_ip, protocol_name)
        self._queue: BackpressureQueue[tuple[bytes, str, str]] = BackpressureQueue(
            self._settings,
        )

        # Parsers by protocol
        self._parsers: dict[str, FlowParser] = {
            "netflow_v5": NetFlowV5Parser(),
            "netflow_v9": NetFlowV9Parser(),
            "ipfix": IPFIXParser(),
            "sflow": SFlowParser(),
        }

        # Transports
        self._transports: list[asyncio.DatagramTransport] = []

        # Processing task
        self._processor_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the flow collector."""
        if self._running:
            return

        self._running = True
        logger.info("Starting flow collector")

        # Start UDP listeners
        loop = asyncio.get_event_loop()

        # NetFlow listener (handles v5, v9, IPFIX on same port)
        netflow_transport, _ = await loop.create_datagram_endpoint(
            lambda: FlowProtocol(self._queue, "netflow"),
            local_addr=(str(self._settings.bind_address), self._settings.netflow_port),
        )
        self._transports.append(netflow_transport)

        logger.info(
            "NetFlow listener started",
            bind=str(self._settings.bind_address),
            port=self._settings.netflow_port,
        )

        # sFlow listener
        sflow_transport, _ = await loop.create_datagram_endpoint(
            lambda: FlowProtocol(self._queue, "sflow"),
            local_addr=(str(self._settings.bind_address), self._settings.sflow_port),
        )
        self._transports.append(sflow_transport)

        logger.info(
            "sFlow listener started",
            bind=str(self._settings.bind_address),
            port=self._settings.sflow_port,
        )

        # Start packet processor
        self._processor_task = asyncio.create_task(self._process_packets())

        logger.info("Flow collector started")

    async def stop(self) -> None:
        """Stop the flow collector."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping flow collector")

        # Stop processor
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        # Close transports
        for transport in self._transports:
            transport.close()
        self._transports.clear()

        # Flush router
        await self._router.flush()
        await self._router.close()

        logger.info("Flow collector stopped")

    async def _process_packets(self) -> None:
        """Process packets from the queue."""
        batch_timeout = self._settings.batch_timeout_ms / 1000

        while self._running:
            try:
                # Get batch of packets
                packets = await self._queue.get_batch(
                    max_items=self._settings.batch_size,
                    timeout=batch_timeout,
                )

                if not packets:
                    continue

                # Parse all packets
                records: list[FlowRecord] = []
                for data, exporter_ip, protocol in packets:
                    try:
                        parsed = self._parse_packet(data, exporter_ip, protocol)
                        records.extend(parsed)
                    except Exception as e:
                        FLOWS_PARSE_ERRORS.labels(
                            protocol=protocol,
                            error_type=type(e).__name__,
                        ).inc()
                        logger.debug(
                            "Failed to parse packet",
                            exporter=exporter_ip,
                            protocol=protocol,
                            error=str(e),
                        )

                # Route to storage
                if records:
                    await self._router.route(records)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error processing packets",
                    error=str(e),
                )
                await asyncio.sleep(1)

    def _parse_packet(
        self,
        data: bytes,
        exporter_ip: str,
        protocol: str,
    ) -> list[FlowRecord]:
        """Parse a single packet.

        Args:
            data: Raw packet data.
            exporter_ip: IP of the exporter.
            protocol: Protocol name from listener ("netflow" or "sflow").

        Returns:
            List of parsed flow records.
        """
        if len(data) < 2:
            raise ValueError("Packet too short")

        # Route sFlow directly to sFlow parser
        if protocol == "sflow":
            parser = self._parsers.get("sflow")
            if parser:
                records = parser.parse(data, IPv4Address(exporter_ip))
                FLOWS_PARSED.labels(protocol="sflow").inc(len(records))
                return records
            raise ValueError("sFlow parser not available")

        # For NetFlow/IPFIX, detect version from first 2 bytes
        version = int.from_bytes(data[0:2], byteorder="big")

        if version == 5:
            parser = self._parsers.get("netflow_v5")
            if parser:
                records = parser.parse(data, IPv4Address(exporter_ip))
                FLOWS_PARSED.labels(protocol="netflow_v5").inc(len(records))
                return records

        if version == 9:
            parser = self._parsers.get("netflow_v9")
            if parser:
                records = parser.parse(data, IPv4Address(exporter_ip))
                FLOWS_PARSED.labels(protocol="netflow_v9").inc(len(records))
                return records

        if version == 10:
            parser = self._parsers.get("ipfix")
            if parser:
                records = parser.parse(data, IPv4Address(exporter_ip))
                FLOWS_PARSED.labels(protocol="ipfix").inc(len(records))
                return records

        raise ValueError(f"Unsupported flow version: {version}")

    @property
    def stats(self) -> dict[str, Any]:
        """Get collector statistics."""
        bp_stats = self._queue.stats
        return {
            "running": self._running,
            "queue_size": bp_stats.queue_size,
            "queue_max_size": bp_stats.queue_max_size,
            "queue_utilization": bp_stats.queue_utilization,
            "backpressure_state": bp_stats.state.value,
            "total_received": bp_stats.total_received,
            "total_sampled": bp_stats.total_sampled,
            "total_dropped": bp_stats.total_dropped,
        }
