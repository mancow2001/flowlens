"""IPFIX (IP Flow Information Export) parser.

IPFIX is the standardized version of NetFlow v9 (RFC 7011).
It uses a similar template-based approach with some differences:
- Version number is 10
- Message header includes length and observation domain ID
- Field types can be vendor-specific (enterprise numbers)
- Variable-length fields are supported

Message Header (16 bytes):
  - version: 2 bytes (must be 10)
  - length: 2 bytes (total message length)
  - export_time: 4 bytes (seconds since epoch)
  - sequence_number: 4 bytes
  - observation_domain_id: 4 bytes

Set Header (4 bytes):
  - set_id: 2 bytes (2=template, 3=options template, >255=data)
  - length: 2 bytes
"""

import struct
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from flowlens.common.logging import get_logger
from flowlens.ingestion.parsers.base import FlowParser, FlowRecord

logger = get_logger(__name__)

# IPFIX constants
IPFIX_HEADER_SIZE = 16
IPFIX_VERSION = 10

# Set IDs
SET_TEMPLATE = 2
SET_OPTIONS_TEMPLATE = 3
SET_DATA_MIN = 256

# IPFIX Information Element IDs (IANA registry)
IE_OCTET_DELTA_COUNT = 1
IE_PACKET_DELTA_COUNT = 2
IE_DELTA_FLOW_COUNT = 3
IE_PROTOCOL_IDENTIFIER = 4
IE_IP_CLASS_OF_SERVICE = 5
IE_TCP_CONTROL_BITS = 6
IE_SOURCE_TRANSPORT_PORT = 7
IE_SOURCE_IPV4_ADDRESS = 8
IE_SOURCE_IPV4_PREFIX_LENGTH = 9
IE_INGRESS_INTERFACE = 10
IE_DESTINATION_TRANSPORT_PORT = 11
IE_DESTINATION_IPV4_ADDRESS = 12
IE_DESTINATION_IPV4_PREFIX_LENGTH = 13
IE_EGRESS_INTERFACE = 14
IE_IP_NEXT_HOP_IPV4_ADDRESS = 15
IE_BGP_SOURCE_AS_NUMBER = 16
IE_BGP_DESTINATION_AS_NUMBER = 17
IE_FLOW_START_SYS_UP_TIME = 22
IE_FLOW_END_SYS_UP_TIME = 21
IE_FLOW_START_SECONDS = 150
IE_FLOW_END_SECONDS = 151
IE_FLOW_START_MILLISECONDS = 152
IE_FLOW_END_MILLISECONDS = 153
IE_FLOW_START_MICROSECONDS = 154
IE_FLOW_END_MICROSECONDS = 155
IE_FLOW_DURATION_MILLISECONDS = 161
IE_SOURCE_IPV6_ADDRESS = 27
IE_DESTINATION_IPV6_ADDRESS = 28
IE_SOURCE_IPV6_PREFIX_LENGTH = 29
IE_DESTINATION_IPV6_PREFIX_LENGTH = 30
IE_FLOW_LABEL_IPV6 = 31
IE_ICMP_TYPE_CODE_IPV4 = 32
IE_SAMPLING_INTERVAL = 34
IE_SAMPLING_ALGORITHM = 35
IE_FLOW_ACTIVE_TIMEOUT = 36
IE_FLOW_IDLE_TIMEOUT = 37
IE_FLOW_DIRECTION = 61
IE_IP_NEXT_HOP_IPV6_ADDRESS = 62
IE_OCTET_TOTAL_COUNT = 85
IE_PACKET_TOTAL_COUNT = 86
IE_FLOW_ID = 148


@dataclass
class IPFIXField:
    """A single field in an IPFIX template."""

    element_id: int
    field_length: int
    enterprise_number: int | None = None  # For vendor-specific fields


@dataclass
class IPFIXTemplate:
    """IPFIX template definition."""

    template_id: int
    observation_domain_id: int
    fields: list[IPFIXField] = dataclass_field(default_factory=list)
    record_length: int = 0
    received_at: datetime = dataclass_field(default_factory=datetime.utcnow)
    has_variable_length: bool = False

    def __post_init__(self) -> None:
        """Calculate record length from fields."""
        self.record_length = 0
        self.has_variable_length = False
        for f in self.fields:
            if f.field_length == 65535:
                self.has_variable_length = True
            else:
                self.record_length += f.field_length


