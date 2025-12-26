"""Heuristic signal definitions for asset classification.

Each asset type has a set of weighted signals that evaluate behavioral features.
Positive signals increase confidence, negative signals decrease it.
"""

from dataclasses import dataclass
from typing import Callable

from flowlens.classification.constants import (
    ClassifiableAssetType,
    DIURNAL_PATTERN_THRESHOLD,
    HIGH_ACTIVE_HOURS_THRESHOLD,
    HIGH_BYTES_PER_FLOW_THRESHOLD,
    HIGH_CONNECTION_RATE_THRESHOLD,
    HIGH_FAN_IN_RATIO,
    HIGH_FAN_IN_THRESHOLD,
    HIGH_FAN_OUT_THRESHOLD,
    LOW_FAN_IN_THRESHOLD,
    LOW_FAN_OUT_THRESHOLD,
    PROTOCOL_ICMP,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    SYMMETRIC_TRAFFIC_THRESHOLD,
    VERY_HIGH_FAN_IN_THRESHOLD,
)
from flowlens.classification.feature_extractor import BehavioralFeatures


@dataclass
class Signal:
    """A classification signal that evaluates a feature condition.

    Signals are weighted and can be positive (indicating the type)
    or negative (indicating NOT the type).
    """

    name: str
    weight: float
    evaluator: Callable[[BehavioralFeatures], float]
    description: str = ""

    def evaluate(self, features: BehavioralFeatures) -> float:
        """Evaluate this signal against features.

        Returns:
            Score contribution (weight * match_strength).
            match_strength is 0.0-1.0 for positive signals.
        """
        try:
            return self.weight * self.evaluator(features)
        except (ZeroDivisionError, TypeError):
            return 0.0


def _safe_ratio(a: float | None, b: float | None, default: float = 0.0) -> float:
    """Calculate a/b safely, returning default if impossible."""
    if a is None or b is None or b == 0:
        return default
    return a / b


# ============================================================================
# Server Signals
# ============================================================================

SERVER_SIGNALS = [
    Signal(
        name="high_fan_in_ratio",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_ratio and f.fan_in_ratio > HIGH_FAN_IN_RATIO else 0.0,
        description="High ratio of incoming to total connections",
    ),
    Signal(
        name="well_known_port_listener",
        weight=0.25,
        evaluator=lambda f: min(1.0, (f.well_known_port_ratio or 0) * 1.5),
        description="Listening on well-known ports",
    ),
    Signal(
        name="24x7_activity",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Active across most hours of the day",
    ),
    Signal(
        name="low_outbound_diversity",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.fan_out_count < LOW_FAN_OUT_THRESHOLD else 0.0,
        description="Low number of outbound connections",
    ),
    Signal(
        name="web_ports",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.has_web_ports else 0.0,
        description="Listening on HTTP/HTTPS ports",
    ),
    Signal(
        name="not_db_dominant",
        weight=0.10,
        evaluator=lambda f: 0.0 if f.has_db_ports and not f.has_web_ports else 1.0,
        description="Not primarily a database server",
    ),
]

# ============================================================================
# Workstation Signals
# ============================================================================

WORKSTATION_SIGNALS = [
    Signal(
        name="high_outbound_diversity",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_out_count > HIGH_FAN_OUT_THRESHOLD else (
            f.fan_out_count / HIGH_FAN_OUT_THRESHOLD if f.fan_out_count > 10 else 0.0
        ),
        description="Connects to many different destinations",
    ),
    Signal(
        name="diurnal_pattern",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.business_hours_ratio and f.business_hours_ratio > DIURNAL_PATTERN_THRESHOLD else 0.0,
        description="Traffic concentrated during business hours",
    ),
    Signal(
        name="low_fan_in",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_in_count < LOW_FAN_IN_THRESHOLD else 0.0,
        description="Few incoming connections",
    ),
    Signal(
        name="ephemeral_source_ports",
        weight=0.15,
        evaluator=lambda f: min(1.0, (f.ephemeral_port_ratio or 0) * 1.2),
        description="Uses ephemeral source ports (client behavior)",
    ),
    Signal(
        name="web_browsing_pattern",
        weight=0.15,
        evaluator=lambda f: 1.0 if 443 in (f.persistent_listener_ports or []) or f.unique_dst_ports > 20 else 0.0,
        description="Pattern consistent with web browsing",
    ),
]

# ============================================================================
# Database Signals
# ============================================================================

DATABASE_SIGNALS = [
    Signal(
        name="db_port_listener",
        weight=0.35,
        evaluator=lambda f: 1.0 if f.has_db_ports else 0.0,
        description="Listening on database ports",
    ),
    Signal(
        name="few_clients",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_in_count > 0 and f.fan_in_count < 20 else 0.0,
        description="Moderate number of client connections",
    ),
    Signal(
        name="high_bytes_per_flow",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet > HIGH_BYTES_PER_FLOW_THRESHOLD / 100 else 0.0,
        description="Large data transfers per connection",
    ),
    Signal(
        name="stable_24x7",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Available around the clock",
    ),
    Signal(
        name="server_like_pattern",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.fan_in_ratio and f.fan_in_ratio > 0.5 else 0.0,
        description="Primarily receives connections",
    ),
]

