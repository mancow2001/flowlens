"""Base flow record dataclass and parser interface.

Defines the normalized flow record structure that all protocol
parsers produce.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from ipaddress import IPv4Address, IPv6Address
from typing import Any


class ProtocolType(IntEnum):
    """IP protocol numbers."""

    ICMP = 1
    TCP = 6
    UDP = 17
    GRE = 47
    ESP = 50
    AH = 51
    ICMPV6 = 58
    SCTP = 132


class TCPFlags(IntEnum):
    """TCP flag bits."""

    FIN = 0x01
    SYN = 0x02
    RST = 0x04
    PSH = 0x08
    ACK = 0x10
    URG = 0x20
    ECE = 0x40
    CWR = 0x80


@dataclass(slots=True)
class FlowRecord:
    """Normalized flow record from any supported protocol.

    This is the internal representation after parsing NetFlow/sFlow/IPFIX.
    All protocol-specific details are normalized to this common structure.
    """

    # Required fields
    timestamp: datetime
    src_ip: IPv4Address | IPv6Address
    dst_ip: IPv4Address | IPv6Address
    src_port: int
    dst_port: int
    protocol: int
    bytes_count: int
    packets_count: int
    exporter_ip: IPv4Address

    # Optional flow timing
    flow_start: datetime | None = None
    flow_end: datetime | None = None
    flow_duration_ms: int | None = None

    # TCP-specific
    tcp_flags: int | None = None

    # Exporter info
    exporter_id: int | None = None
    sampling_rate: int = 1

    # Interface info
    input_interface: int | None = None
    output_interface: int | None = None

    # QoS
    tos: int | None = None

    # Source protocol
    flow_source: str = "unknown"

    # Protocol-specific extended fields
    extended_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate flow record fields."""
        if not 0 <= self.src_port <= 65535:
            raise ValueError(f"Invalid source port: {self.src_port}")
        if not 0 <= self.dst_port <= 65535:
            raise ValueError(f"Invalid destination port: {self.dst_port}")
        if not 0 <= self.protocol <= 255:
            raise ValueError(f"Invalid protocol: {self.protocol}")
        if self.bytes_count < 0:
            raise ValueError(f"Invalid bytes count: {self.bytes_count}")
        if self.packets_count < 0:
            raise ValueError(f"Invalid packets count: {self.packets_count}")

    @property
    def is_tcp(self) -> bool:
        """Check if this is a TCP flow."""
        return self.protocol == ProtocolType.TCP

    @property
    def is_udp(self) -> bool:
        """Check if this is a UDP flow."""
        return self.protocol == ProtocolType.UDP

    @property
    def is_icmp(self) -> bool:
        """Check if this is an ICMP flow."""
        return self.protocol in (ProtocolType.ICMP, ProtocolType.ICMPV6)

    @property
    def has_syn(self) -> bool:
        """Check if TCP SYN flag is set."""
        if self.tcp_flags is None:
            return False
        return bool(self.tcp_flags & TCPFlags.SYN)

    @property
    def has_fin(self) -> bool:
        """Check if TCP FIN flag is set."""
        if self.tcp_flags is None:
            return False
        return bool(self.tcp_flags & TCPFlags.FIN)

    @property
    def has_rst(self) -> bool:
        """Check if TCP RST flag is set."""
        if self.tcp_flags is None:
            return False
        return bool(self.tcp_flags & TCPFlags.RST)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "timestamp": self.timestamp,
            "src_ip": str(self.src_ip),
            "dst_ip": str(self.dst_ip),
            "src_port": self.src_port,
            "dst_port": self.dst_port,
            "protocol": self.protocol,
            "bytes_count": self.bytes_count,
            "packets_count": self.packets_count,
            "exporter_ip": str(self.exporter_ip),
            "flow_start": self.flow_start,
            "flow_end": self.flow_end,
            "flow_duration_ms": self.flow_duration_ms,
            "tcp_flags": self.tcp_flags,
            "exporter_id": self.exporter_id,
            "sampling_rate": self.sampling_rate,
            "input_interface": self.input_interface,
            "output_interface": self.output_interface,
            "tos": self.tos,
            "flow_source": self.flow_source,
            "extended_fields": self.extended_fields if self.extended_fields else None,
        }


class FlowParser(ABC):
    """Abstract base class for flow protocol parsers."""

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """Return the protocol name (e.g., 'netflow_v5')."""
        ...

    @abstractmethod
    def parse(
        self,
        data: bytes,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse raw packet data into flow records.

        Args:
            data: Raw UDP packet payload.
            exporter_ip: IP address of the exporter.

        Returns:
            List of parsed flow records.

        Raises:
            ValueError: If data is malformed.
        """
        ...

    def validate_header(self, data: bytes, min_length: int) -> None:
        """Validate packet has minimum required length.

        Args:
            data: Raw packet data.
            min_length: Minimum required bytes.

        Raises:
            ValueError: If data too short.
        """
        if len(data) < min_length:
            raise ValueError(
                f"{self.protocol_name}: packet too short "
                f"({len(data)} < {min_length} bytes)"
            )
