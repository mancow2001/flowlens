"""sFlow parser.

sFlow is a statistical sampling technology that provides
continuous monitoring of network traffic. Unlike NetFlow,
it samples packets directly rather than tracking flows.

sFlow v5 datagram format:
  - version: 4 bytes (must be 5)
  - agent_address_type: 4 bytes (1=IPv4, 2=IPv6)
  - agent_address: 4 or 16 bytes
  - sub_agent_id: 4 bytes
  - sequence_number: 4 bytes
  - uptime: 4 bytes (ms since boot)
  - num_samples: 4 bytes
  - samples: variable

Sample types:
  - Flow sample (enterprise=0, format=1)
  - Counter sample (enterprise=0, format=2)
  - Expanded flow sample (enterprise=0, format=3)
  - Expanded counter sample (enterprise=0, format=4)

Flow sample contains sampled packet data which can be
decoded for layer 3/4 information.
"""

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from flowlens.common.logging import get_logger
from flowlens.ingestion.parsers.base import FlowParser, FlowRecord, ProtocolType

logger = get_logger(__name__)

# sFlow constants
SFLOW_VERSION = 5
SFLOW_HEADER_MIN_SIZE = 28  # Without agent address

# Address types
ADDRESS_TYPE_IPV4 = 1
ADDRESS_TYPE_IPV6 = 2

# Sample formats
SAMPLE_FORMAT_FLOW = 1
SAMPLE_FORMAT_COUNTER = 2
SAMPLE_FORMAT_EXPANDED_FLOW = 3
SAMPLE_FORMAT_EXPANDED_COUNTER = 4

# Flow record formats
FLOW_RECORD_RAW_PACKET = 1
FLOW_RECORD_ETHERNET_FRAME = 2
FLOW_RECORD_IPV4 = 3
FLOW_RECORD_IPV6 = 4
FLOW_RECORD_EXTENDED_SWITCH = 1001
FLOW_RECORD_EXTENDED_ROUTER = 1002
FLOW_RECORD_EXTENDED_GATEWAY = 1003

# Ethernet header size
ETHERNET_HEADER_SIZE = 14


@dataclass
class SFlowHeader:
    """sFlow datagram header."""

    version: int
    agent_address: IPv4Address | IPv6Address
    sub_agent_id: int
    sequence_number: int
    uptime_ms: int
    num_samples: int


@dataclass
class FlowSample:
    """sFlow flow sample."""

    sequence_number: int
    source_id: int
    sampling_rate: int
    sample_pool: int
    drops: int
    input_interface: int
    output_interface: int
    num_records: int


