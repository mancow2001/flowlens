"""Heuristic signal definitions for asset classification.

Each asset type has a set of weighted signals that evaluate behavioral features.
Positive signals increase confidence, negative signals decrease it.
"""

from collections.abc import Callable
from dataclasses import dataclass

from flowlens.classification.constants import (
    CAMERA_PORTS,
    DHCP_SERVER_PORTS,
    DIRECTORY_PORTS,
    DIURNAL_PATTERN_THRESHOLD,
    DNS_PORTS,
    HIGH_ACTIVE_HOURS_THRESHOLD,
    HIGH_BYTES_PER_FLOW_THRESHOLD,
    HIGH_CONNECTION_RATE_THRESHOLD,
    HIGH_FAN_IN_RATIO,
    HIGH_FAN_IN_THRESHOLD,
    HIGH_FAN_OUT_THRESHOLD,
    IOT_PORTS,
    LOG_COLLECTOR_PORTS,
    LOW_FAN_IN_THRESHOLD,
    LOW_FAN_OUT_THRESHOLD,
    MAIL_PORTS,
    MESSAGE_QUEUE_PORTS,
    MONITORING_PORTS,
    NTP_PORTS,
    PRINTER_PORTS,
    PROTOCOL_ICMP,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    PROXY_PORTS,
    REMOTE_ACCESS_PORTS,
    SYMMETRIC_TRAFFIC_THRESHOLD,
    VERY_HIGH_FAN_IN_THRESHOLD,
    VOIP_PORTS,
    VPN_PORTS,
    ClassifiableAssetType,
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
# DNS Server Signals
# ============================================================================

DNS_SERVER_SIGNALS = [
    Signal(
        name="dns_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, DNS_PORTS),
        description="Listening on DNS port 53",
    ),
    Signal(
        name="udp_dominant",
        weight=0.25,
        evaluator=lambda f: _is_udp_dominant(f, 0.7),
        description="UDP-dominant traffic pattern",
    ),
    Signal(
        name="high_fan_in",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_in_count > HIGH_FAN_IN_THRESHOLD else 0.0,
        description="Many client queries",
    ),
    Signal(
        name="24x7_activity",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Available around the clock",
    ),
    Signal(
        name="small_packets",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet < 500 else 0.0,
        description="Small DNS query/response packets",
    ),
]

# ============================================================================
# DHCP Server Signals
# ============================================================================

DHCP_SERVER_SIGNALS = [
    Signal(
        name="dhcp_port_listener",
        weight=0.40,
        evaluator=lambda f: _has_ports_from_set(f, DHCP_SERVER_PORTS),
        description="Listening on DHCP server port 67",
    ),
    Signal(
        name="udp_only",
        weight=0.25,
        evaluator=lambda f: _is_udp_dominant(f, 0.95),
        description="UDP-only traffic (DHCP is UDP)",
    ),
    Signal(
        name="broadcast_pattern",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_out_count > f.fan_in_count else 0.5,
        description="Broadcast-like response pattern",
    ),
    Signal(
        name="low_bytes_per_flow",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet < 1000 else 0.0,
        description="Small DHCP lease packets",
    ),
]

# ============================================================================
# NTP Server Signals
# ============================================================================

NTP_SERVER_SIGNALS = [
    Signal(
        name="ntp_port_listener",
        weight=0.40,
        evaluator=lambda f: _has_ports_from_set(f, NTP_PORTS),
        description="Listening on NTP port 123",
    ),
    Signal(
        name="udp_only",
        weight=0.25,
        evaluator=lambda f: _is_udp_dominant(f, 0.95),
        description="UDP-only traffic (NTP is UDP)",
    ),
    Signal(
        name="symmetric_tiny_packets",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet < 100 else 0.0,
        description="Very small NTP packets",
    ),
    Signal(
        name="24x7_activity",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Time sync available 24/7",
    ),
]

# ============================================================================
# Directory Service Signals (LDAP/AD/Kerberos/RADIUS)
# ============================================================================

DIRECTORY_SERVICE_SIGNALS = [
    Signal(
        name="directory_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, DIRECTORY_PORTS),
        description="Listening on LDAP/Kerberos/RADIUS ports",
    ),
    Signal(
        name="high_workstation_fan_in",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > HIGH_FAN_IN_THRESHOLD else 0.0,
        description="Many client authentication requests",
    ),
    Signal(
        name="24x7_activity",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Auth service available 24/7",
    ),
    Signal(
        name="persistent_connections",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.fan_in_ratio and f.fan_in_ratio > 0.6 else 0.0,
        description="Primarily receives connections",
    ),
    Signal(
        name="tcp_dominant",
        weight=0.10,
        evaluator=lambda f: _is_tcp_dominant(f),
        description="LDAP is primarily TCP",
    ),
]

# ============================================================================
# Mail Server Signals
# ============================================================================

MAIL_SERVER_SIGNALS = [
    Signal(
        name="mail_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, MAIL_PORTS),
        description="Listening on SMTP/IMAP/POP3 ports",
    ),
    Signal(
        name="bidirectional_traffic",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > 5 and f.fan_out_count > 5 else 0.0,
        description="Both receives and sends mail",
    ),
    Signal(
        name="business_hours_spike",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.business_hours_ratio and f.business_hours_ratio > 0.5 else 0.0,
        description="Higher activity during business hours",
    ),
    Signal(
        name="variable_message_size",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet > 1000 else 0.0,
        description="Variable message sizes (attachments)",
    ),
    Signal(
        name="tcp_dominant",
        weight=0.10,
        evaluator=lambda f: _is_tcp_dominant(f),
        description="Mail protocols are TCP",
    ),
]

# ============================================================================
# VoIP Server Signals
# ============================================================================

VOIP_SERVER_SIGNALS = [
    Signal(
        name="voip_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, VOIP_PORTS),
        description="Listening on SIP/RTP ports",
    ),
    Signal(
        name="high_udp_ratio",
        weight=0.25,
        evaluator=lambda f: _is_udp_dominant(f, 0.5),
        description="High UDP ratio (RTP streams)",
    ),
    Signal(
        name="bidirectional_streams",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_in_count > 0 and f.fan_out_count > 0 else 0.0,
        description="Bidirectional RTP streams",
    ),
    Signal(
        name="constant_traffic",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > 12 else 0.0,
        description="Consistent presence for calls",
    ),
    Signal(
        name="business_hours_bias",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.business_hours_ratio and f.business_hours_ratio > 0.4 else 0.0,
        description="More calls during business hours",
    ),
]

# ============================================================================
# VPN Gateway Signals
# ============================================================================

VPN_GATEWAY_SIGNALS = [
    Signal(
        name="vpn_port_listener",
        weight=0.30,
        evaluator=lambda f: _has_ports_from_set(f, VPN_PORTS),
        description="Listening on VPN ports (IKE/OpenVPN)",
    ),
    Signal(
        name="high_fan_in",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > HIGH_FAN_IN_THRESHOLD else 0.0,
        description="Many remote clients connecting",
    ),
    Signal(
        name="udp_dominant",
        weight=0.20,
        evaluator=lambda f: _is_udp_dominant(f, 0.5),
        description="VPN tunnels often use UDP",
    ),
    Signal(
        name="high_bytes_per_flow",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet > 5000 else 0.0,
        description="High throughput tunnel traffic",
    ),
    Signal(
        name="symmetric_traffic",
        weight=0.10,
        evaluator=lambda f: _compute_traffic_symmetry(f),
        description="Bidirectional tunnel traffic",
    ),
]

# ============================================================================
# Proxy Server Signals
# ============================================================================

PROXY_SERVER_SIGNALS = [
    Signal(
        name="proxy_port_listener",
        weight=0.30,
        evaluator=lambda f: _has_ports_from_set(f, PROXY_PORTS),
        description="Listening on proxy ports (3128/8080)",
    ),
    Signal(
        name="symmetric_traffic",
        weight=0.25,
        evaluator=lambda f: _compute_traffic_symmetry(f),
        description="Similar in/out traffic (proxying)",
    ),
    Signal(
        name="high_workstation_fan_in",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.fan_in_count > HIGH_FAN_IN_THRESHOLD else 0.0,
        description="Many client connections",
    ),
    Signal(
        name="web_destinations",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.unique_dst_ports > 10 else 0.0,
        description="Connects to many web destinations",
    ),
    Signal(
        name="tcp_dominant",
        weight=0.10,
        evaluator=lambda f: _is_tcp_dominant(f),
        description="HTTP proxy is TCP",
    ),
]

# ============================================================================
# Log Collector Signals
# ============================================================================

LOG_COLLECTOR_SIGNALS = [
    Signal(
        name="log_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, LOG_COLLECTOR_PORTS),
        description="Listening on syslog/NetFlow ports",
    ),
    Signal(
        name="very_high_inbound_diversity",
        weight=0.25,
        evaluator=lambda f: _compute_inbound_diversity(f),
        description="Receives from many sources",
    ),
    Signal(
        name="asymmetric_inbound",
        weight=0.20,
        evaluator=lambda f: _is_asymmetric_inbound(f, 0.7),
        description="Mostly receives, minimal outbound",
    ),
    Signal(
        name="24x7_activity",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Log collection is 24/7",
    ),
    Signal(
        name="udp_common",
        weight=0.10,
        evaluator=lambda f: _is_udp_dominant(f, 0.3),
        description="Syslog often uses UDP",
    ),
]

# ============================================================================
# Remote Access Signals (RDP/VNC/VDI)
# ============================================================================

REMOTE_ACCESS_SIGNALS = [
    Signal(
        name="remote_access_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, REMOTE_ACCESS_PORTS),
        description="Listening on RDP/VNC ports",
    ),
    Signal(
        name="interactive_sessions",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > 0 and f.fan_in_count < 20 else 0.0,
        description="Moderate number of remote sessions",
    ),
    Signal(
        name="business_hours_bias",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.business_hours_ratio and f.business_hours_ratio > 0.5 else 0.0,
        description="Remote access during work hours",
    ),
    Signal(
        name="tcp_dominant",
        weight=0.10,
        evaluator=lambda f: _is_tcp_dominant(f),
        description="RDP/VNC are TCP protocols",
    ),
    Signal(
        name="moderate_bytes",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and 500 < f.avg_bytes_per_packet < 10000 else 0.0,
        description="Screen sharing traffic pattern",
    ),
]

# ============================================================================
# Printer Signals
# ============================================================================

PRINTER_SIGNALS = [
    Signal(
        name="printer_port_listener",
        weight=0.40,
        evaluator=lambda f: _has_ports_from_set(f, PRINTER_PORTS),
        description="Listening on printer ports (9100/631)",
    ),
    Signal(
        name="low_traffic",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.total_flows < 500 else 0.0,
        description="Low overall traffic volume",
    ),
    Signal(
        name="bursty_pattern",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.traffic_variance and f.traffic_variance > 0.5 else 0.5,
        description="Bursty print job traffic",
    ),
    Signal(
        name="business_hours",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.business_hours_ratio and f.business_hours_ratio > 0.6 else 0.0,
        description="Printing during work hours",
    ),
    Signal(
        name="minimal_outbound",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.fan_out_count < 5 else 0.0,
        description="Printers rarely initiate connections",
    ),
]

# ============================================================================
# IoT Device Signals
# ============================================================================

IOT_DEVICE_SIGNALS = [
    Signal(
        name="iot_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, IOT_PORTS),
        description="Listening on MQTT/CoAP ports",
    ),
    Signal(
        name="heartbeat_pattern",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.traffic_variance and f.traffic_variance < 0.3 else 0.0,
        description="Very predictable traffic timing",
    ),
    Signal(
        name="tiny_packets",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet < 200 else 0.0,
        description="Small sensor/telemetry packets",
    ),
    Signal(
        name="minimal_ports",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.unique_dst_ports < 5 else 0.0,
        description="Connects to very few destinations",
    ),
    Signal(
        name="24x7_activity",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > 20 else 0.0,
        description="IoT devices are always on",
    ),
]

# ============================================================================
# IP Camera Signals
# ============================================================================

IP_CAMERA_SIGNALS = [
    Signal(
        name="camera_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, CAMERA_PORTS),
        description="Listening on RTSP port 554",
    ),
    Signal(
        name="constant_outbound_stream",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.outbound_bytes > f.inbound_bytes * 5 else 0.0,
        description="High outbound video stream",
    ),
    Signal(
        name="high_bandwidth",
        weight=0.20,
        evaluator=lambda f: 1.0 if f.avg_bytes_per_packet and f.avg_bytes_per_packet > 1000 else 0.0,
        description="Video-sized packet payloads",
    ),
    Signal(
        name="24x7_activity",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > 20 else 0.0,
        description="Cameras stream continuously",
    ),
    Signal(
        name="few_destinations",
        weight=0.10,
        evaluator=lambda f: 1.0 if f.fan_out_count < 5 else 0.0,
        description="Streams to NVR only",
    ),
]

# ============================================================================
# Message Queue Signals
# ============================================================================

MESSAGE_QUEUE_SIGNALS = [
    Signal(
        name="mq_port_listener",
        weight=0.35,
        evaluator=lambda f: _has_ports_from_set(f, MESSAGE_QUEUE_PORTS),
        description="Listening on RabbitMQ/Kafka ports",
    ),
    Signal(
        name="balanced_fan_in_out",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_in_count > 5 and f.fan_out_count > 5 else 0.0,
        description="Both producers and consumers",
    ),
    Signal(
        name="persistent_connections",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.total_flows > 1000 else 0.0,
        description="High connection count (pub/sub)",
    ),
    Signal(
        name="24x7_activity",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Message queues run 24/7",
    ),
    Signal(
        name="tcp_dominant",
        weight=0.10,
        evaluator=lambda f: _is_tcp_dominant(f),
        description="AMQP/Kafka are TCP",
    ),
]

# ============================================================================
# Monitoring Server Signals
# ============================================================================

MONITORING_SERVER_SIGNALS = [
    Signal(
        name="monitoring_port_listener",
        weight=0.30,
        evaluator=lambda f: _has_ports_from_set(f, MONITORING_PORTS),
        description="Listening on Prometheus/Grafana ports",
    ),
    Signal(
        name="high_fan_out",
        weight=0.25,
        evaluator=lambda f: 1.0 if f.fan_out_count > HIGH_FAN_OUT_THRESHOLD else 0.0,
        description="Scrapes many targets",
    ),
    Signal(
        name="web_ui_ports",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.has_web_ports or 3000 in (f.persistent_listener_ports or []) else 0.0,
        description="Web UI for dashboards",
    ),
    Signal(
        name="24x7_activity",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.active_hours_count and f.active_hours_count > HIGH_ACTIVE_HOURS_THRESHOLD else 0.0,
        description="Monitoring is 24/7",
    ),
    Signal(
        name="time_series_pattern",
        weight=0.15,
        evaluator=lambda f: 1.0 if f.traffic_variance and f.traffic_variance < 0.5 else 0.5,
        description="Regular scraping intervals",
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


def _is_udp_dominant(features: BehavioralFeatures, threshold: float = 0.6) -> float:
    """Check if UDP is the dominant protocol."""
    protocol_dist = features.protocol_distribution or {}
    total_flows = sum(protocol_dist.values())

    if total_flows == 0:
        return 0.0

    udp_flows = protocol_dist.get(PROTOCOL_UDP, 0)
    udp_ratio = udp_flows / total_flows

    return 1.0 if udp_ratio > threshold else udp_ratio / threshold


def _has_ports_from_set(features: BehavioralFeatures, port_set: set[int]) -> float:
    """Check if any listener ports match a given set."""
    listener_ports = features.persistent_listener_ports or []
    return 1.0 if any(p in port_set for p in listener_ports) else 0.0


def _compute_inbound_diversity(features: BehavioralFeatures) -> float:
    """Compute diversity of inbound connections (for log collectors, etc.)."""
    if features.fan_in_count > 50:
        return 1.0
    elif features.fan_in_count > 20:
        return 0.8
    elif features.fan_in_count > 10:
        return 0.5
    return 0.0


def _is_asymmetric_inbound(features: BehavioralFeatures, threshold: float = 0.8) -> float:
    """Check if traffic is heavily inbound-biased."""
    if features.fan_in_ratio and features.fan_in_ratio > threshold:
        return 1.0
    return 0.0


# ============================================================================
# Signal Registry
# ============================================================================

ASSET_TYPE_SIGNALS: dict[ClassifiableAssetType, list[Signal]] = {
    # Compute
    ClassifiableAssetType.SERVER: SERVER_SIGNALS,
    ClassifiableAssetType.WORKSTATION: WORKSTATION_SIGNALS,
    ClassifiableAssetType.VIRTUAL_MACHINE: VIRTUAL_MACHINE_SIGNALS,
    ClassifiableAssetType.CONTAINER: CONTAINER_SIGNALS,
    ClassifiableAssetType.CLOUD_SERVICE: CLOUD_SERVICE_SIGNALS,
    # Data
    ClassifiableAssetType.DATABASE: DATABASE_SIGNALS,
    ClassifiableAssetType.STORAGE: STORAGE_SIGNALS,
    # Network
    ClassifiableAssetType.LOAD_BALANCER: LOAD_BALANCER_SIGNALS,
    ClassifiableAssetType.NETWORK_DEVICE: NETWORK_DEVICE_SIGNALS,
    # Network Services
    ClassifiableAssetType.DNS_SERVER: DNS_SERVER_SIGNALS,
    ClassifiableAssetType.DHCP_SERVER: DHCP_SERVER_SIGNALS,
    ClassifiableAssetType.NTP_SERVER: NTP_SERVER_SIGNALS,
    ClassifiableAssetType.DIRECTORY_SERVICE: DIRECTORY_SERVICE_SIGNALS,
    # Communication
    ClassifiableAssetType.MAIL_SERVER: MAIL_SERVER_SIGNALS,
    ClassifiableAssetType.VOIP_SERVER: VOIP_SERVER_SIGNALS,
    # Security & Access
    ClassifiableAssetType.VPN_GATEWAY: VPN_GATEWAY_SIGNALS,
    ClassifiableAssetType.PROXY_SERVER: PROXY_SERVER_SIGNALS,
    ClassifiableAssetType.LOG_COLLECTOR: LOG_COLLECTOR_SIGNALS,
    ClassifiableAssetType.REMOTE_ACCESS: REMOTE_ACCESS_SIGNALS,
    # Endpoints
    ClassifiableAssetType.PRINTER: PRINTER_SIGNALS,
    ClassifiableAssetType.IOT_DEVICE: IOT_DEVICE_SIGNALS,
    ClassifiableAssetType.IP_CAMERA: IP_CAMERA_SIGNALS,
    # Application Infrastructure
    ClassifiableAssetType.MESSAGE_QUEUE: MESSAGE_QUEUE_SIGNALS,
    ClassifiableAssetType.MONITORING_SERVER: MONITORING_SERVER_SIGNALS,
    # Default
    ClassifiableAssetType.UNKNOWN: UNKNOWN_SIGNALS,
}


def get_signals_for_type(asset_type: ClassifiableAssetType) -> list[Signal]:
    """Get the heuristic signals for an asset type."""
    return ASSET_TYPE_SIGNALS.get(asset_type, [])