class IPFIXTemplateCache:
    """Cache for IPFIX templates.

    Templates are keyed by (exporter_ip, observation_domain_id, template_id).
    """

    def __init__(self, ttl_seconds: int = 3600, max_templates: int = 10000) -> None:
        """Initialize template cache.

        Args:
            ttl_seconds: Template expiration time in seconds.
            max_templates: Maximum number of templates to cache.
        """
        self._ttl_seconds = ttl_seconds
        self._max_templates = max_templates
        self._templates: dict[tuple[str, int, int], IPFIXTemplate] = {}

    def get(
        self,
        exporter_ip: str,
        observation_domain_id: int,
        template_id: int,
    ) -> IPFIXTemplate | None:
        """Get a template from cache."""
        key = (exporter_ip, observation_domain_id, template_id)
        template = self._templates.get(key)

        if template is None:
            return None

        age = (datetime.utcnow() - template.received_at).total_seconds()
        if age > self._ttl_seconds:
            del self._templates[key]
            return None

        return template

    def set(
        self,
        exporter_ip: str,
        observation_domain_id: int,
        template: IPFIXTemplate,
    ) -> None:
        """Store a template in cache."""
        if len(self._templates) >= self._max_templates:
            oldest_key = min(
                self._templates.keys(),
                key=lambda k: self._templates[k].received_at,
            )
            del self._templates[oldest_key]

        key = (exporter_ip, observation_domain_id, template.template_id)
        self._templates[key] = template

        logger.debug(
            "Cached IPFIX template",
            exporter=exporter_ip,
            domain_id=observation_domain_id,
            template_id=template.template_id,
            fields=len(template.fields),
        )

    def clear(self) -> None:
        """Clear all templates."""
        self._templates.clear()

    @property
    def size(self) -> int:
        """Get number of cached templates."""
        return len(self._templates)