class SFlowParser(FlowParser):
    """Parser for sFlow version 5 datagrams."""

    @property
    def protocol_name(self) -> str:
        return "sflow"

    def parse(
        self,
        data: bytes,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse sFlow datagram into flow records.

        Args:
            data: Raw UDP packet payload.
            exporter_ip: IP address of the exporter.

        Returns:
            List of parsed flow records.

        Raises:
            ValueError: If packet is malformed.
        """
        self.validate_header(data, SFLOW_HEADER_MIN_SIZE)

        # Parse header
        header, offset = self._parse_header(data)

        # Parse samples
        records: list[FlowRecord] = []

        for _ in range(header.num_samples):
            if offset + 8 > len(data):
                break

            # Sample header
            sample_format, sample_length = struct.unpack(
                "!II", data[offset:offset + 8]
            )

            # Extract enterprise and format
            enterprise = (sample_format >> 12) & 0xFFFFF
            fmt = sample_format & 0xFFF

            sample_data = data[offset + 8:offset + 8 + sample_length]

            if enterprise == 0:
                if fmt == SAMPLE_FORMAT_FLOW:
                    new_records = self._parse_flow_sample(
                        sample_data,
                        header,
                        exporter_ip,
                    )
                    records.extend(new_records)
                elif fmt == SAMPLE_FORMAT_EXPANDED_FLOW:
                    new_records = self._parse_expanded_flow_sample(
                        sample_data,
                        header,
                        exporter_ip,
                    )
                    records.extend(new_records)
                # Counter samples are ignored for flow analysis

            offset += 8 + sample_length

        return records

    def _parse_header(self, data: bytes) -> tuple[SFlowHeader, int]:
        """Parse sFlow datagram header.

        Args:
            data: Raw datagram data.

        Returns:
            Tuple of (SFlowHeader, offset after header).

        Raises:
            ValueError: If version is not 5.
        """
        version, agent_type = struct.unpack("!II", data[:8])

        if version != SFLOW_VERSION:
            raise ValueError(f"sflow: invalid version {version}")

        offset = 8

        # Parse agent address
        if agent_type == ADDRESS_TYPE_IPV4:
            agent_address = IPv4Address(data[offset:offset + 4])
            offset += 4
        elif agent_type == ADDRESS_TYPE_IPV6:
            agent_address = IPv6Address(data[offset:offset + 16])
            offset += 16
        else:
            raise ValueError(f"sflow: invalid agent address type {agent_type}")

        # Parse rest of header
        (
            sub_agent_id,
            sequence_number,
            uptime_ms,
            num_samples,
        ) = struct.unpack("!IIII", data[offset:offset + 16])
        offset += 16

        header = SFlowHeader(
            version=version,
            agent_address=agent_address,
            sub_agent_id=sub_agent_id,
            sequence_number=sequence_number,
            uptime_ms=uptime_ms,
            num_samples=num_samples,
        )

        return header, offset

    def _parse_flow_sample(
        self,
        data: bytes,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse a flow sample.

        Args:
            data: Sample data (without header).
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            List of flow records.
        """
        if len(data) < 32:
            return []

        (
            sequence_number,
            source_id,
            sampling_rate,
            sample_pool,
            drops,
            input_if,
            output_if,
            num_records,
        ) = struct.unpack("!IIIIIIII", data[:32])

        sample = FlowSample(
            sequence_number=sequence_number,
            source_id=source_id,
            sampling_rate=sampling_rate,
            sample_pool=sample_pool,
            drops=drops,
            input_interface=input_if,
            output_interface=output_if,
            num_records=num_records,
        )

        return self._parse_flow_records(data[32:], sample, header, exporter_ip)

    def _parse_expanded_flow_sample(
        self,
        data: bytes,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse an expanded flow sample.

        Expanded samples use 32-bit interface IDs.

        Args:
            data: Sample data (without header).
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            List of flow records.
        """
        if len(data) < 44:
            return []

        (
            sequence_number,
            source_id_type,
            source_id_index,
            sampling_rate,
            sample_pool,
            drops,
            input_if_format,
            input_if_value,
            output_if_format,
            output_if_value,
            num_records,
        ) = struct.unpack("!IIIIIIIIIII", data[:44])

        sample = FlowSample(
            sequence_number=sequence_number,
            source_id=(source_id_type << 24) | source_id_index,
            sampling_rate=sampling_rate,
            sample_pool=sample_pool,
            drops=drops,
            input_interface=input_if_value,
            output_interface=output_if_value,
            num_records=num_records,
        )

        return self._parse_flow_records(data[44:], sample, header, exporter_ip)

    def _parse_flow_records(
        self,
        data: bytes,
        sample: FlowSample,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse flow records from a sample.

        Args:
            data: Flow records data.
            sample: Parent flow sample.
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            List of flow records.
        """
        records: list[FlowRecord] = []
        offset = 0

        for _ in range(sample.num_records):
            if offset + 8 > len(data):
                break

            record_format, record_length = struct.unpack(
                "!II", data[offset:offset + 8]
            )

            enterprise = (record_format >> 12) & 0xFFFFF
            fmt = record_format & 0xFFF

            record_data = data[offset + 8:offset + 8 + record_length]

            if enterprise == 0:
                if fmt == FLOW_RECORD_RAW_PACKET:
                    record = self._parse_raw_packet_record(
                        record_data,
                        sample,
                        header,
                        exporter_ip,
                    )
                    if record:
                        records.append(record)
                elif fmt == FLOW_RECORD_IPV4:
                    record = self._parse_ipv4_record(
                        record_data,
                        sample,
                        header,
                        exporter_ip,
                    )
                    if record:
                        records.append(record)
                elif fmt == FLOW_RECORD_IPV6:
                    record = self._parse_ipv6_record(
                        record_data,
                        sample,
                        header,
                        exporter_ip,
                    )
                    if record:
                        records.append(record)

            offset += 8 + record_length
            # Align to 4-byte boundary
            if record_length % 4:
                offset += 4 - (record_length % 4)

        return records

    def _parse_raw_packet_record(
        self,
        data: bytes,
        sample: FlowSample,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse a raw packet header record.

        Args:
            data: Record data.
            sample: Parent flow sample.
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            FlowRecord or None.
        """
        if len(data) < 16:
            return None

        (
            protocol,
            frame_length,
            stripped,
            header_length,
        ) = struct.unpack("!IIII", data[:16])

        packet_data = data[16:16 + header_length]

        # Skip to IP header (assume Ethernet)
        if protocol == 1 and len(packet_data) > ETHERNET_HEADER_SIZE:
            # Check EtherType
            ether_type = struct.unpack("!H", packet_data[12:14])[0]

            ip_offset = ETHERNET_HEADER_SIZE

            # Handle VLAN tags
            if ether_type == 0x8100:  # 802.1Q
                if len(packet_data) > ip_offset + 4:
                    ether_type = struct.unpack("!H", packet_data[ip_offset + 2:ip_offset + 4])[0]
                    ip_offset += 4

            if ether_type == 0x0800:  # IPv4
                return self._parse_ipv4_header(
                    packet_data[ip_offset:],
                    frame_length,
                    sample,
                    header,
                    exporter_ip,
                )
            elif ether_type == 0x86DD:  # IPv6
                return self._parse_ipv6_header(
                    packet_data[ip_offset:],
                    frame_length,
                    sample,
                    header,
                    exporter_ip,
                )

        return None

    def _parse_ipv4_header(
        self,
        data: bytes,
        frame_length: int,
        sample: FlowSample,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse IPv4 header from packet data.

        Args:
            data: IP header data.
            frame_length: Original frame length.
            sample: Parent flow sample.
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            FlowRecord or None.
        """
        if len(data) < 20:
            return None

        version_ihl = data[0]
        ihl = (version_ihl & 0x0F) * 4
        tos = data[1]
        total_length = struct.unpack("!H", data[2:4])[0]
        protocol = data[9]
        src_ip = IPv4Address(data[12:16])
        dst_ip = IPv4Address(data[16:20])

        src_port = 0
        dst_port = 0
        tcp_flags = None

        # Parse transport layer
        if len(data) >= ihl + 4:
            transport_data = data[ihl:]

            if protocol == ProtocolType.TCP and len(transport_data) >= 14:
                src_port, dst_port = struct.unpack("!HH", transport_data[:4])
                tcp_flags = transport_data[13]
            elif protocol == ProtocolType.UDP and len(transport_data) >= 8:
                src_port, dst_port = struct.unpack("!HH", transport_data[:4])

        # Estimate bytes from sampling
        estimated_bytes = frame_length * sample.sampling_rate

        return FlowRecord(
            timestamp=datetime.now(timezone.utc),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            protocol=protocol,
            bytes_count=estimated_bytes,
            packets_count=sample.sampling_rate,  # Each sample represents N packets
            exporter_ip=exporter_ip,
            tcp_flags=tcp_flags if protocol == ProtocolType.TCP else None,
            exporter_id=sample.source_id,
            sampling_rate=sample.sampling_rate,
            input_interface=sample.input_interface,
            output_interface=sample.output_interface,
            tos=tos,
            flow_source="sflow",
            extended_fields={
                "agent": str(header.agent_address),
                "sequence_number": header.sequence_number,
                "sample_pool": sample.sample_pool,
                "drops": sample.drops,
            },
        )

    def _parse_ipv6_header(
        self,
        data: bytes,
        frame_length: int,
        sample: FlowSample,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse IPv6 header from packet data.

        Args:
            data: IP header data.
            frame_length: Original frame length.
            sample: Parent flow sample.
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            FlowRecord or None.
        """
        if len(data) < 40:
            return None

        # IPv6 header is 40 bytes
        version_tc_fl = struct.unpack("!I", data[:4])[0]
        traffic_class = (version_tc_fl >> 20) & 0xFF
        next_header = data[6]
        src_ip = IPv6Address(data[8:24])
        dst_ip = IPv6Address(data[24:40])

        protocol = next_header
        src_port = 0
        dst_port = 0
        tcp_flags = None

        # Parse transport layer (simplified - ignores extension headers)
        if len(data) >= 44:
            transport_data = data[40:]

            if protocol == ProtocolType.TCP and len(transport_data) >= 14:
                src_port, dst_port = struct.unpack("!HH", transport_data[:4])
                tcp_flags = transport_data[13]
            elif protocol == ProtocolType.UDP and len(transport_data) >= 8:
                src_port, dst_port = struct.unpack("!HH", transport_data[:4])

        estimated_bytes = frame_length * sample.sampling_rate

        return FlowRecord(
            timestamp=datetime.now(timezone.utc),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            protocol=protocol,
            bytes_count=estimated_bytes,
            packets_count=sample.sampling_rate,
            exporter_ip=exporter_ip,
            tcp_flags=tcp_flags if protocol == ProtocolType.TCP else None,
            exporter_id=sample.source_id,
            sampling_rate=sample.sampling_rate,
            input_interface=sample.input_interface,
            output_interface=sample.output_interface,
            tos=traffic_class,
            flow_source="sflow",
            extended_fields={
                "agent": str(header.agent_address),
                "sequence_number": header.sequence_number,
                "sample_pool": sample.sample_pool,
                "drops": sample.drops,
            },
        )

    def _parse_ipv4_record(
        self,
        data: bytes,
        sample: FlowSample,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse a sampled IPv4 record.

        This is a decoded IPv4 header from sFlow.

        Args:
            data: Record data.
            sample: Parent flow sample.
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            FlowRecord or None.
        """
        if len(data) < 32:
            return None

        (
            length,
            protocol,
            src_ip_raw,
            dst_ip_raw,
            src_port,
            dst_port,
            tcp_flags,
            tos,
        ) = struct.unpack("!IIIIIIII", data[:32])

        src_ip = IPv4Address(src_ip_raw)
        dst_ip = IPv4Address(dst_ip_raw)

        estimated_bytes = length * sample.sampling_rate

        return FlowRecord(
            timestamp=datetime.now(timezone.utc),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            protocol=protocol,
            bytes_count=estimated_bytes,
            packets_count=sample.sampling_rate,
            exporter_ip=exporter_ip,
            tcp_flags=tcp_flags if protocol == ProtocolType.TCP else None,
            exporter_id=sample.source_id,
            sampling_rate=sample.sampling_rate,
            input_interface=sample.input_interface,
            output_interface=sample.output_interface,
            tos=tos,
            flow_source="sflow",
            extended_fields={
                "agent": str(header.agent_address),
                "sequence_number": header.sequence_number,
            },
        )

    def _parse_ipv6_record(
        self,
        data: bytes,
        sample: FlowSample,
        header: SFlowHeader,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse a sampled IPv6 record.

        Args:
            data: Record data.
            sample: Parent flow sample.
            header: Datagram header.
            exporter_ip: Exporter IP address.

        Returns:
            FlowRecord or None.
        """
        if len(data) < 64:
            return None

        length = struct.unpack("!I", data[:4])[0]
        protocol = struct.unpack("!I", data[4:8])[0]
        src_ip = IPv6Address(data[8:24])
        dst_ip = IPv6Address(data[24:40])
        src_port = struct.unpack("!I", data[40:44])[0]
        dst_port = struct.unpack("!I", data[44:48])[0]
        tcp_flags = struct.unpack("!I", data[48:52])[0]
        priority = struct.unpack("!I", data[52:56])[0]

        estimated_bytes = length * sample.sampling_rate

        return FlowRecord(
            timestamp=datetime.now(timezone.utc),
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=src_port,
            dst_port=dst_port,
            protocol=protocol,
            bytes_count=estimated_bytes,
            packets_count=sample.sampling_rate,
            exporter_ip=exporter_ip,
            tcp_flags=tcp_flags if protocol == ProtocolType.TCP else None,
            exporter_id=sample.source_id,
            sampling_rate=sample.sampling_rate,
            input_interface=sample.input_interface,
            output_interface=sample.output_interface,
            tos=priority,
            flow_source="sflow",
            extended_fields={
                "agent": str(header.agent_address),
                "sequence_number": header.sequence_number,
            },
        )
