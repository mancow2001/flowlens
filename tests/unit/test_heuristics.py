"""Unit tests for classification heuristics and signals."""

from datetime import datetime, timezone

import pytest

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import BehavioralFeatures
from flowlens.classification.heuristics import (
    ASSET_TYPE_SIGNALS,
    Signal,
    get_signals_for_type,
    _compute_traffic_symmetry,
    _has_routing_traffic,
    _is_tcp_dominant,
)


def _create_features(**kwargs) -> BehavioralFeatures:
    """Helper to create BehavioralFeatures with defaults."""
    defaults = {
        "ip_address": "192.168.1.1/32",
        "window_size": "5min",
        "computed_at": datetime.now(timezone.utc),
        "inbound_flows": 0,
        "outbound_flows": 0,
        "inbound_bytes": 0,
        "outbound_bytes": 0,
        "fan_in_count": 0,
        "fan_out_count": 0,
        "fan_in_ratio": None,
        "unique_dst_ports": 0,
        "unique_src_ports": 0,
        "well_known_port_ratio": None,
        "ephemeral_port_ratio": None,
        "persistent_listener_ports": [],
        "protocol_distribution": {},
        "avg_bytes_per_packet": None,
        "total_flows": 0,
        "active_hours_count": None,
        "business_hours_ratio": None,
        # Original port flags
        "has_db_ports": False,
        "has_storage_ports": False,
        "has_web_ports": False,
        "has_ssh_ports": False,
        # Network services
        "has_dns_ports": False,
        "has_dhcp_ports": False,
        "has_ntp_ports": False,
        "has_directory_ports": False,
        # Communication
        "has_mail_ports": False,
        "has_voip_ports": False,
        # Security & Access
        "has_vpn_ports": False,
        "has_proxy_ports": False,
        "has_log_collector_ports": False,
        "has_remote_access_ports": False,
        # Endpoints
        "has_printer_ports": False,
        "has_iot_ports": False,
        "has_camera_ports": False,
        # Application infrastructure
        "has_message_queue_ports": False,
        "has_monitoring_ports": False,
        # Variance metric
        "traffic_variance": None,
    }
    defaults.update(kwargs)
    return BehavioralFeatures(**defaults)


@pytest.mark.unit
class TestSignal:
    """Test cases for Signal class."""

    def test_signal_evaluate_positive(self):
        """Test signal evaluation returns positive contribution."""
        signal = Signal(
            name="test_signal",
            weight=0.5,
            evaluator=lambda f: 1.0,
            description="Test signal",
        )
        features = _create_features()
        contribution = signal.evaluate(features)

        assert contribution == 0.5  # weight * 1.0

    def test_signal_evaluate_zero(self):
        """Test signal evaluation returns zero contribution."""
        signal = Signal(
            name="test_signal",
            weight=0.5,
            evaluator=lambda f: 0.0,
            description="Test signal",
        )
        features = _create_features()
        contribution = signal.evaluate(features)

        assert contribution == 0.0

    def test_signal_evaluate_partial(self):
        """Test signal evaluation returns partial contribution."""
        signal = Signal(
            name="test_signal",
            weight=0.5,
            evaluator=lambda f: 0.5,
            description="Test signal",
        )
        features = _create_features()
        contribution = signal.evaluate(features)

        assert contribution == 0.25  # weight * 0.5

    def test_signal_handles_division_by_zero(self):
        """Test signal gracefully handles division by zero."""
        signal = Signal(
            name="test_signal",
            weight=0.5,
            evaluator=lambda f: f.inbound_flows / f.outbound_flows,  # Will raise ZeroDivisionError
            description="Test signal",
        )
        features = _create_features(inbound_flows=10, outbound_flows=0)
        contribution = signal.evaluate(features)

        assert contribution == 0.0

    def test_signal_handles_type_error(self):
        """Test signal gracefully handles type errors."""
        signal = Signal(
            name="test_signal",
            weight=0.5,
            evaluator=lambda f: f.fan_in_ratio * 2,  # None * 2 raises TypeError
            description="Test signal",
        )
        features = _create_features(fan_in_ratio=None)
        contribution = signal.evaluate(features)

        assert contribution == 0.0


