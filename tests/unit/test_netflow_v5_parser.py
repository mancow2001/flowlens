"""Unit tests for NetFlow v5 parser."""

from ipaddress import IPv4Address

import pytest

from flowlens.ingestion.parsers.netflow_v5 import NetFlowV5Parser


class TestNetFlowV5Parser:
    """Test cases for NetFlow v5 parser."""

    @pytest.fixture
    def parser(self) -> NetFlowV5Parser:
        """Create parser instance."""
        return NetFlowV5Parser()

    @pytest.fixture
    def exporter_ip(self) -> IPv4Address:
        """Sample exporter IP."""
        return IPv4Address("10.0.0.1")

    def test_protocol_name(self, parser: NetFlowV5Parser):
        """Test protocol name property."""
        assert parser.protocol_name == "netflow_v5"

    def test_parse_valid_packet(
        self,
        parser: NetFlowV5Parser,
        exporter_ip: IPv4Address,
        sample_netflow_v5_packet: bytes,
    ):
        """Test parsing a valid NetFlow v5 packet."""
        records = parser.parse(sample_netflow_v5_packet, exporter_ip)

        assert len(records) == 1
        record = records[0]

        assert record.src_ip == IPv4Address("192.168.1.100")
        assert record.dst_ip == IPv4Address("10.0.0.1")
        assert record.src_port == 54321
        assert record.dst_port == 443
        assert record.protocol == 6  # TCP
        assert record.packets_count == 100
        assert record.bytes_count == 50000
        assert record.tcp_flags == 0x18
        assert record.flow_source == "netflow_v5"

    def test_parse_empty_packet(
        self,
        parser: NetFlowV5Parser,
        exporter_ip: IPv4Address,
    ):
        """Test parsing empty packet raises error."""
        with pytest.raises(ValueError, match="packet too short"):
            parser.parse(b"", exporter_ip)

    def test_parse_short_packet(
        self,
        parser: NetFlowV5Parser,
        exporter_ip: IPv4Address,
    ):
        """Test parsing truncated packet raises error."""
        with pytest.raises(ValueError, match="packet too short"):
            parser.parse(b"\x00\x05\x00\x01", exporter_ip)

    def test_parse_wrong_version(
        self,
        parser: NetFlowV5Parser,
        exporter_ip: IPv4Address,
    ):
        """Test parsing wrong version raises error."""
        # Create a packet with version 9 instead of 5
        import struct

        header = struct.pack(
            "!HHIIIIBBH",
            9,  # Wrong version
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )

        with pytest.raises(ValueError, match="invalid version 9"):
            parser.parse(header, exporter_ip)

    def test_parse_multiple_flows(
        self,
        parser: NetFlowV5Parser,
        exporter_ip: IPv4Address,
    ):
        """Test parsing packet with multiple flow records."""
        import struct
        from datetime import datetime

        # Header with count=2
        unix_secs = int(datetime.utcnow().timestamp())
        header = struct.pack(
            "!HHIIIIBBH",
            5, 2, 1000000, unix_secs, 0, 1, 0, 0, 0,
        )

        # Two flow records
        def make_record(src_ip: bytes, dst_ip: bytes, src_port: int, dst_port: int):
            return struct.pack(
                "!IIIHHIIIIHHBBBBHHBBH",
                int.from_bytes(src_ip, "big"),
                int.from_bytes(dst_ip, "big"),
                0, 1, 2, 100, 50000, 900000, 999000,
                src_port, dst_port, 0, 0x18, 6, 0, 0, 0, 24, 24, 0,
            )

        record1 = make_record(bytes([192, 168, 1, 1]), bytes([10, 0, 0, 1]), 12345, 80)
        record2 = make_record(bytes([192, 168, 1, 2]), bytes([10, 0, 0, 2]), 23456, 443)

        packet = header + record1 + record2
        records = parser.parse(packet, exporter_ip)

        assert len(records) == 2
        assert records[0].src_ip == IPv4Address("192.168.1.1")
        assert records[0].dst_port == 80
        assert records[1].src_ip == IPv4Address("192.168.1.2")
        assert records[1].dst_port == 443
