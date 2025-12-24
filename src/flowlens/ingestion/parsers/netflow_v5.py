"""NetFlow v5 parser.

NetFlow v5 is a fixed-format protocol with a simple header and
fixed-size flow records. It's the most common NetFlow version.

Header format (24 bytes):
  - version: 2 bytes (must be 5)
  - count: 2 bytes (number of flows)
  - sys_uptime: 4 bytes (ms since boot)
  - unix_secs: 4 bytes (current time)
  - unix_nsecs: 4 bytes (residual nanoseconds)
  - flow_sequence: 4 bytes (sequence counter)
  - engine_type: 1 byte
  - engine_id: 1 byte
  - sampling_interval: 2 bytes

Flow record format (48 bytes each):
  - srcaddr: 4 bytes
  - dstaddr: 4 bytes
  - nexthop: 4 bytes
  - input: 2 bytes
  - output: 2 bytes
  - dPkts: 4 bytes
  - dOctets: 4 bytes
  - first: 4 bytes (sysuptime at start)
  - last: 4 bytes (sysuptime at end)
  - srcport: 2 bytes
  - dstport: 2 bytes
  - pad1: 1 byte
  - tcp_flags: 1 byte
  - prot: 1 byte
  - tos: 1 byte
  - src_as: 2 bytes
  - dst_as: 2 bytes
  - src_mask: 1 byte
  - dst_mask: 1 byte
  - pad2: 2 bytes
"""

import struct
from datetime import datetime, timezone
from ipaddress import IPv4Address

from flowlens.ingestion.parsers.base import FlowParser, FlowRecord

# NetFlow v5 constants
NETFLOW_V5_HEADER_SIZE = 24
NETFLOW_V5_RECORD_SIZE = 48
NETFLOW_V5_VERSION = 5


class NetFlowV5Parser(FlowParser):
    """Parser for NetFlow version 5 packets."""

    @property
    def protocol_name(self) -> str:
        return "netflow_v5"

    def parse(
        self,
        data: bytes,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse NetFlow v5 packet into flow records.

        Args:
            data: Raw UDP packet payload.
            exporter_ip: IP address of the exporter.

        Returns:
            List of parsed flow records.

        Raises:
            ValueError: If packet is malformed.
        """
        self.validate_header(data, NETFLOW_V5_HEADER_SIZE)

        # Parse header
        header = self._parse_header(data[:NETFLOW_V5_HEADER_SIZE])

        # Validate packet size
        expected_size = NETFLOW_V5_HEADER_SIZE + (header["count"] * NETFLOW_V5_RECORD_SIZE)
        if len(data) < expected_size:
            raise ValueError(
                f"netflow_v5: packet truncated "
                f"(got {len(data)}, expected {expected_size} bytes)"
            )

        # Parse flow records
        records = []
        offset = NETFLOW_V5_HEADER_SIZE

        for _ in range(header["count"]):
            record_data = data[offset:offset + NETFLOW_V5_RECORD_SIZE]
            record = self._parse_record(record_data, header, exporter_ip)
            records.append(record)
            offset += NETFLOW_V5_RECORD_SIZE

        return records

    def _parse_header(self, data: bytes) -> dict:
        """Parse NetFlow v5 header.

        Args:
            data: 24 bytes of header data.

        Returns:
            Dictionary with header fields.

        Raises:
            ValueError: If version is not 5.
        """
        (
            version,
            count,
            sys_uptime,
            unix_secs,
            unix_nsecs,
            flow_sequence,
            engine_type,
            engine_id,
            sampling_interval,
        ) = struct.unpack("!HHIIIIBBH", data)

        if version != NETFLOW_V5_VERSION:
            raise ValueError(f"netflow_v5: invalid version {version}")

        # Extract sampling mode and rate from sampling_interval
        # Upper 2 bits = mode, lower 14 bits = rate
        sampling_mode = (sampling_interval >> 14) & 0x03
        sampling_rate = sampling_interval & 0x3FFF

        # Calculate base timestamp
        base_timestamp = datetime.fromtimestamp(
            unix_secs + (unix_nsecs / 1_000_000_000),
            tz=timezone.utc,
        )

        return {
            "version": version,
            "count": count,
            "sys_uptime": sys_uptime,
            "unix_secs": unix_secs,
            "unix_nsecs": unix_nsecs,
            "flow_sequence": flow_sequence,
            "engine_type": engine_type,
            "engine_id": engine_id,
            "sampling_mode": sampling_mode,
            "sampling_rate": sampling_rate if sampling_rate > 0 else 1,
            "base_timestamp": base_timestamp,
        }

    def _parse_record(
        self,
        data: bytes,
        header: dict,
        exporter_ip: IPv4Address,
    ) -> FlowRecord:
        """Parse a single NetFlow v5 flow record.

        Args:
            data: 48 bytes of record data.
            header: Parsed header dictionary.
            exporter_ip: IP address of the exporter.

        Returns:
            Parsed FlowRecord.
        """
        (
            srcaddr,
            dstaddr,
            nexthop,
            input_if,
            output_if,
            packets,
            octets,
            first,
            last,
            srcport,
            dstport,
            pad1,
            tcp_flags,
            protocol,
            tos,
            src_as,
            dst_as,
            src_mask,
            dst_mask,
            pad2,
        ) = struct.unpack("!IIIHHIIIIHHBBBBHHBBH", data)

        # Convert IP addresses
        src_ip = IPv4Address(srcaddr)
        dst_ip = IPv4Address(dstaddr)
        next_hop = IPv4Address(nexthop)

        # Calculate flow timestamps based on sysuptime offsets
        sys_uptime = header["sys_uptime"]
        base_ts = header["base_timestamp"]

        # Flow start and end are relative to sys_uptime
        # first/last are in milliseconds since boot
        if first <= sys_uptime:
            start_offset_ms = sys_uptime - first
            flow_start = datetime.fromtimestamp(
                base_ts.timestamp() - (start_offset_ms / 1000),
                tz=timezone.utc,
            )
        else:
            flow_start = base_ts

        if last <= sys_uptime:
            end_offset_ms = sys_uptime - last
            flow_end = datetime.fromtimestamp(
                base_ts.timestamp() - (end_offset_ms / 1000),
                tz=timezone.utc,
            )
        else:
            flow_end = base_ts

        # Calculate duration
        flow_duration_ms = max(0, last - first) if last >= first else 0

        return FlowRecord(
            timestamp=flow_end,  # Use flow end as the primary timestamp
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=srcport,
            dst_port=dstport,
            protocol=protocol,
            bytes_count=octets,
            packets_count=packets,
            exporter_ip=exporter_ip,
            flow_start=flow_start,
            flow_end=flow_end,
            flow_duration_ms=flow_duration_ms,
            tcp_flags=tcp_flags if protocol == 6 else None,
            exporter_id=header["engine_id"],
            sampling_rate=header["sampling_rate"],
            input_interface=input_if,
            output_interface=output_if,
            tos=tos,
            flow_source="netflow_v5",
            extended_fields={
                "next_hop": str(next_hop),
                "src_as": src_as,
                "dst_as": dst_as,
                "src_mask": src_mask,
                "dst_mask": dst_mask,
                "flow_sequence": header["flow_sequence"],
            },
        )