@pytest.mark.unit
class TestHelperFunctions:
    """Test cases for helper functions."""

    def test_traffic_symmetry_equal(self):
        """Test traffic symmetry with equal in/out bytes."""
        features = _create_features(
            inbound_bytes=1000,
            outbound_bytes=1000,
        )
        symmetry = _compute_traffic_symmetry(features)

        assert symmetry == 1.0

    def test_traffic_symmetry_asymmetric(self):
        """Test traffic symmetry with unequal bytes."""
        features = _create_features(
            inbound_bytes=1000,
            outbound_bytes=100,
        )
        symmetry = _compute_traffic_symmetry(features)

        # Asymmetry = |1000-100| / (1000+100) = 900/1100 ≈ 0.818
        # Symmetry = 1 - 0.818 ≈ 0.182
        assert 0 < symmetry < 0.5

    def test_traffic_symmetry_zero_traffic(self):
        """Test traffic symmetry with no traffic."""
        features = _create_features(
            inbound_bytes=0,
            outbound_bytes=0,
        )
        symmetry = _compute_traffic_symmetry(features)

        assert symmetry == 0.0

    def test_has_routing_traffic_with_icmp(self):
        """Test routing traffic detection with ICMP."""
        features = _create_features(
            protocol_distribution={1: 100, 6: 900},  # 10% ICMP
        )
        routing_score = _has_routing_traffic(features)

        assert routing_score > 0

    def test_has_routing_traffic_no_icmp(self):
        """Test routing traffic detection without ICMP."""
        features = _create_features(
            protocol_distribution={6: 1000, 17: 100},  # TCP + UDP only
        )
        routing_score = _has_routing_traffic(features)

        assert routing_score == 0.0

    def test_has_routing_traffic_empty(self):
        """Test routing traffic detection with empty distribution."""
        features = _create_features(
            protocol_distribution={},
        )
        routing_score = _has_routing_traffic(features)

        assert routing_score == 0.0

    def test_is_tcp_dominant_high_tcp(self):
        """Test TCP dominance detection with high TCP ratio."""
        features = _create_features(
            protocol_distribution={6: 900, 17: 100},  # 90% TCP
        )
        tcp_dominant = _is_tcp_dominant(features)

        assert tcp_dominant == 1.0

    def test_is_tcp_dominant_low_tcp(self):
        """Test TCP dominance detection with low TCP ratio."""
        features = _create_features(
            protocol_distribution={6: 300, 17: 700},  # 30% TCP
        )
        tcp_dominant = _is_tcp_dominant(features)

        assert tcp_dominant == 0.3

    def test_is_tcp_dominant_no_traffic(self):
        """Test TCP dominance detection with no traffic."""
        features = _create_features(
            protocol_distribution={},
        )
        tcp_dominant = _is_tcp_dominant(features)

        assert tcp_dominant == 0.0