# ============================================================================
# Load Balancer Signals
# ============================================================================

LOAD_BALANCER_SIGNALS = [
    Signal(
        name="symmetric_traffic",
        weight=0.25,
        evaluator=lambda f: _compute_traffic_symmetry(f),
        description="Similar inbound and outbound traffic volumes",
    ),
    Signal(
        name="high_connection_rate",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.total_flows > HIGH_CONNECTION_RATE_THRESHOLD else (
            f.total_flows / HIGH_CONNECTION_RATE_THRESHOLD if f.total_flows > 1000 else 0.0
        ),
        description="Very high number of connections",
    ),
    Signal(
        name="web_ports",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.has_web_ports else 0.0,
        description="Listening on HTTP/HTTPS ports",
    ),
    Signal(
        name="multiple_backends",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.fan_out_count > 5 else 0.0,
        description="Connects to multiple backend servers",
    ),
    Signal(
        name="high_fan_in",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.fan_in_count > HIGH_FAN_IN_THRESHOLD else 0.0,
        description="Many client connections",
    ),
]

# ============================================================================
# Network Device Signals
# ============================================================================

NETWORK_DEVICE_SIGNALS = [
    Signal(
        name="low_port_diversity",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.unique_dst_ports < 10 else 0.0,
        description="Low variety of ports used",
    ),
    Signal(
        name="routing_protocols",
        weight=0.25,
        evaluator=lambda f: _has_routing_traffic(f),
        description="Uses ICMP or routing protocols",
    ),
    Signal(
        name="symmetric_traffic",
        weight=0.20,
        evaluator=lambda f: _compute_traffic_symmetry(f),
        description="Pass-through traffic pattern",
    ),
    Signal(
        name="high_packet_rate",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.total_flows > 1000 else 0.0,
        description="High number of small packets",
    ),
    Signal(
        name="low_bytes_per_packet",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet < 200 else 0.0,
        description="Small packet sizes (control plane)",
    ),
]

# ============================================================================
# Storage Signals
# ============================================================================

STORAGE_SIGNALS = [
    Signal(
        name="storage_port_listener",
        weight=0.35,
        evaluator=lambda f: 1.0 if f.has_storage_ports else 0.0,
        description="Listening on NFS/SMB/iSCSI ports",
    ),
    Signal(
        name="high_byte_volume",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.inbound_bytes + f.outbound_bytes > 10_000_000_000 else 0.0,  # 10GB
        description="Very high data transfer volumes",
    ),
    Signal(
        name="server_like_pattern",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_in_ratio and f.fan_in_ratio > 0.5 else 0.0,
        description="Primarily receives connections",
    ),
    Signal(
        name="stable_24x7",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Available around the clock",
    ),
]

# ============================================================================
# Cloud Service Signals
# ============================================================================

CLOUD_SERVICE_SIGNALS = [
    Signal(
        name="very_high_fan_in",
        weight=0.30,
        evaluator=lambda f: 1.0 if f.fan_in_count > VERY_HIGH_FAN_IN_THRESHOLD else (
            f.fan_in_count / VERY_HIGH_FAN_IN_THRESHOLD if f.fan_in_count > 20 else 0.0
        ),
        description="Extremely high number of client connections",
    ),
    Signal(
        name="high_connection_rate",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.total_flows > HIGH_CONNECTION_RATE_THRESHOLD * 2 else 0.0,
        description="Very high connection rate",
    ),
    Signal(
        name="web_ports",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.has_web_ports else 0.0,
        description="Listening on HTTP/HTTPS",
    ),
    Signal(
        name="24x7_activity",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > 22 else 0.0,
        description="Active all hours",
    ),
    Signal(
        name="low_outbound",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.fan_in_ratio and f.fan_in_ratio > 0.8 else 0.0,
        description="Primarily receives connections",
    ),
]

# ============================================================================
# Container Signals
# ============================================================================

CONTAINER_SIGNALS = [
    Signal(
        name="east_west_traffic",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > 0 and f.fan_out_count > 0 else 0.0,
        description="Both inbound and outbound connections",
    ),
    Signal(
        name="high_port_churn",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.unique_dst_ports > 20 or f.unique_src_ports > 10 else 0.0,
        description="Uses many different ports",
    ),
    Signal(
        name="ephemeral_listeners",
        weight=0.20,
        evaluator=lambda f: 1.0 if any(p > 30000 for p in (f.persistent_listener_ports or [])) else 0.0,
        description="Listens on high ephemeral ports",
    ),
    Signal(
        name="web_service",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.has_web_ports or 3000 in (f.persistent_listener_ports or []) or 8000 in (f.persistent_listener_ports or []) else 0.0,
        description="Common container web service pattern",
    ),
    Signal(
        name="moderate_fan_in",
        weight=0.15,
        evaluator=lambda f: 1.0 if 5 < f.fan_in_count < 50 else 0.0,
        description="Microservice pattern fan-in",
    ),
]

