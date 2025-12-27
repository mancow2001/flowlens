"""Unit tests for flow aggregator."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from flowlens.resolution.aggregator import (
    EPHEMERAL_PORT_THRESHOLD,
    AggregationBucket,
    AggregationKey,
    FlowAggregator,
    is_ephemeral_port,
    normalize_flow_direction,
)


@pytest.mark.unit
class TestIsEphemeralPort:
    """Test cases for is_ephemeral_port function."""

    def test_ephemeral_port_threshold(self):
        """Test ephemeral port threshold value."""
        assert EPHEMERAL_PORT_THRESHOLD == 32768

    def test_well_known_ports_not_ephemeral(self):
        """Test well-known ports are not ephemeral."""
        assert is_ephemeral_port(22) is False
        assert is_ephemeral_port(80) is False
        assert is_ephemeral_port(443) is False
        assert is_ephemeral_port(3306) is False
        assert is_ephemeral_port(8080) is False

    def test_ephemeral_ports_detected(self):
        """Test ephemeral ports are detected."""
        assert is_ephemeral_port(32768) is True
        assert is_ephemeral_port(40000) is True
        assert is_ephemeral_port(50000) is True
        assert is_ephemeral_port(65535) is True

    def test_boundary_port(self):
        """Test boundary between registered and ephemeral."""
        assert is_ephemeral_port(32767) is False
        assert is_ephemeral_port(32768) is True


@pytest.mark.unit
class TestNormalizeFlowDirection:
    """Test cases for normalize_flow_direction function."""

    def test_normal_client_to_server(self):
        """Test normal client → server direction is preserved."""
        client_ip, server_ip, service_port, protocol = normalize_flow_direction(
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            src_port=50000,  # Ephemeral
            dst_port=443,    # Well-known
            protocol=6,
        )

        assert client_ip == "192.168.1.100"
        assert server_ip == "10.0.0.1"
        assert service_port == 443
        assert protocol == 6

    def test_response_flow_normalized(self):
        """Test response flow (server → client) is normalized."""
        client_ip, server_ip, service_port, protocol = normalize_flow_direction(
            src_ip="10.0.0.1",     # Server
            dst_ip="192.168.1.100", # Client
            src_port=443,          # Well-known
            dst_port=50000,        # Ephemeral
            protocol=6,
        )

        # Should be normalized to client → server
        assert client_ip == "192.168.1.100"
        assert server_ip == "10.0.0.1"
        assert service_port == 443
        assert protocol == 6

    def test_both_well_known_ports(self):
        """Test when both ports are well-known (server to server)."""
        client_ip, server_ip, service_port, protocol = normalize_flow_direction(
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            src_port=80,   # Well-known
            dst_port=443,  # Well-known
            protocol=6,
        )

        # Keeps original direction since dst is not ephemeral
        assert client_ip == "192.168.1.100"
        assert server_ip == "10.0.0.1"
        assert service_port == 443

    def test_both_ephemeral_ports(self):
        """Test when both ports are ephemeral."""
        client_ip, server_ip, service_port, protocol = normalize_flow_direction(
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            src_port=50000,  # Ephemeral
            dst_port=60000,  # Ephemeral
            protocol=6,
        )

        # Keeps original direction
        assert client_ip == "192.168.1.100"
        assert server_ip == "10.0.0.1"
        assert service_port == 60000

    def test_udp_protocol(self):
        """Test UDP flows work correctly."""
        client_ip, server_ip, service_port, protocol = normalize_flow_direction(
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            src_port=50000,
            dst_port=53,  # DNS
            protocol=17,  # UDP
        )

        assert protocol == 17
        assert service_port == 53


@pytest.mark.unit
class TestAggregationKey:
    """Test cases for AggregationKey dataclass."""

    def test_create_key(self):
        """Test creating an aggregation key."""
        key = AggregationKey(
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            dst_port=443,
            protocol=6,
        )

        assert key.src_ip == "192.168.1.100"
        assert key.dst_ip == "10.0.0.1"
        assert key.dst_port == 443
        assert key.protocol == 6

    def test_key_hashable(self):
        """Test keys are hashable for dict usage."""
        key = AggregationKey(
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            dst_port=443,
            protocol=6,
        )

        # Should not raise
        hash_value = hash(key)
        assert isinstance(hash_value, int)

    def test_identical_keys_have_same_hash(self):
        """Test identical keys have the same hash."""
        key1 = AggregationKey("192.168.1.100", "10.0.0.1", 443, 6)
        key2 = AggregationKey("192.168.1.100", "10.0.0.1", 443, 6)

        assert hash(key1) == hash(key2)

    def test_different_keys_have_different_hash(self):
        """Test different keys have different hashes."""
        key1 = AggregationKey("192.168.1.100", "10.0.0.1", 443, 6)
        key2 = AggregationKey("192.168.1.100", "10.0.0.1", 80, 6)

        assert hash(key1) != hash(key2)

    def test_key_usable_as_dict_key(self):
        """Test keys work as dictionary keys."""
        key1 = AggregationKey("192.168.1.100", "10.0.0.1", 443, 6)
        key2 = AggregationKey("192.168.1.101", "10.0.0.1", 80, 6)

        buckets = {key1: "bucket1", key2: "bucket2"}

        assert buckets[key1] == "bucket1"
        assert buckets[key2] == "bucket2"


@pytest.mark.unit
class TestAggregationBucket:
    """Test cases for AggregationBucket dataclass."""

    def test_initial_state(self):
        """Test bucket initial state."""
        bucket = AggregationBucket()

        assert bucket.bytes_total == 0
        assert bucket.packets_total == 0
        assert bucket.flows_count == 0
        assert bucket.bytes_max == 0
        assert len(bucket.unique_sources) == 0
        assert len(bucket.unique_destinations) == 0

    def test_add_single_flow(self):
        """Test adding a single flow to bucket."""
        bucket = AggregationBucket()
        bucket.add(
            bytes_count=1000,
            packets_count=10,
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
        )

        assert bucket.bytes_total == 1000
        assert bucket.packets_total == 10
        assert bucket.flows_count == 1
        assert bucket.bytes_min == 1000
        assert bucket.bytes_max == 1000
        assert "192.168.1.100" in bucket.unique_sources
        assert "10.0.0.1" in bucket.unique_destinations

    def test_add_multiple_flows(self):
        """Test adding multiple flows to bucket."""
        bucket = AggregationBucket()

        bucket.add(bytes_count=1000, packets_count=10, src_ip="192.168.1.100", dst_ip="10.0.0.1")
        bucket.add(bytes_count=2000, packets_count=20, src_ip="192.168.1.101", dst_ip="10.0.0.1")
        bucket.add(bytes_count=500, packets_count=5, src_ip="192.168.1.100", dst_ip="10.0.0.2")

        assert bucket.bytes_total == 3500
        assert bucket.packets_total == 35
        assert bucket.flows_count == 3
        assert bucket.bytes_min == 500
        assert bucket.bytes_max == 2000
        assert len(bucket.unique_sources) == 2
        assert len(bucket.unique_destinations) == 2

    def test_bytes_avg(self):
        """Test average bytes calculation."""
        bucket = AggregationBucket()

        bucket.add(bytes_count=1000, packets_count=10, src_ip="a", dst_ip="b")
        bucket.add(bytes_count=2000, packets_count=20, src_ip="a", dst_ip="b")
        bucket.add(bytes_count=3000, packets_count=30, src_ip="a", dst_ip="b")

        assert bucket.bytes_avg == 2000.0

    def test_bytes_avg_empty(self):
        """Test average bytes with no flows."""
        bucket = AggregationBucket()

        assert bucket.bytes_avg == 0.0

    def test_add_with_asset_ids(self):
        """Test adding flows with asset IDs."""
        src_id = uuid4()
        dst_id = uuid4()

        bucket = AggregationBucket()
        bucket.add(
            bytes_count=1000,
            packets_count=10,
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            src_asset_id=src_id,
            dst_asset_id=dst_id,
        )

        assert bucket.src_asset_id == src_id
        assert bucket.dst_asset_id == dst_id

    def test_add_with_gateway(self):
        """Test adding flows with gateway info."""
        bucket = AggregationBucket()

        bucket.add(
            bytes_count=1000,
            packets_count=10,
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            gateway_ip="192.168.1.1",
        )

        assert "192.168.1.1" in bucket.gateway_bytes
        assert bucket.gateway_bytes["192.168.1.1"] == 1000

    def test_add_with_multiple_gateways(self):
        """Test adding flows with multiple gateways."""
        bucket = AggregationBucket()

        bucket.add(bytes_count=1000, packets_count=10, src_ip="a", dst_ip="b", gateway_ip="192.168.1.1")
        bucket.add(bytes_count=2000, packets_count=20, src_ip="a", dst_ip="b", gateway_ip="192.168.1.2")
        bucket.add(bytes_count=500, packets_count=5, src_ip="a", dst_ip="b", gateway_ip="192.168.1.1")

        assert bucket.gateway_bytes["192.168.1.1"] == 1500
        assert bucket.gateway_bytes["192.168.1.2"] == 2000

    def test_primary_gateway_ip(self):
        """Test primary gateway is the one with most traffic."""
        bucket = AggregationBucket()

        bucket.add(bytes_count=1000, packets_count=10, src_ip="a", dst_ip="b", gateway_ip="192.168.1.1")
        bucket.add(bytes_count=5000, packets_count=50, src_ip="a", dst_ip="b", gateway_ip="192.168.1.2")

        assert bucket.primary_gateway_ip == "192.168.1.2"

    def test_primary_gateway_ip_none(self):
        """Test primary gateway is None when no gateways."""
        bucket = AggregationBucket()
        bucket.add(bytes_count=1000, packets_count=10, src_ip="a", dst_ip="b")

        assert bucket.primary_gateway_ip is None

    def test_zero_gateway_ignored(self):
        """Test zero gateway (0.0.0.0) is ignored."""
        bucket = AggregationBucket()
        bucket.add(bytes_count=1000, packets_count=10, src_ip="a", dst_ip="b", gateway_ip="0.0.0.0")

        assert len(bucket.gateway_bytes) == 0
        assert bucket.primary_gateway_ip is None

    def test_empty_gateway_ignored(self):
        """Test empty gateway is ignored."""
        bucket = AggregationBucket()
        bucket.add(bytes_count=1000, packets_count=10, src_ip="a", dst_ip="b", gateway_ip="")

        assert len(bucket.gateway_bytes) == 0

    def test_add_with_exporter_ip(self):
        """Test adding flows with exporter IP."""
        bucket = AggregationBucket()
        bucket.add(
            bytes_count=1000,
            packets_count=10,
            src_ip="192.168.1.100",
            dst_ip="10.0.0.1",
            exporter_ip="192.168.1.1",
        )

        assert bucket.exporter_ip == "192.168.1.1"


@pytest.mark.unit
class TestFlowAggregator:
    """Test cases for FlowAggregator class."""

    @pytest.fixture
    def aggregator(self) -> FlowAggregator:
        """Create aggregator instance."""
        return FlowAggregator()

    def test_aggregator_initialization(self, aggregator: FlowAggregator):
        """Test aggregator initializes correctly."""
        assert aggregator._window_size_minutes > 0
        assert aggregator._batch_size > 0

    def test_get_window_bounds_exact_boundary(self, aggregator: FlowAggregator):
        """Test window bounds at exact window boundary."""
        # Assume 5-minute windows
        if aggregator._window_size_minutes != 5:
            pytest.skip("Test assumes 5-minute windows")

        timestamp = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        start, end = aggregator.get_window_bounds(timestamp)

        assert start == datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2025, 1, 15, 10, 5, 0, tzinfo=timezone.utc)

    def test_get_window_bounds_mid_window(self, aggregator: FlowAggregator):
        """Test window bounds for timestamp mid-window."""
        if aggregator._window_size_minutes != 5:
            pytest.skip("Test assumes 5-minute windows")

        timestamp = datetime(2025, 1, 15, 10, 3, 30, tzinfo=timezone.utc)
        start, end = aggregator.get_window_bounds(timestamp)

        assert start == datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2025, 1, 15, 10, 5, 0, tzinfo=timezone.utc)

    def test_get_window_bounds_end_of_window(self, aggregator: FlowAggregator):
        """Test window bounds for timestamp at end of window."""
        if aggregator._window_size_minutes != 5:
            pytest.skip("Test assumes 5-minute windows")

        timestamp = datetime(2025, 1, 15, 10, 4, 59, tzinfo=timezone.utc)
        start, end = aggregator.get_window_bounds(timestamp)

        assert start == datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert end == datetime(2025, 1, 15, 10, 5, 0, tzinfo=timezone.utc)

    def test_get_window_bounds_strips_seconds(self, aggregator: FlowAggregator):
        """Test that window bounds strip seconds and microseconds."""
        timestamp = datetime(2025, 1, 15, 10, 2, 45, 123456, tzinfo=timezone.utc)
        start, end = aggregator.get_window_bounds(timestamp)

        assert start.second == 0
        assert start.microsecond == 0
        assert end.second == 0
        assert end.microsecond == 0

    def test_consecutive_windows(self, aggregator: FlowAggregator):
        """Test consecutive windows don't overlap."""
        if aggregator._window_size_minutes != 5:
            pytest.skip("Test assumes 5-minute windows")

        ts1 = datetime(2025, 1, 15, 10, 2, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 15, 10, 7, 0, tzinfo=timezone.utc)

        start1, end1 = aggregator.get_window_bounds(ts1)
        start2, end2 = aggregator.get_window_bounds(ts2)

        # Windows should be consecutive
        assert end1 == start2
        assert start1 < start2
        assert end1 < end2