class IPFIXParser(FlowParser):
    """Parser for IPFIX (NetFlow v10) packets."""

    def __init__(self, template_cache: IPFIXTemplateCache | None = None) -> None:
        """Initialize parser.

        Args:
            template_cache: Shared template cache instance.
        """
        self._template_cache = template_cache or IPFIXTemplateCache()

    @property
    def protocol_name(self) -> str:
        return "ipfix"

    @property
    def template_cache(self) -> IPFIXTemplateCache:
        """Get the template cache."""
        return self._template_cache

    def parse(
        self,
        data: bytes,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse IPFIX message into flow records.

        Args:
            data: Raw UDP packet payload.
            exporter_ip: IP address of the exporter.

        Returns:
            List of parsed flow records.

        Raises:
            ValueError: If packet is malformed.
        """
        self.validate_header(data, IPFIX_HEADER_SIZE)

        # Parse header
        header = self._parse_header(data[:IPFIX_HEADER_SIZE])

        # Validate message length
        if header["length"] > len(data):
            raise ValueError(
                f"ipfix: message truncated "
                f"(got {len(data)}, expected {header['length']} bytes)"
            )

        # Parse sets
        records: list[FlowRecord] = []
        offset = IPFIX_HEADER_SIZE

        while offset + 4 <= header["length"]:
            set_id, set_length = struct.unpack("!HH", data[offset:offset + 4])

            if set_length < 4:
                logger.warning(
                    "Invalid IPFIX set length",
                    set_id=set_id,
                    length=set_length,
                )
                break

            set_data = data[offset:offset + set_length]

            if set_id == SET_TEMPLATE:
                self._parse_template_set(
                    set_data,
                    header["observation_domain_id"],
                    str(exporter_ip),
                )
            elif set_id == SET_OPTIONS_TEMPLATE:
                # Options templates not implemented yet
                pass
            elif set_id >= SET_DATA_MIN:
                new_records = self._parse_data_set(
                    set_data,
                    set_id,
                    header,
                    exporter_ip,
                )
                records.extend(new_records)

            offset += set_length

        return records

    def _parse_header(self, data: bytes) -> dict:
        """Parse IPFIX message header.

        Args:
            data: 16 bytes of header data.

        Returns:
            Dictionary with header fields.

        Raises:
            ValueError: If version is not 10.
        """
        (
            version,
            length,
            export_time,
            sequence_number,
            observation_domain_id,
        ) = struct.unpack("!HHIII", data)

        if version != IPFIX_VERSION:
            raise ValueError(f"ipfix: invalid version {version}")

        export_timestamp = datetime.fromtimestamp(export_time, tz=timezone.utc)

        return {
            "version": version,
            "length": length,
            "export_time": export_time,
            "export_timestamp": export_timestamp,
            "sequence_number": sequence_number,
            "observation_domain_id": observation_domain_id,
        }

    def _parse_template_set(
        self,
        data: bytes,
        observation_domain_id: int,
        exporter_ip: str,
    ) -> None:
        """Parse a template set.

        Args:
            data: Set data including header.
            observation_domain_id: Observation domain ID from message header.
            exporter_ip: Exporter IP address string.
        """
        offset = 4  # Skip set header

        while offset + 4 <= len(data):
            template_id, field_count = struct.unpack(
                "!HH", data[offset:offset + 4]
            )
            offset += 4

            if template_id < 256:
                logger.warning(
                    "Invalid IPFIX template ID",
                    template_id=template_id,
                )
                break

            fields: list[IPFIXField] = []
            for _ in range(field_count):
                if offset + 4 > len(data):
                    break

                element_id, field_length = struct.unpack(
                    "!HH", data[offset:offset + 4]
                )
                offset += 4

                # Check for enterprise field (bit 15 set)
                enterprise_number = None
                if element_id & 0x8000:
                    element_id &= 0x7FFF
                    if offset + 4 <= len(data):
                        enterprise_number = struct.unpack("!I", data[offset:offset + 4])[0]
                        offset += 4

                fields.append(IPFIXField(element_id, field_length, enterprise_number))

            template = IPFIXTemplate(
                template_id=template_id,
                observation_domain_id=observation_domain_id,
                fields=fields,
            )

            self._template_cache.set(exporter_ip, observation_domain_id, template)

    def _parse_data_set(
        self,
        data: bytes,
        template_id: int,
        header: dict,
        exporter_ip: IPv4Address,
    ) -> list[FlowRecord]:
        """Parse a data set.

        Args:
            data: Set data including header.
            template_id: Template ID (same as set_id).
            header: Parsed message header.
            exporter_ip: Exporter IP address.

        Returns:
            List of parsed flow records.
        """
        template = self._template_cache.get(
            str(exporter_ip),
            header["observation_domain_id"],
            template_id,
        )

        if template is None:
            logger.debug(
                "No template for IPFIX data set",
                exporter=str(exporter_ip),
                domain_id=header["observation_domain_id"],
                template_id=template_id,
            )
            return []

        records: list[FlowRecord] = []
        offset = 4  # Skip set header
        set_length = struct.unpack("!H", data[2:4])[0]

        if template.has_variable_length:
            # Variable-length records need special handling
            while offset < set_length:
                record, bytes_consumed = self._parse_variable_record(
                    data[offset:set_length],
                    template,
                    header,
                    exporter_ip,
                )
                if record:
                    records.append(record)
                if bytes_consumed == 0:
                    break
                offset += bytes_consumed
        else:
            # Fixed-length records
            while offset + template.record_length <= set_length:
                record_data = data[offset:offset + template.record_length]
                record = self._parse_record(record_data, template, header, exporter_ip)
                if record:
                    records.append(record)
                offset += template.record_length

        return records

    def _parse_record(
        self,
        data: bytes,
        template: IPFIXTemplate,
        header: dict,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Parse a single fixed-length data record.

        Args:
            data: Record data.
            template: Template for decoding.
            header: Message header.
            exporter_ip: Exporter IP address.

        Returns:
            Parsed FlowRecord or None if required fields missing.
        """
        fields: dict[int, Any] = {}
        offset = 0

        for field in template.fields:
            if field.enterprise_number is not None:
                # Skip vendor-specific fields for now
                offset += field.field_length
                continue

            field_data = data[offset:offset + field.field_length]
            fields[field.element_id] = self._decode_field(
                field.element_id,
                field.field_length,
                field_data,
            )
            offset += field.field_length

        return self._build_flow_record(fields, header, exporter_ip)

    def _parse_variable_record(
        self,
        data: bytes,
        template: IPFIXTemplate,
        header: dict,
        exporter_ip: IPv4Address,
    ) -> tuple[FlowRecord | None, int]:
        """Parse a variable-length data record.

        Args:
            data: Record data.
            template: Template for decoding.
            header: Message header.
            exporter_ip: Exporter IP address.

        Returns:
            Tuple of (FlowRecord or None, bytes consumed).
        """
        fields: dict[int, Any] = {}
        offset = 0

        for field in template.fields:
            if offset >= len(data):
                return None, 0

            if field.field_length == 65535:
                # Variable-length field
                first_byte = data[offset]
                offset += 1
                if first_byte < 255:
                    actual_length = first_byte
                else:
                    if offset + 2 > len(data):
                        return None, 0
                    actual_length = struct.unpack("!H", data[offset:offset + 2])[0]
                    offset += 2

                if offset + actual_length > len(data):
                    return None, 0

                field_data = data[offset:offset + actual_length]
                offset += actual_length
            else:
                if offset + field.field_length > len(data):
                    return None, 0
                field_data = data[offset:offset + field.field_length]
                offset += field.field_length

            if field.enterprise_number is None:
                fields[field.element_id] = self._decode_field(
                    field.element_id,
                    len(field_data),
                    field_data,
                )

        record = self._build_flow_record(fields, header, exporter_ip)
        return record, offset

    def _build_flow_record(
        self,
        fields: dict[int, Any],
        header: dict,
        exporter_ip: IPv4Address,
    ) -> FlowRecord | None:
        """Build FlowRecord from decoded fields.

        Args:
            fields: Dictionary of decoded field values.
            header: Message header.
            exporter_ip: Exporter IP address.

        Returns:
            FlowRecord or None if required fields missing.
        """
        try:
            src_ip = fields.get(IE_SOURCE_IPV4_ADDRESS) or fields.get(IE_SOURCE_IPV6_ADDRESS)
            dst_ip = fields.get(IE_DESTINATION_IPV4_ADDRESS) or fields.get(IE_DESTINATION_IPV6_ADDRESS)

            if src_ip is None or dst_ip is None:
                return None

            src_port = fields.get(IE_SOURCE_TRANSPORT_PORT, 0)
            dst_port = fields.get(IE_DESTINATION_TRANSPORT_PORT, 0)
            protocol = fields.get(IE_PROTOCOL_IDENTIFIER, 0)

            bytes_count = (
                fields.get(IE_OCTET_DELTA_COUNT, 0) or
                fields.get(IE_OCTET_TOTAL_COUNT, 0)
            )
            packets_count = (
                fields.get(IE_PACKET_DELTA_COUNT, 0) or
                fields.get(IE_PACKET_TOTAL_COUNT, 0)
            )

            # Get timestamps
            export_ts = header["export_timestamp"]
            flow_start = fields.get(IE_FLOW_START_MILLISECONDS) or fields.get(IE_FLOW_START_SECONDS)
            flow_end = fields.get(IE_FLOW_END_MILLISECONDS) or fields.get(IE_FLOW_END_SECONDS)

            if isinstance(flow_start, int):
                flow_start = datetime.fromtimestamp(flow_start / 1000, tz=timezone.utc)
            if isinstance(flow_end, int):
                flow_end = datetime.fromtimestamp(flow_end / 1000, tz=timezone.utc)

            flow_duration_ms = fields.get(IE_FLOW_DURATION_MILLISECONDS)

            return FlowRecord(
                timestamp=flow_end or export_ts,
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
                flow_duration_ms=flow_duration_ms,
                tcp_flags=fields.get(IE_TCP_CONTROL_BITS) if protocol == 6 else None,
                exporter_id=header["observation_domain_id"],
                sampling_rate=fields.get(IE_SAMPLING_INTERVAL, 1),
                input_interface=fields.get(IE_INGRESS_INTERFACE),
                output_interface=fields.get(IE_EGRESS_INTERFACE),
                tos=fields.get(IE_IP_CLASS_OF_SERVICE),
                flow_source="ipfix",
                extended_fields={
                    "src_as": fields.get(IE_BGP_SOURCE_AS_NUMBER),
                    "dst_as": fields.get(IE_BGP_DESTINATION_AS_NUMBER),
                    "src_mask": fields.get(IE_SOURCE_IPV4_PREFIX_LENGTH) or fields.get(IE_SOURCE_IPV6_PREFIX_LENGTH),
                    "dst_mask": fields.get(IE_DESTINATION_IPV4_PREFIX_LENGTH) or fields.get(IE_DESTINATION_IPV6_PREFIX_LENGTH),
                    "next_hop": str(fields.get(IE_IP_NEXT_HOP_IPV4_ADDRESS) or fields.get(IE_IP_NEXT_HOP_IPV6_ADDRESS) or ""),
                    "direction": fields.get(IE_FLOW_DIRECTION),
                    "flow_id": fields.get(IE_FLOW_ID),
                    "sequence_number": header["sequence_number"],
                },
            )

        except Exception as e:
            logger.warning(
                "Failed to parse IPFIX record",
                error=str(e),
            )
            return None

    def _decode_field(
        self,
        element_id: int,
        field_length: int,
        data: bytes,
    ) -> Any:
        """Decode a field value based on element ID and length.

        Args:
            element_id: IPFIX information element ID.
            field_length: Field length in bytes.
            data: Raw field data.

        Returns:
            Decoded value.
        """
        # IPv4 addresses
        if element_id in (IE_SOURCE_IPV4_ADDRESS, IE_DESTINATION_IPV4_ADDRESS, IE_IP_NEXT_HOP_IPV4_ADDRESS):
            if field_length == 4:
                return IPv4Address(data)
            return None

        # IPv6 addresses
        if element_id in (IE_SOURCE_IPV6_ADDRESS, IE_DESTINATION_IPV6_ADDRESS, IE_IP_NEXT_HOP_IPV6_ADDRESS):
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

        return data