# ============================================================================
# Virtual Machine Signals
# ============================================================================

VIRTUAL_MACHINE_SIGNALS = [
    Signal(
        name="mixed_traffic",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > 5 and f.fan_out_count > 5 else 0.0,
        description="Both inbound and outbound activity",
    ),
    Signal(
        name="standard_server_ports",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.has_web_ports or f.has_ssh_ports else 0.0,
        description="Common server ports",
    ),
    Signal(
        name="moderate_activity",
        weight=0.20,
        evaluator=lambda f: 1.0 if 100 < f.total_flows < 5000 else 0.0,
        description="Moderate traffic volume",
    ),
    Signal(
        name="business_hours_bias",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.business_hours_ratio and 0.3 < f.business_hours_ratio < 0.8 else 0.0,
        description="Some business hours bias but not extreme",
    ),
    Signal(
        name="tcp_dominant",
        weight=0.15,
        evaluator=lambda f: _is_tcp_dominant(f),
        description="Primarily TCP traffic",
    ),
]

# ============================================================================
# Unknown Signals (low confidence baseline)
# ============================================================================

UNKNOWN_SIGNALS = [
    Signal(
        name="insufficient_data",
        weight=0.50,
        evaluator=lambda f: 1.0 if f.total_flows < 50 else 0.0,
        description="Not enough data to classify",
    ),
    Signal(
        name="no_clear_pattern",
        weight=0.50,
        evaluator=lambda f: 1.0 if f.fan_in_count == 0 and f.fan_out_count == 0 else 0.0,
        description="No clear traffic pattern",
    ),
]


# ============================================================================
# Helper Functions
# ============================================================================

def _compute_traffic_symmetry(features: BehavioralFeatures) -> float:
    """Compute how symmetric the traffic is (0 = asymmetric, 1 = symmetric)."""
    total = features.inbound_bytes + features.outbound_bytes
    if total == 0:
        return 0.0

    diff = abs(features.inbound_bytes - features.outbound_bytes)
    asymmetry = diff / total

    # Invert: low asymmetry = high symmetry
    symmetry = 1.0 - asymmetry

    # Return 1.0 if symmetry is high enough
    return 1.0 if symmetry > (1.0 - SYMMETRIC_TRAFFIC_THRESHOLD) else symmetry


def _has_routing_traffic(features: BehavioralFeatures) -> float:
    """Check if traffic includes routing protocols (ICMP, etc.)."""
    protocol_dist = features.protocol_distribution or {}
    total_flows = sum(protocol_dist.values())

    if total_flows == 0:
        return 0.0

    # Check for ICMP traffic
    icmp_flows = protocol_dist.get(PROTOCOL_ICMP, 0)

    if icmp_flows > 0:
        icmp_ratio = icmp_flows / total_flows
        return min(1.0, icmp_ratio * 10)  # Even small ICMP presence is significant

    return 0.0


def _is_tcp_dominant(features: BehavioralFeatures) -> float:
    """Check if TCP is the dominant protocol."""
    protocol_dist = features.protocol_distribution or {}
    total_flows = sum(protocol_dist.values())

    if total_flows == 0:
        return 0.0

    tcp_flows = protocol_dist.get(PROTOCOL_TCP, 0)
    tcp_ratio = tcp_flows / total_flows

    return 1.0 if tcp_ratio > 0.8 else tcp_ratio


# ============================================================================
# Signal Registry
# ============================================================================

ASSET_TYPE_SIGNALS: dict[ClassifiableAssetType, list[Signal]] = {
    ClassifiableAssetType.SERVER: SERVER_SIGNALS,
    ClassifiableAssetType.WORKSTATION: WORKSTATION_SIGNALS,
    ClassifiableAssetType.DATABASE: DATABASE_SIGNALS,
    ClassifiableAssetType.LOAD_BALANCER: LOAD_BALANCER_SIGNALS,
    ClassifiableAssetType.NETWORK_DEVICE: NETWORK_DEVICE_SIGNALS,
    ClassifiableAssetType.STORAGE: STORAGE_SIGNALS,
    ClassifiableAssetType.CLOUD_SERVICE: CLOUD_SERVICE_SIGNALS,
    ClassifiableAssetType.CONTAINER: CONTAINER_SIGNALS,
    ClassifiableAssetType.VIRTUAL_MACHINE: VIRTUAL_MACHINE_SIGNALS,
    ClassifiableAssetType.UNKNOWN: UNKNOWN_SIGNALS,
}


def get_signals_for_type(asset_type: ClassifiableAssetType) -> list[Signal]:
    """Get the heuristic signals for an asset type."""
    return ASSET_TYPE_SIGNALS.get(asset_type, [])
