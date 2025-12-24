"""NetFlow v9 parser with template cache.

NetFlow v9 is a template-based protocol where field definitions
are sent separately from data records. This requires maintaining
a template cache to decode data records.

Header format (20 bytes):
  - version: 2 bytes (must be 9)
  - count: 2 bytes (number of FlowSets)
  - sys_uptime: 4 bytes (ms since boot)
  - unix_secs: 4 bytes (current time)
  - sequence_number: 4 bytes
  - source_id: 4 bytes

FlowSet format:
  - flowset_id: 2 bytes (0=template, 1=options, >255=data)
  - length: 2 bytes (total length including header)
  - data: variable

Template FlowSet (flowset_id=0):
  - template_id: 2 bytes
  - field_count: 2 bytes
  - fields: field_count * (type: 2 bytes, length: 2 bytes)

Data FlowSet (flowset_id >= 256):
  - Records using template_id = flowset_id
"""

import struct
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from flowlens.common.logging import get_logger
from flowlens.ingestion.parsers.base import FlowParser, FlowRecord

logger = get_logger(__name__)

# NetFlow v9 constants
NETFLOW_V9_HEADER_SIZE = 20
NETFLOW_V9_VERSION = 9

# FlowSet IDs
FLOWSET_TEMPLATE = 0
FLOWSET_OPTIONS_TEMPLATE = 1
FLOWSET_DATA_MIN = 256

# Field type constants (RFC 3954)
NF9_FIELD_IN_BYTES = 1
NF9_FIELD_IN_PKTS = 2
NF9_FIELD_FLOWS = 3
NF9_FIELD_PROTOCOL = 4
NF9_FIELD_SRC_TOS = 5
NF9_FIELD_TCP_FLAGS = 6
NF9_FIELD_L4_SRC_PORT = 7
NF9_FIELD_IPV4_SRC_ADDR = 8
NF9_FIELD_SRC_MASK = 9
NF9_FIELD_INPUT_SNMP = 10
NF9_FIELD_L4_DST_PORT = 11
NF9_FIELD_IPV4_DST_ADDR = 12
NF9_FIELD_DST_MASK = 13
NF9_FIELD_OUTPUT_SNMP = 14
NF9_FIELD_IPV4_NEXT_HOP = 15
NF9_FIELD_SRC_AS = 16
NF9_FIELD_DST_AS = 17
NF9_FIELD_LAST_SWITCHED = 21
NF9_FIELD_FIRST_SWITCHED = 22
NF9_FIELD_OUT_BYTES = 23
NF9_FIELD_OUT_PKTS = 24
NF9_FIELD_IPV6_SRC_ADDR = 27
NF9_FIELD_IPV6_DST_ADDR = 28
NF9_FIELD_IPV6_FLOW_LABEL = 31
NF9_FIELD_ICMP_TYPE = 32
NF9_FIELD_SAMPLING_INTERVAL = 34
NF9_FIELD_SAMPLING_ALGORITHM = 35
NF9_FIELD_ENGINE_TYPE = 38
NF9_FIELD_ENGINE_ID = 39
NF9_FIELD_FLOW_SAMPLER_ID = 48
NF9_FIELD_FLOW_SAMPLER_MODE = 49
NF9_FIELD_FLOW_SAMPLER_RANDOM_INTERVAL = 50
NF9_FIELD_DIRECTION = 61
NF9_FIELD_IPV6_NEXT_HOP = 62


@dataclass
class TemplateField:
    """A single field in a NetFlow v9 template."""

    field_type: int
    field_length: int