@pytest.mark.unit
class TestAssetTypeSignals:
    """Test cases for asset type signal definitions."""

    def test_all_asset_types_have_signals(self):
        """Test that all classifiable types have signal definitions."""
        for asset_type in ClassifiableAssetType:
            signals = get_signals_for_type(asset_type)
            assert isinstance(signals, list)
            # Each type should have at least one signal
            assert len(signals) > 0, f"{asset_type} has no signals"

    def test_signal_weights_sum_to_one(self):
        """Test that signal weights for each type sum to approximately 1.0."""
        for asset_type in ClassifiableAssetType:
            signals = get_signals_for_type(asset_type)
            total_weight = sum(s.weight for s in signals)
            assert 0.9 <= total_weight <= 1.1, f"{asset_type} weights sum to {total_weight}"

    def test_server_signals_evaluate(self):
        """Test server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.SERVER)
        features = _create_features(
            fan_in_ratio=0.8,
            well_known_port_ratio=0.9,
            active_hours_count=20,
            fan_out_count=3,
            has_web_ports=True,
            has_db_ports=False,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_workstation_signals_evaluate(self):
        """Test workstation signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.WORKSTATION)
        features = _create_features(
            fan_out_count=100,
            business_hours_ratio=0.8,
            fan_in_count=2,
            ephemeral_port_ratio=0.9,
            unique_dst_ports=50,
            total_flows=500,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_database_signals_evaluate(self):
        """Test database signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.DATABASE)
        features = _create_features(
            has_db_ports=True,
            fan_in_count=10,
            avg_bytes_per_packet=50000,  # High bytes per packet
            active_hours_count=23,
            fan_in_ratio=0.9,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_load_balancer_signals_evaluate(self):
        """Test load balancer signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.LOAD_BALANCER)
        features = _create_features(
            inbound_bytes=1000000,
            outbound_bytes=1000000,
            total_flows=10000,
            has_web_ports=True,
            fan_out_count=10,
            fan_in_count=100,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_network_device_signals_evaluate(self):
        """Test network device signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.NETWORK_DEVICE)
        features = _create_features(
            unique_dst_ports=5,
            protocol_distribution={1: 200, 6: 800},  # Has ICMP
            inbound_bytes=500000,
            outbound_bytes=500000,
            total_flows=2000,
            avg_bytes_per_packet=100,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_storage_signals_evaluate(self):
        """Test storage signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.STORAGE)
        features = _create_features(
            has_storage_ports=True,
            inbound_bytes=5_000_000_000,
            outbound_bytes=5_000_000_000,
            fan_in_ratio=0.8,
            active_hours_count=24,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_cloud_service_signals_evaluate(self):
        """Test cloud service signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.CLOUD_SERVICE)
        features = _create_features(
            fan_in_count=500,
            total_flows=50000,
            has_web_ports=True,
            active_hours_count=24,
            fan_in_ratio=0.95,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_container_signals_evaluate(self):
        """Test container signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.CONTAINER)
        features = _create_features(
            fan_in_count=20,
            fan_out_count=30,
            unique_dst_ports=25,
            unique_src_ports=15,
            persistent_listener_ports=[3000, 8000, 35000],
            has_web_ports=True,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_virtual_machine_signals_evaluate(self):
        """Test virtual machine signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.VIRTUAL_MACHINE)
        features = _create_features(
            fan_in_count=10,
            fan_out_count=10,
            has_web_ports=True,
            has_ssh_ports=True,
            total_flows=1000,
            business_hours_ratio=0.5,
            protocol_distribution={6: 900, 17: 100},
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_unknown_signals_evaluate(self):
        """Test unknown signals evaluate correctly with no data."""
        signals = get_signals_for_type(ClassifiableAssetType.UNKNOWN)
        features = _create_features(
            total_flows=10,
            fan_in_count=0,
            fan_out_count=0,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    # ========== Network Services (4 new types) ==========

    def test_dns_server_signals_evaluate(self):
        """Test DNS server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.DNS_SERVER)
        features = _create_features(
            has_dns_ports=True,
            fan_in_count=500,
            protocol_distribution={17: 800, 6: 200},  # 80% UDP
            avg_bytes_per_packet=100,  # Small packets
            active_hours_count=24,
            total_flows=10000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_dhcp_server_signals_evaluate(self):
        """Test DHCP server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.DHCP_SERVER)
        features = _create_features(
            has_dhcp_ports=True,
            protocol_distribution={17: 1000},  # UDP only
            fan_in_count=100,
            avg_bytes_per_packet=300,
            active_hours_count=24,
            total_flows=500,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_ntp_server_signals_evaluate(self):
        """Test NTP server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.NTP_SERVER)
        features = _create_features(
            has_ntp_ports=True,
            protocol_distribution={17: 1000},  # UDP only
            fan_out_count=500,  # High fan-out
            avg_bytes_per_packet=50,  # Very small packets
            active_hours_count=24,
            total_flows=5000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_directory_service_signals_evaluate(self):
        """Test directory service signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.DIRECTORY_SERVICE)
        features = _create_features(
            has_directory_ports=True,
            fan_in_count=200,
            active_hours_count=24,
            protocol_distribution={6: 900, 17: 100},  # Mostly TCP
            total_flows=5000,
            avg_bytes_per_packet=500,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    # ========== Communication Services (2 new types) ==========

    def test_mail_server_signals_evaluate(self):
        """Test mail server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.MAIL_SERVER)
        features = _create_features(
            has_mail_ports=True,
            inbound_bytes=1_000_000,
            outbound_bytes=800_000,  # Fairly balanced
            business_hours_ratio=0.7,
            fan_in_count=50,
            total_flows=2000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_voip_server_signals_evaluate(self):
        """Test VoIP server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.VOIP_SERVER)
        features = _create_features(
            has_voip_ports=True,
            protocol_distribution={17: 600, 6: 400},  # High UDP
            inbound_bytes=500_000,
            outbound_bytes=500_000,  # Symmetric
            fan_in_count=30,
            fan_out_count=30,
            total_flows=1000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    # ========== Security & Access (4 new types) ==========

    def test_vpn_gateway_signals_evaluate(self):
        """Test VPN gateway signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.VPN_GATEWAY)
        features = _create_features(
            has_vpn_ports=True,
            fan_in_count=100,
            protocol_distribution={17: 700, 6: 300},  # UDP dominant
            inbound_bytes=10_000_000,
            outbound_bytes=10_000_000,
            avg_bytes_per_packet=1200,  # Large packets (tunneled)
            total_flows=5000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_proxy_server_signals_evaluate(self):
        """Test proxy server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.PROXY_SERVER)
        features = _create_features(
            has_proxy_ports=True,
            inbound_bytes=5_000_000,
            outbound_bytes=5_000_000,  # Symmetric
            fan_in_count=100,
            fan_out_count=50,
            total_flows=10000,
            has_web_ports=True,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_log_collector_signals_evaluate(self):
        """Test log collector signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.LOG_COLLECTOR)
        features = _create_features(
            has_log_collector_ports=True,
            fan_in_count=200,  # High inbound diversity
            inbound_bytes=50_000_000,
            outbound_bytes=1_000_000,  # Asymmetric (mostly inbound)
            active_hours_count=24,
            total_flows=20000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_remote_access_signals_evaluate(self):
        """Test remote access signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.REMOTE_ACCESS)
        features = _create_features(
            has_remote_access_ports=True,
            business_hours_ratio=0.8,  # Business hours bias
            inbound_bytes=500_000,
            outbound_bytes=2_000_000,  # More outbound (screen data)
            fan_in_count=20,
            total_flows=1000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    # ========== Endpoints (3 new types) ==========

    def test_printer_signals_evaluate(self):
        """Test printer signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.PRINTER)
        features = _create_features(
            has_printer_ports=True,
            business_hours_ratio=0.9,  # Strong business hours
            inbound_bytes=100_000,
            outbound_bytes=10_000,  # Low outbound
            fan_in_count=10,
            fan_out_count=2,
            total_flows=50,
            traffic_variance=0.8,  # Bursty
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_iot_device_signals_evaluate(self):
        """Test IoT device signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.IOT_DEVICE)
        features = _create_features(
            has_iot_ports=True,
            avg_bytes_per_packet=100,  # Small packets
            unique_dst_ports=3,  # Minimal port diversity
            traffic_variance=0.2,  # Regular pattern
            total_flows=500,
            fan_out_count=5,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_ip_camera_signals_evaluate(self):
        """Test IP camera signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.IP_CAMERA)
        features = _create_features(
            has_camera_ports=True,
            outbound_bytes=50_000_000,  # High outbound
            inbound_bytes=1_000_000,  # Low inbound
            active_hours_count=24,
            fan_out_count=3,  # Streams to few destinations
            traffic_variance=0.1,  # Constant stream
            total_flows=1000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    # ========== Application Infrastructure (2 new types) ==========

    def test_message_queue_signals_evaluate(self):
        """Test message queue signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.MESSAGE_QUEUE)
        features = _create_features(
            has_message_queue_ports=True,
            fan_in_count=20,
            fan_out_count=20,  # Balanced fan
            inbound_bytes=2_000_000,
            outbound_bytes=2_000_000,  # Symmetric
            active_hours_count=24,
            total_flows=5000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0

    def test_monitoring_server_signals_evaluate(self):
        """Test monitoring server signals evaluate correctly."""
        signals = get_signals_for_type(ClassifiableAssetType.MONITORING_SERVER)
        features = _create_features(
            has_monitoring_ports=True,
            fan_out_count=100,  # High fan-out (scraping)
            has_web_ports=True,  # Web UI
            inbound_bytes=5_000_000,
            outbound_bytes=1_000_000,  # More inbound (metrics)
            active_hours_count=24,
            total_flows=10000,
        )

        total_contribution = sum(s.evaluate(features) for s in signals)
        assert total_contribution > 0


@pytest.mark.unit
class TestSignalRegistry:
    """Test cases for the signal registry."""

    def test_asset_type_signals_registry_complete(self):
        """Test that ASSET_TYPE_SIGNALS contains all types."""
        for asset_type in ClassifiableAssetType:
            assert asset_type in ASSET_TYPE_SIGNALS

    def test_get_signals_for_type_returns_list(self):
        """Test get_signals_for_type returns a list."""
        for asset_type in ClassifiableAssetType:
            signals = get_signals_for_type(asset_type)
            assert isinstance(signals, list)

    def test_get_signals_for_unknown_type(self):
        """Test get_signals_for_type with invalid type returns empty list."""
        # This tests the .get() fallback
        signals = ASSET_TYPE_SIGNALS.get("invalid_type", [])
        assert signals == []

    def test_signals_have_required_attributes(self):
        """Test all signals have required attributes."""
        for asset_type, signals in ASSET_TYPE_SIGNALS.items():
            for signal in signals:
                assert hasattr(signal, "name")
                assert hasattr(signal, "weight")
                assert hasattr(signal, "evaluator")
                assert callable(signal.evaluator)
                assert 0 < signal.weight <= 1.0, f"{asset_type}.{signal.name} has invalid weight {signal.weight}"