@dataclass
class Template:
    """NetFlow v9 template definition."""

    template_id: int
    source_id: int
    fields: list[TemplateField] = dataclass_field(default_factory=list)
    record_length: int = 0
    received_at: datetime = dataclass_field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Calculate record length from fields."""
        self.record_length = sum(f.field_length for f in self.fields)


class TemplateCache:
    """Cache for NetFlow v9 templates.

    Templates are keyed by (exporter_ip, source_id, template_id).
    Templates expire after a configurable TTL.
    """

    def __init__(self, ttl_seconds: int = 3600, max_templates: int = 10000) -> None:
        """Initialize template cache.

        Args:
            ttl_seconds: Template expiration time in seconds.
            max_templates: Maximum number of templates to cache.
        """
        self._ttl_seconds = ttl_seconds
        self._max_templates = max_templates
        self._templates: dict[tuple[str, int, int], Template] = {}

    def get(
        self,
        exporter_ip: str,
        source_id: int,
        template_id: int,
    ) -> Template | None:
        """Get a template from cache.

        Args:
            exporter_ip: Exporter IP address.
            source_id: Source ID from header.
            template_id: Template ID.

        Returns:
            Template if found and not expired, None otherwise.
        """
        key = (exporter_ip, source_id, template_id)
        template = self._templates.get(key)

        if template is None:
            return None

        # Check expiration
        age = (datetime.utcnow() - template.received_at).total_seconds()
        if age > self._ttl_seconds:
            del self._templates[key]
            return None

        return template

    def set(
        self,
        exporter_ip: str,
        source_id: int,
        template: Template,
    ) -> None:
        """Store a template in cache.

        Args:
            exporter_ip: Exporter IP address.
            source_id: Source ID from header.
            template: Template to store.
        """
        # Evict oldest if at capacity
        if len(self._templates) >= self._max_templates:
            oldest_key = min(
                self._templates.keys(),
                key=lambda k: self._templates[k].received_at,
            )
            del self._templates[oldest_key]

        key = (exporter_ip, source_id, template.template_id)
        self._templates[key] = template

        logger.debug(
            "Cached template",
            exporter=exporter_ip,
            source_id=source_id,
            template_id=template.template_id,
            fields=len(template.fields),
            record_length=template.record_length,
        )

    def clear(self) -> None:
        """Clear all templates."""
        self._templates.clear()

    @property
    def size(self) -> int:
        """Get number of cached templates."""
        return len(self._templates)


class NetFlowV9Parser(FlowParser):
    """Parser for NetFlow version 9 packets."""

    def __init__(self, template_cache: TemplateCache | None = None) -> None:
        """Initialize parser.

        Args:
            template_cache: Shared template cache instance.
        """
        self._template_cache = template_cache or TemplateCache()

    @property
    def protocol_name(self) -> str:
        return "netflow_v9"

    @property
    def template_cache(self) -> TemplateCache:
        """Get the template cache."""
        return self._template_cache

    def parse(
        self,
        data: bytes,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse NetFlow v9 packet into flow records.

        Args:
            data: Raw UDP packet payload.
            exporter_ip: IP address of the exporter.

        Returns:
            List of parsed flow records.

        Raises:
            ValueError: If packet is malformed.
        """
        self.validate_header(data, NETFLOW_V9_HEADER_SIZE)

        # Parse header
        header = self._parse_header(data[:NETFLOW_V9_HEADER_SIZE])

        # Parse FlowSets
        records: list[FlowRecord] = []
        offset = NETFLOW_V9_HEADER_SIZE

        while offset + 4 <= len(data):
            flowset_id, flowset_length = struct.unpack(
                "!HH", data[offset:offset + 4]
            )

            if flowset_length < 4:
                logger.warning(
                    "Invalid flowset length",
                    flowset_id=flowset_id,
                    length=flowset_length,
                )
                break

            flowset_data = data[offset:offset + flowset_length]

            if flowset_id == FLOWSET_TEMPLATE:
                self._parse_template_flowset(
                    flowset_data,
                    header["source_id"],
                    str(exporter_ip),
                )
            elif flowset_id == FLOWSET_OPTIONS_TEMPLATE:
                # Options templates not implemented yet
                pass
            elif flowset_id >= FLOWSET_DATA_MIN:
                new_records = self._parse_data_flowset(
                    flowset_data,
                    flowset_id,
                    header,
                    exporter_ip,
                )
                records.extend(new_records)

            offset += flowset_length

        return records

    def _parse_header(self, data: bytes) -> dict:
        """Parse NetFlow v9 header.

        Args:
            data: 20 bytes of header data.

        Returns:
            Dictionary with header fields.

        Raises:
            ValueError: If version is not 9.
        """
        (
            version,
            count,
            sys_uptime,
            unix_secs,
            sequence_number,
            source_id,
        ) = struct.unpack("!HHIIII", data)

        if version != NETFLOW_V9_VERSION:
            raise ValueError(f"netflow_v9: invalid version {version}")

        base_timestamp = datetime.fromtimestamp(unix_secs, tz=timezone.utc)

        return {
            "version": version,
            "count": count,
            "sys_uptime": sys_uptime,
            "unix_secs": unix_secs,
            "sequence_number": sequence_number,
            "source_id": source_id,
            "base_timestamp": base_timestamp,
        }

    def _parse_template_flowset(
        self,
        data: bytes,
        source_id: int,
        exporter_ip: str,
    ) -> None:
        """Parse a template FlowSet.

        Args:
            data: FlowSet data including header.
            source_id: Source ID from packet header.
            exporter_ip: Exporter IP address string.
        """
        offset = 4  # Skip flowset header

        while offset + 4 <= len(data):
            template_id, field_count = struct.unpack(
                "!HH", data[offset:offset + 4]
            )
            offset += 4

            # Need 4 bytes per field
            if offset + (field_count * 4) > len(data):
                logger.warning(
                    "Truncated template",
                    template_id=template_id,
                    field_count=field_count,
                )
                break

            fields: list[TemplateField] = []
            for _ in range(field_count):
                field_type, field_length = struct.unpack(
                    "!HH", data[offset:offset + 4]
                )
                fields.append(TemplateField(field_type, field_length))
                offset += 4

            template = Template(
                template_id=template_id,
                source_id=source_id,
                fields=fields,
            )

            self._template_cache.set(exporter_ip, source_id, template)

    def _parse_data_flowset(
        self,
        data: bytes,
        template_id: int,
        header: dict,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse a data FlowSet.

        Args:
            data: FlowSet data including header.
            template_id: Template ID (same as flowset_id).
            header: Parsed packet header.
            exporter_ip: Exporter IP address.

        Returns:
            List of parsed flow records.
        """
        template = self._template_cache.get(
            str(exporter_ip),
            header["source_id"],
            template_id,
        )

        if template is None:
            logger.debug(
                "No template for data flowset",
                exporter=str(exporter_ip),
                source_id=header["source_id"],
                template_id=template_id,
            )
            return []

        records: list[FlowRecord] = []
        offset = 4  # Skip flowset header
        flowset_length = struct.unpack("!H", data[2:4])[0]

        while offset + template.record_length <= flowset_length:
            record_data = data[offset:offset + template.record_length]
            record = self._parse_record(record_data, template, header, exporter_ip)
            if record:
                records.append(record)
            offset += template.record_length

        return records

    def _parse_record(
        self,
        data: bytes,
        template: Template,
        header: dict,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse a single data record using template.

        Args:
            data: Record data.
            template: Template for decoding.
            header: Packet header.
            exporter_ip: Exporter IP address.

        Returns:
            Parsed FlowRecord or None if required fields missing.
        """
        # Extract fields from record
        fields: dict[int, Any] = {}
        offset = 0

        for field in template.fields:
            field_data = data[offset:offset + field.field_length]
            fields[field.field_type] = self._decode_field(
                field.field_type,
                field.field_length,
                field_data,
            )
            offset += field.field_length

        # Build FlowRecord from fields
        try:
            src_ip = fields.get(NF9_FIELD_IPV4_SRC_ADDR) or fields.get(NF9_FIELD_IPV6_SRC_ADDR)
            dst_ip = fields.get(NF9_FIELD_IPV4_DST_ADDR) or fields.get(NF9_FIELD_IPV6_DST_ADDR)

            if src_ip is None or dst_ip is None:
                return None

            src_port = fields.get(NF9_FIELD_L4_SRC_PORT, 0)
            dst_port = fields.get(NF9_FIELD_L4_DST_PORT, 0)
            protocol = fields.get(NF9_FIELD_PROTOCOL, 0)

            bytes_count = fields.get(NF9_FIELD_IN_BYTES, 0) + fields.get(NF9_FIELD_OUT_BYTES, 0)
            packets_count = fields.get(NF9_FIELD_IN_PKTS, 0) + fields.get(NF9_FIELD_OUT_PKTS, 0)

            # Calculate timestamps
            base_ts = header["base_timestamp"]
            sys_uptime = header["sys_uptime"]

            first_switched = fields.get(NF9_FIELD_FIRST_SWITCHED, sys_uptime)
            last_switched = fields.get(NF9_FIELD_LAST_SWITCHED, sys_uptime)

            flow_start = datetime.fromtimestamp(
                base_ts.timestamp() - (sys_uptime - first_switched) / 1000,
                tz=timezone.utc,
            )
            flow_end = datetime.fromtimestamp(
                base_ts.timestamp() - (sys_uptime - last_switched) / 1000,
                tz=timezone.utc,
            )

            return FlowRecord(
                timestamp=flow_end,
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=src_port,
                dst_port=dst_port,
                protocol=protocol,
                bytes_count=bytes_count,
                packets_count=packets_count,
                exporter_ip=exporter_ip,
                flow_start=flow_start,
                flow_end=flow_end,
                flow_duration_ms=max(0, last_switched - first_switched),
                tcp_flags=fields.get(NF9_FIELD_TCP_FLAGS) if protocol == 6 else None,
                exporter_id=header["source_id"],
                sampling_rate=fields.get(NF9_FIELD_SAMPLING_INTERVAL, 1),
                input_interface=fields.get(NF9_FIELD_INPUT_SNMP),
                output_interface=fields.get(NF9_FIELD_OUTPUT_SNMP),
                tos=fields.get(NF9_FIELD_SRC_TOS),
                flow_source="netflow_v9",
                extended_fields={
                    "src_as": fields.get(NF9_FIELD_SRC_AS),
                    "dst_as": fields.get(NF9_FIELD_DST_AS),
                    "src_mask": fields.get(NF9_FIELD_SRC_MASK),
                    "dst_mask": fields.get(NF9_FIELD_DST_MASK),
                    "next_hop": str(fields.get(NF9_FIELD_IPV4_NEXT_HOP) or fields.get(NF9_FIELD_IPV6_NEXT_HOP) or ""),
                    "direction": fields.get(NF9_FIELD_DIRECTION),
                    "sequence_number": header["sequence_number"],
                },
            )

        except Exception as e:
            logger.warning(
                "Failed to parse NetFlow v9 record",
                error=str(e),
            )
            return None

    def _decode_field(
        self,
        field_type: int,
        field_length: int,
        data: bytes,
    ) -> Any:
        """Decode a field value based on type and length.

        Args:
            field_type: NetFlow v9 field type.
            field_length: Field length in bytes.
            data: Raw field data.

        Returns:
            Decoded value.
        """
        # IPv4 addresses
        if field_type in (NF9_FIELD_IPV4_SRC_ADDR, NF9_FIELD_IPV4_DST_ADDR, NF9_FIELD_IPV4_NEXT_HOP):
            if field_length == 4:
                return IPv4Address(data)
            return None

        # IPv6 addresses
        if field_type in (NF9_FIELD_IPV6_SRC_ADDR, NF9_FIELD_IPV6_DST_ADDR, NF9_FIELD_IPV6_NEXT_HOP):
            if field_length == 16:
                return IPv6Address(data)
            return None

        # Numeric fields
        if field_length == 1:
            return data[0]
        elif field_length == 2:
            return struct.unpack("!H", data)[0]
        elif field_length == 4:
            return struct.unpack("!I", data)[0]
        elif field_length == 8:
            return struct.unpack("!Q", data)[0]

        # Variable length - return as bytes
        return data
