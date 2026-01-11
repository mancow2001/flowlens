"""Synthetic data generator for ML classification.

Generates realistic BehavioralFeatures for each asset type based on
characteristic traffic patterns. Used to build the shipped model.

This improved generator includes:
- Sub-type variants (e.g., mysql vs mongodb vs redis)
- Realistic distributions (log-normal, beta, Pareto)
- Correlated features that vary together
- Edge cases (idle, burst, hybrid patterns)
- Workload modes (development, production, batch)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar

import numpy as np

from flowlens.classification.constants import (
    CAMERA_PORTS,
    DATABASE_PORTS,
    DHCP_SERVER_PORTS,
    DIRECTORY_PORTS,
    DNS_PORTS,
    IOT_PORTS,
    LOAD_BALANCER_PORTS,
    LOG_COLLECTOR_PORTS,
    MAIL_PORTS,
    MESSAGE_QUEUE_PORTS,
    MONITORING_PORTS,
    NETWORK_DEVICE_PORTS,
    NTP_PORTS,
    PRINTER_PORTS,
    PROXY_PORTS,
    REMOTE_ACCESS_PORTS,
    STORAGE_PORTS,
    VOIP_PORTS,
    VPN_PORTS,
    WEB_PORTS,
)
from flowlens.classification.feature_extractor import BehavioralFeatures
from flowlens.classification.ml.dataset import DatasetBuilder, TrainingDataset
from flowlens.classification.ml.feature_transformer import FeatureTransformer
from flowlens.common.logging import get_logger

logger = get_logger(__name__)


class WorkloadMode(Enum):
    """Different workload patterns that affect traffic characteristics."""

    IDLE = "idle"  # Minimal activity (standby, maintenance)
    LIGHT = "light"  # Development, testing, low-traffic
    NORMAL = "normal"  # Typical production workload
    HEAVY = "heavy"  # High-traffic production
    BURST = "burst"  # Batch processing, scheduled jobs


@dataclass
class SubTypeProfile:
    """Profile for a specific sub-type of an asset.

    Each sub-type has characteristic ports, traffic patterns, and
    behavior that distinguishes it from other sub-types.
    """

    name: str
    weight: float = 1.0  # Sampling weight (higher = more common)

    # Characteristic ports
    primary_ports: list[int] = field(default_factory=list)
    secondary_ports: list[int] = field(default_factory=list)

    # Traffic shape parameters (for log-normal distribution)
    # (mu, sigma) for log-normal, higher sigma = more variance
    fan_in_params: tuple[float, float] = (2.0, 1.0)
    fan_out_params: tuple[float, float] = (2.0, 1.0)
    inbound_flow_params: tuple[float, float] = (6.0, 1.5)
    outbound_flow_params: tuple[float, float] = (6.0, 1.5)

    # Bytes per flow (log-normal)
    bytes_per_flow_params: tuple[float, float] = (8.0, 1.5)

    # Directionality bias (0 = all outbound, 1 = all inbound)
    inbound_bias: float = 0.5

    # Temporal patterns
    active_hours_mean: float = 18.0
    active_hours_std: float = 4.0
    business_hours_bias: float = 0.5  # 0 = off-hours, 1 = business hours

    # Protocol preferences
    tcp_preference: float = 0.85
    udp_preference: float = 0.10

    # Stability (lower = more bursty traffic)
    stability: float = 0.5


@dataclass
class FeatureProfile:
    """Profile defining characteristic ranges for an asset type.

    All ranges are (min, max) tuples. Values are sampled uniformly
    within these ranges with optional Gaussian noise.
    """

    # Traffic directionality
    fan_in_range: tuple[int, int] = (0, 10)
    fan_out_range: tuple[int, int] = (0, 10)
    inbound_flows_range: tuple[int, int] = (100, 1000)
    outbound_flows_range: tuple[int, int] = (100, 1000)

    # Byte volumes (relative to flows)
    bytes_per_flow_range: tuple[int, int] = (1000, 10000)

    # Port behavior
    listener_ports: list[int] = field(default_factory=list)
    unique_dst_ports_range: tuple[int, int] = (5, 20)

    # Temporal patterns
    active_hours_range: tuple[int, int] = (12, 24)
    business_hours_ratio_range: tuple[float, float] = (0.4, 0.6)

    # Protocol distribution (TCP %, UDP %, rest is other)
    tcp_ratio_range: tuple[float, float] = (0.7, 0.95)
    udp_ratio_range: tuple[float, float] = (0.02, 0.2)


class SyntheticDataGenerator:
    """Generates synthetic BehavioralFeatures for building the shipped model.

    This improved generator creates more realistic data by:
    1. Using sub-type variants (e.g., MySQL vs MongoDB vs Redis)
    2. Applying realistic distributions (log-normal, beta)
    3. Modeling correlations between features
    4. Including edge cases and workload variations
    """

    # Sub-type definitions for each asset type
    SUBTYPES: ClassVar[dict[str, list[SubTypeProfile]]] = {
        "server": [
            SubTypeProfile(
                name="web_api_server",
                weight=3.0,
                primary_ports=[80, 443, 8080],
                secondary_ports=[22, 8443],
                fan_in_params=(3.5, 0.8),  # Many clients
                fan_out_params=(1.5, 0.6),  # Few backends
                inbound_flow_params=(7.5, 1.2),
                outbound_flow_params=(5.5, 1.0),
                bytes_per_flow_params=(7.5, 1.0),
                inbound_bias=0.75,
                active_hours_mean=22.0,
                business_hours_bias=0.4,
                tcp_preference=0.95,
                stability=0.7,
            ),
            SubTypeProfile(
                name="static_file_server",
                weight=1.5,
                primary_ports=[80, 443],
                secondary_ports=[22],
                fan_in_params=(4.0, 1.0),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(6.0, 1.5),
                outbound_flow_params=(6.5, 1.5),  # Responses are larger
                bytes_per_flow_params=(10.0, 1.5),  # Large files
                inbound_bias=0.4,  # More outbound (serving files)
                active_hours_mean=20.0,
                business_hours_bias=0.45,
                tcp_preference=0.98,
                stability=0.8,
            ),
            SubTypeProfile(
                name="ssh_bastion",
                weight=1.0,
                primary_ports=[22],
                secondary_ports=[2222],
                fan_in_params=(2.0, 0.8),
                fan_out_params=(2.5, 0.8),
                inbound_flow_params=(4.0, 1.0),
                outbound_flow_params=(4.0, 1.0),
                bytes_per_flow_params=(6.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=12.0,
                business_hours_bias=0.8,
                tcp_preference=0.99,
                stability=0.3,  # Bursty sessions
            ),
            SubTypeProfile(
                name="mail_server",
                weight=0.8,
                primary_ports=[25, 465, 587, 993, 143],
                secondary_ports=[22, 110],
                fan_in_params=(3.0, 1.0),
                fan_out_params=(2.5, 0.8),
                inbound_flow_params=(6.0, 1.2),
                outbound_flow_params=(5.5, 1.2),
                bytes_per_flow_params=(8.0, 2.0),  # Attachments vary
                inbound_bias=0.55,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.6,
            ),
            SubTypeProfile(
                name="game_server",
                weight=0.5,
                primary_ports=[27015, 7777, 25565],
                secondary_ports=[22],
                fan_in_params=(3.0, 1.2),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(8.0, 1.0),
                outbound_flow_params=(8.0, 1.0),  # Real-time bidirectional
                bytes_per_flow_params=(6.0, 0.8),  # Small frequent packets
                inbound_bias=0.5,
                active_hours_mean=18.0,
                business_hours_bias=0.3,  # More off-hours
                tcp_preference=0.4,  # Often UDP
                udp_preference=0.55,
                stability=0.5,
            ),
        ],
        "workstation": [
            SubTypeProfile(
                name="developer_workstation",
                weight=2.0,
                primary_ports=[],
                secondary_ports=[22, 3000, 8080],  # Local dev servers
                fan_in_params=(0.5, 0.5),
                fan_out_params=(4.0, 0.8),  # Many outbound connections
                inbound_flow_params=(4.0, 1.5),
                outbound_flow_params=(6.5, 1.0),
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.2,
                active_hours_mean=10.0,
                business_hours_bias=0.85,
                tcp_preference=0.75,
                udp_preference=0.15,
                stability=0.3,  # Bursty
            ),
            SubTypeProfile(
                name="office_workstation",
                weight=3.0,
                primary_ports=[],
                secondary_ports=[],
                fan_in_params=(0.3, 0.3),
                fan_out_params=(3.0, 0.7),
                inbound_flow_params=(4.5, 1.2),
                outbound_flow_params=(5.5, 1.0),
                bytes_per_flow_params=(7.5, 1.2),
                inbound_bias=0.25,
                active_hours_mean=9.0,
                business_hours_bias=0.92,
                tcp_preference=0.7,
                udp_preference=0.2,
                stability=0.4,
            ),
            SubTypeProfile(
                name="power_user_workstation",
                weight=1.0,
                primary_ports=[],
                secondary_ports=[22],
                fan_in_params=(1.0, 0.6),
                fan_out_params=(4.5, 0.9),
                inbound_flow_params=(5.5, 1.3),
                outbound_flow_params=(7.0, 1.2),
                bytes_per_flow_params=(9.0, 1.8),  # Large downloads
                inbound_bias=0.3,
                active_hours_mean=12.0,
                business_hours_bias=0.75,
                tcp_preference=0.72,
                udp_preference=0.18,
                stability=0.35,
            ),
            SubTypeProfile(
                name="remote_workstation",
                weight=1.5,
                primary_ports=[],
                secondary_ports=[],
                fan_in_params=(0.2, 0.2),
                fan_out_params=(2.5, 0.6),
                inbound_flow_params=(5.0, 1.5),
                outbound_flow_params=(5.0, 1.5),
                bytes_per_flow_params=(8.5, 1.5),
                inbound_bias=0.45,  # VPN bidirectional
                active_hours_mean=8.0,
                business_hours_bias=0.8,
                tcp_preference=0.65,
                udp_preference=0.25,  # VPN UDP
                stability=0.5,
            ),
        ],
        "database": [
            SubTypeProfile(
                name="mysql_postgres",
                weight=3.0,
                primary_ports=[3306, 5432],
                secondary_ports=[22],
                fan_in_params=(2.5, 0.7),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(6.5, 1.0),
                outbound_flow_params=(5.0, 1.0),
                bytes_per_flow_params=(9.0, 1.5),
                inbound_bias=0.6,
                active_hours_mean=23.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                stability=0.75,
            ),
            SubTypeProfile(
                name="mongodb",
                weight=1.5,
                primary_ports=[27017, 27018, 27019],
                secondary_ports=[22],
                fan_in_params=(2.0, 0.8),
                fan_out_params=(1.5, 0.6),  # Replica set comms
                inbound_flow_params=(6.0, 1.2),
                outbound_flow_params=(5.5, 1.2),
                bytes_per_flow_params=(9.5, 1.8),  # Document sizes vary
                inbound_bias=0.55,
                active_hours_mean=24.0,
                business_hours_bias=0.48,
                tcp_preference=0.99,
                stability=0.7,
            ),
            SubTypeProfile(
                name="redis_cache",
                weight=2.0,
                primary_ports=[6379, 6380],
                secondary_ports=[16379],  # Cluster bus
                fan_in_params=(3.5, 0.8),  # Many clients
                fan_out_params=(0.5, 0.4),
                inbound_flow_params=(8.0, 0.8),  # High volume
                outbound_flow_params=(8.0, 0.8),
                bytes_per_flow_params=(6.0, 1.0),  # Small values
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                stability=0.85,  # Very stable
            ),
            SubTypeProfile(
                name="elasticsearch",
                weight=1.0,
                primary_ports=[9200, 9300],
                secondary_ports=[22],
                fan_in_params=(2.0, 0.7),
                fan_out_params=(2.0, 0.7),  # Cluster coordination
                inbound_flow_params=(6.5, 1.3),
                outbound_flow_params=(6.5, 1.3),
                bytes_per_flow_params=(10.0, 1.5),  # Large docs
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.65,
            ),
            SubTypeProfile(
                name="mssql_oracle",
                weight=1.0,
                primary_ports=[1433, 1521],
                secondary_ports=[22],
                fan_in_params=(2.0, 0.6),
                fan_out_params=(0.3, 0.2),
                inbound_flow_params=(6.0, 1.0),
                outbound_flow_params=(5.5, 1.0),
                bytes_per_flow_params=(9.5, 1.3),
                inbound_bias=0.65,
                active_hours_mean=22.0,
                business_hours_bias=0.6,
                tcp_preference=0.99,
                stability=0.8,
            ),
            SubTypeProfile(
                name="cassandra",
                weight=0.8,
                primary_ports=[9042, 7000, 7001],
                secondary_ports=[7199],
                fan_in_params=(2.5, 0.8),
                fan_out_params=(2.5, 0.8),  # Peer-to-peer
                inbound_flow_params=(7.0, 1.0),
                outbound_flow_params=(7.0, 1.0),
                bytes_per_flow_params=(8.5, 1.2),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.48,
                tcp_preference=0.99,
                stability=0.72,
            ),
        ],
        "load_balancer": [
            SubTypeProfile(
                name="http_lb",
                weight=3.0,
                primary_ports=[80, 443],
                secondary_ports=[8080, 8443],
                fan_in_params=(5.0, 1.0),  # Many clients
                fan_out_params=(2.5, 0.6),  # Backend pool
                inbound_flow_params=(9.0, 1.0),
                outbound_flow_params=(9.0, 1.0),
                bytes_per_flow_params=(7.0, 1.2),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.97,
                stability=0.9,
            ),
            SubTypeProfile(
                name="tcp_lb",
                weight=1.5,
                primary_ports=[3306, 5432, 6379],
                secondary_ports=[],
                fan_in_params=(3.5, 0.8),
                fan_out_params=(1.5, 0.5),
                inbound_flow_params=(8.0, 1.2),
                outbound_flow_params=(8.0, 1.2),
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                stability=0.88,
            ),
            SubTypeProfile(
                name="api_gateway",
                weight=2.0,
                primary_ports=[443, 8443],
                secondary_ports=[80, 8080, 9090],
                fan_in_params=(4.5, 0.9),
                fan_out_params=(3.0, 0.7),  # Many microservices
                inbound_flow_params=(8.5, 1.0),
                outbound_flow_params=(8.5, 1.0),
                bytes_per_flow_params=(7.5, 1.0),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.85,
            ),
            SubTypeProfile(
                name="dns_lb",
                weight=0.5,
                primary_ports=[53],
                secondary_ports=[],
                fan_in_params=(4.0, 1.2),
                fan_out_params=(2.0, 0.8),
                inbound_flow_params=(8.5, 1.5),
                outbound_flow_params=(8.5, 1.5),
                bytes_per_flow_params=(5.5, 0.5),  # Small DNS packets
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.15,
                udp_preference=0.83,
                stability=0.92,
            ),
        ],
        "network_device": [
            SubTypeProfile(
                name="router",
                weight=2.0,
                primary_ports=[22, 23],
                secondary_ports=[161, 162],  # SNMP
                fan_in_params=(2.0, 0.8),
                fan_out_params=(2.0, 0.8),
                inbound_flow_params=(6.0, 1.5),
                outbound_flow_params=(6.0, 1.5),
                bytes_per_flow_params=(6.0, 1.0),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.4,
                udp_preference=0.35,
                stability=0.8,
            ),
            SubTypeProfile(
                name="switch",
                weight=2.0,
                primary_ports=[22],
                secondary_ports=[161, 162],
                fan_in_params=(1.5, 0.6),
                fan_out_params=(1.5, 0.6),
                inbound_flow_params=(5.0, 1.2),
                outbound_flow_params=(5.0, 1.2),
                bytes_per_flow_params=(5.5, 0.8),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.35,
                udp_preference=0.4,
                stability=0.85,
            ),
            SubTypeProfile(
                name="firewall",
                weight=1.5,
                primary_ports=[22, 443],
                secondary_ports=[161, 514],  # SNMP, syslog
                fan_in_params=(2.5, 1.0),
                fan_out_params=(2.0, 0.8),
                inbound_flow_params=(7.0, 1.5),
                outbound_flow_params=(6.5, 1.5),
                bytes_per_flow_params=(5.0, 1.2),
                inbound_bias=0.52,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.45,
                udp_preference=0.3,
                stability=0.75,
            ),
            SubTypeProfile(
                name="wireless_controller",
                weight=0.8,
                primary_ports=[22, 443, 5246, 5247],
                secondary_ports=[161],
                fan_in_params=(3.0, 1.0),
                fan_out_params=(3.0, 1.0),
                inbound_flow_params=(6.5, 1.2),
                outbound_flow_params=(6.5, 1.2),
                bytes_per_flow_params=(5.5, 1.0),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.5,
                udp_preference=0.35,
                stability=0.78,
            ),
            SubTypeProfile(
                name="vpn_concentrator",
                weight=1.0,
                primary_ports=[443, 500, 4500],
                secondary_ports=[22, 1194],
                fan_in_params=(3.5, 1.0),
                fan_out_params=(1.0, 0.5),
                inbound_flow_params=(7.0, 1.3),
                outbound_flow_params=(7.0, 1.3),
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.6,
                tcp_preference=0.3,
                udp_preference=0.6,
                stability=0.7,
            ),
        ],
        "storage": [
            SubTypeProfile(
                name="nfs_server",
                weight=2.0,
                primary_ports=[2049, 111],
                secondary_ports=[20048],
                fan_in_params=(2.5, 0.8),
                fan_out_params=(0.3, 0.2),
                inbound_flow_params=(6.0, 1.2),
                outbound_flow_params=(6.5, 1.2),
                bytes_per_flow_params=(11.0, 1.5),
                inbound_bias=0.4,  # More outbound (serving files)
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.7,
                udp_preference=0.25,
                stability=0.75,
            ),
            SubTypeProfile(
                name="smb_cifs",
                weight=2.0,
                primary_ports=[445, 139],
                secondary_ports=[137, 138],
                fan_in_params=(3.0, 0.9),
                fan_out_params=(0.2, 0.2),
                inbound_flow_params=(6.5, 1.0),
                outbound_flow_params=(7.0, 1.0),
                bytes_per_flow_params=(10.5, 1.8),
                inbound_bias=0.35,
                active_hours_mean=20.0,
                business_hours_bias=0.6,
                tcp_preference=0.85,
                udp_preference=0.1,
                stability=0.7,
            ),
            SubTypeProfile(
                name="iscsi_target",
                weight=1.0,
                primary_ports=[3260],
                secondary_ports=[],
                fan_in_params=(1.5, 0.5),
                fan_out_params=(0.2, 0.1),
                inbound_flow_params=(7.0, 0.8),
                outbound_flow_params=(7.5, 0.8),
                bytes_per_flow_params=(12.0, 1.0),  # Block-level
                inbound_bias=0.4,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                stability=0.9,
            ),
            SubTypeProfile(
                name="s3_minio",
                weight=1.5,
                primary_ports=[9000, 443],
                secondary_ports=[9001],
                fan_in_params=(3.0, 1.0),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(7.0, 1.2),
                outbound_flow_params=(7.5, 1.2),
                bytes_per_flow_params=(11.0, 2.0),
                inbound_bias=0.45,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.8,
            ),
            SubTypeProfile(
                name="backup_server",
                weight=1.0,
                primary_ports=[10000, 9102],
                secondary_ports=[22, 445],
                fan_in_params=(1.0, 0.5),
                fan_out_params=(3.0, 1.0),  # Pulls from many sources
                inbound_flow_params=(7.5, 1.5),
                outbound_flow_params=(5.0, 1.5),
                bytes_per_flow_params=(12.0, 1.5),
                inbound_bias=0.7,
                active_hours_mean=12.0,
                business_hours_bias=0.2,  # Off-hours backups
                tcp_preference=0.95,
                stability=0.3,  # Bursty (scheduled)
            ),
        ],
        "container": [
            SubTypeProfile(
                name="microservice",
                weight=4.0,
                primary_ports=[8080, 3000, 8000],
                secondary_ports=[9090, 8081],
                fan_in_params=(2.5, 0.9),
                fan_out_params=(2.5, 0.9),
                inbound_flow_params=(6.5, 1.2),
                outbound_flow_params=(6.5, 1.2),
                bytes_per_flow_params=(7.0, 1.2),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.55,
                tcp_preference=0.95,
                stability=0.65,
            ),
            SubTypeProfile(
                name="worker_container",
                weight=2.0,
                primary_ports=[],
                secondary_ports=[8080],
                fan_in_params=(0.5, 0.4),
                fan_out_params=(3.0, 1.0),  # Pulls work
                inbound_flow_params=(5.0, 1.5),
                outbound_flow_params=(6.0, 1.5),
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.35,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.92,
                stability=0.5,
            ),
            SubTypeProfile(
                name="sidecar_proxy",
                weight=2.0,
                primary_ports=[15001, 15006],
                secondary_ports=[15000, 15090],
                fan_in_params=(3.0, 0.8),
                fan_out_params=(3.0, 0.8),
                inbound_flow_params=(7.5, 1.0),
                outbound_flow_params=(7.5, 1.0),
                bytes_per_flow_params=(7.0, 1.0),
                inbound_bias=0.5,
                active_hours_mean=22.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.75,
            ),
            SubTypeProfile(
                name="init_container",
                weight=0.5,
                primary_ports=[],
                secondary_ports=[],
                fan_in_params=(0.2, 0.2),
                fan_out_params=(1.5, 0.8),
                inbound_flow_params=(3.0, 1.5),
                outbound_flow_params=(4.0, 1.5),
                bytes_per_flow_params=(7.0, 2.0),
                inbound_bias=0.2,
                active_hours_mean=4.0,
                business_hours_bias=0.5,
                tcp_preference=0.9,
                stability=0.1,  # Very short-lived
            ),
            SubTypeProfile(
                name="database_container",
                weight=1.5,
                primary_ports=[5432, 3306, 27017],
                secondary_ports=[],
                fan_in_params=(2.0, 0.7),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(6.0, 1.0),
                outbound_flow_params=(5.5, 1.0),
                bytes_per_flow_params=(9.0, 1.5),
                inbound_bias=0.6,
                active_hours_mean=22.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                stability=0.7,
            ),
        ],
        "cloud_service": [
            SubTypeProfile(
                name="saas_endpoint",
                weight=3.0,
                primary_ports=[443],
                secondary_ports=[80],
                fan_in_params=(5.5, 1.2),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(9.5, 1.0),
                outbound_flow_params=(8.0, 1.0),
                bytes_per_flow_params=(7.0, 1.2),
                inbound_bias=0.6,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.9,
            ),
            SubTypeProfile(
                name="cdn_edge",
                weight=2.0,
                primary_ports=[443, 80],
                secondary_ports=[],
                fan_in_params=(6.0, 1.0),
                fan_out_params=(0.3, 0.2),
                inbound_flow_params=(9.0, 0.8),
                outbound_flow_params=(9.5, 0.8),
                bytes_per_flow_params=(9.0, 1.5),
                inbound_bias=0.4,  # Serves content
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.95,
                stability=0.92,
            ),
            SubTypeProfile(
                name="cloud_database",
                weight=1.5,
                primary_ports=[5432, 3306, 443],
                secondary_ports=[],
                fan_in_params=(3.0, 0.8),
                fan_out_params=(0.2, 0.15),
                inbound_flow_params=(7.0, 1.0),
                outbound_flow_params=(6.5, 1.0),
                bytes_per_flow_params=(9.0, 1.3),
                inbound_bias=0.55,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                stability=0.88,
            ),
            SubTypeProfile(
                name="serverless_function",
                weight=1.5,
                primary_ports=[443],
                secondary_ports=[],
                fan_in_params=(4.0, 1.5),
                fan_out_params=(1.5, 1.0),
                inbound_flow_params=(6.0, 2.0),  # Highly variable
                outbound_flow_params=(5.0, 2.0),
                bytes_per_flow_params=(6.5, 1.5),
                inbound_bias=0.55,
                active_hours_mean=18.0,
                business_hours_bias=0.6,
                tcp_preference=0.97,
                stability=0.3,  # Very bursty
            ),
            SubTypeProfile(
                name="message_queue",
                weight=1.0,
                primary_ports=[5672, 9092, 6379],
                secondary_ports=[15672, 9093],
                fan_in_params=(3.5, 1.0),
                fan_out_params=(3.5, 1.0),
                inbound_flow_params=(8.0, 1.2),
                outbound_flow_params=(8.0, 1.2),
                bytes_per_flow_params=(7.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                stability=0.75,
            ),
        ],
        "virtual_machine": [
            SubTypeProfile(
                name="linux_server_vm",
                weight=3.0,
                primary_ports=[22, 80, 443],
                secondary_ports=[8080],
                fan_in_params=(2.5, 1.0),
                fan_out_params=(2.0, 0.9),
                inbound_flow_params=(6.0, 1.3),
                outbound_flow_params=(5.5, 1.3),
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.55,
                active_hours_mean=20.0,
                business_hours_bias=0.5,
                tcp_preference=0.88,
                stability=0.6,
            ),
            SubTypeProfile(
                name="windows_server_vm",
                weight=2.0,
                primary_ports=[3389, 445, 135],
                secondary_ports=[22, 5985],
                fan_in_params=(2.0, 0.8),
                fan_out_params=(1.5, 0.7),
                inbound_flow_params=(5.5, 1.2),
                outbound_flow_params=(5.0, 1.2),
                bytes_per_flow_params=(8.5, 1.3),
                inbound_bias=0.55,
                active_hours_mean=18.0,
                business_hours_bias=0.6,
                tcp_preference=0.9,
                stability=0.65,
            ),
            SubTypeProfile(
                name="development_vm",
                weight=1.5,
                primary_ports=[22],
                secondary_ports=[3000, 8080, 5000],
                fan_in_params=(1.0, 0.6),
                fan_out_params=(3.0, 1.0),
                inbound_flow_params=(5.0, 1.5),
                outbound_flow_params=(6.0, 1.5),
                bytes_per_flow_params=(8.0, 1.8),
                inbound_bias=0.35,
                active_hours_mean=10.0,
                business_hours_bias=0.85,
                tcp_preference=0.82,
                stability=0.4,
            ),
            SubTypeProfile(
                name="ci_cd_runner",
                weight=1.0,
                primary_ports=[22],
                secondary_ports=[],
                fan_in_params=(0.5, 0.4),
                fan_out_params=(4.0, 1.2),  # Pulls artifacts, pushes
                inbound_flow_params=(6.0, 1.8),
                outbound_flow_params=(7.0, 1.8),
                bytes_per_flow_params=(9.5, 2.0),
                inbound_bias=0.4,
                active_hours_mean=14.0,
                business_hours_bias=0.7,
                tcp_preference=0.92,
                stability=0.25,  # Very bursty
            ),
            SubTypeProfile(
                name="monitoring_vm",
                weight=1.0,
                primary_ports=[9090, 3000, 8086],
                secondary_ports=[22, 9100],
                fan_in_params=(2.0, 0.8),
                fan_out_params=(4.0, 1.0),  # Scrapes many targets
                inbound_flow_params=(6.0, 1.0),
                outbound_flow_params=(7.0, 1.0),
                bytes_per_flow_params=(6.0, 1.0),
                inbound_bias=0.4,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.95,
                stability=0.8,
            ),
        ],
        # === NEW ASSET TYPES ===
        "dns_server": [
            SubTypeProfile(
                name="primary_dns",
                weight=3.0,
                primary_ports=[53],
                secondary_ports=[953],  # RNDC control
                fan_in_params=(4.5, 1.0),  # Many clients
                fan_out_params=(1.5, 0.6),  # Few upstream DNS
                inbound_flow_params=(8.5, 1.0),
                outbound_flow_params=(8.0, 1.0),
                bytes_per_flow_params=(5.0, 0.5),  # Small DNS packets
                inbound_bias=0.55,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.15,
                udp_preference=0.83,  # DNS is mostly UDP
                stability=0.9,
            ),
            SubTypeProfile(
                name="recursive_dns",
                weight=2.0,
                primary_ports=[53],
                secondary_ports=[],
                fan_in_params=(5.0, 1.2),  # Very high fan-in
                fan_out_params=(2.0, 0.8),  # Queries upstream
                inbound_flow_params=(9.0, 1.0),
                outbound_flow_params=(8.5, 1.0),
                bytes_per_flow_params=(5.2, 0.6),
                inbound_bias=0.52,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.12,
                udp_preference=0.86,
                stability=0.92,
            ),
            SubTypeProfile(
                name="mdns_service",
                weight=0.5,
                primary_ports=[5353],
                secondary_ports=[],
                fan_in_params=(2.0, 0.8),
                fan_out_params=(2.0, 0.8),  # Multicast both ways
                inbound_flow_params=(5.0, 1.5),
                outbound_flow_params=(5.0, 1.5),
                bytes_per_flow_params=(4.5, 0.4),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.5,
                tcp_preference=0.05,
                udp_preference=0.93,
                stability=0.7,
            ),
        ],
        "dhcp_server": [
            SubTypeProfile(
                name="dhcp_primary",
                weight=3.0,
                primary_ports=[67],
                secondary_ports=[68],
                fan_in_params=(3.5, 1.0),  # Many clients
                fan_out_params=(0.5, 0.3),  # Minimal outbound
                inbound_flow_params=(6.0, 1.2),
                outbound_flow_params=(6.0, 1.2),  # Responses match requests
                bytes_per_flow_params=(5.5, 0.5),  # Small DHCP packets
                inbound_bias=0.5,  # Symmetric DORA
                active_hours_mean=24.0,
                business_hours_bias=0.55,  # Slight business hours bias
                tcp_preference=0.02,
                udp_preference=0.97,  # DHCP is UDP-only
                stability=0.85,
            ),
            SubTypeProfile(
                name="dhcp_failover",
                weight=1.0,
                primary_ports=[67, 68],
                secondary_ports=[647],  # Failover port
                fan_in_params=(3.0, 0.9),
                fan_out_params=(1.0, 0.5),  # Peer communication
                inbound_flow_params=(5.5, 1.0),
                outbound_flow_params=(5.5, 1.0),
                bytes_per_flow_params=(5.5, 0.6),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.05,
                udp_preference=0.94,
                stability=0.88,
            ),
        ],
        "ntp_server": [
            SubTypeProfile(
                name="ntp_primary",
                weight=3.0,
                primary_ports=[123],
                secondary_ports=[],
                fan_in_params=(4.0, 1.2),  # Many clients polling
                fan_out_params=(0.8, 0.4),  # Upstream stratum servers
                inbound_flow_params=(7.0, 1.0),
                outbound_flow_params=(7.0, 1.0),  # Symmetric UDP
                bytes_per_flow_params=(4.2, 0.3),  # Tiny NTP packets ~48B
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.02,
                udp_preference=0.97,  # NTP is UDP
                stability=0.95,  # Very stable, regular polling
            ),
            SubTypeProfile(
                name="ntp_stratum1",
                weight=0.5,
                primary_ports=[123],
                secondary_ports=[],
                fan_in_params=(5.0, 1.0),  # Very high fan-in
                fan_out_params=(0.2, 0.1),  # GPS/atomic source only
                inbound_flow_params=(8.0, 0.8),
                outbound_flow_params=(8.0, 0.8),
                bytes_per_flow_params=(4.2, 0.3),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.01,
                udp_preference=0.98,
                stability=0.98,
            ),
        ],
        "directory_service": [
            SubTypeProfile(
                name="active_directory",
                weight=3.0,
                primary_ports=[389, 636, 88],  # LDAP, LDAPS, Kerberos
                secondary_ports=[3268, 3269, 464],  # GC, GC-SSL, kpasswd
                fan_in_params=(4.0, 0.9),  # Many workstations
                fan_out_params=(1.5, 0.6),  # DC replication
                inbound_flow_params=(7.5, 1.0),
                outbound_flow_params=(6.5, 1.0),
                bytes_per_flow_params=(6.5, 1.2),
                inbound_bias=0.6,
                active_hours_mean=24.0,
                business_hours_bias=0.55,
                tcp_preference=0.85,
                udp_preference=0.12,  # Kerberos can be UDP
                stability=0.8,
            ),
            SubTypeProfile(
                name="ldap_server",
                weight=2.0,
                primary_ports=[389, 636],
                secondary_ports=[],
                fan_in_params=(3.5, 0.8),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(7.0, 1.0),
                outbound_flow_params=(6.0, 1.0),
                bytes_per_flow_params=(6.0, 1.0),
                inbound_bias=0.65,
                active_hours_mean=24.0,
                business_hours_bias=0.6,
                tcp_preference=0.95,
                udp_preference=0.03,
                stability=0.85,
            ),
            SubTypeProfile(
                name="radius_server",
                weight=1.5,
                primary_ports=[1812, 1813],
                secondary_ports=[],
                fan_in_params=(3.0, 1.0),  # Network devices authenticating
                fan_out_params=(1.0, 0.5),  # Backend LDAP
                inbound_flow_params=(6.5, 1.2),
                outbound_flow_params=(5.5, 1.0),
                bytes_per_flow_params=(5.5, 0.8),
                inbound_bias=0.58,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.1,
                udp_preference=0.88,  # RADIUS is UDP
                stability=0.82,
            ),
        ],
        "mail_server": [
            SubTypeProfile(
                name="smtp_server",
                weight=2.5,
                primary_ports=[25, 465, 587],
                secondary_ports=[22],
                fan_in_params=(3.5, 1.0),  # External mail + internal clients
                fan_out_params=(2.5, 0.8),  # Outbound delivery
                inbound_flow_params=(7.0, 1.2),
                outbound_flow_params=(6.5, 1.2),
                bytes_per_flow_params=(8.5, 2.0),  # Attachments vary widely
                inbound_bias=0.55,
                active_hours_mean=24.0,
                business_hours_bias=0.55,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.7,
            ),
            SubTypeProfile(
                name="imap_pop_server",
                weight=2.0,
                primary_ports=[143, 993, 110, 995],
                secondary_ports=[22],
                fan_in_params=(3.0, 0.9),  # Mail clients
                fan_out_params=(0.5, 0.3),  # Minimal outbound
                inbound_flow_params=(6.5, 1.0),
                outbound_flow_params=(7.0, 1.0),  # Serving mailboxes
                bytes_per_flow_params=(9.0, 1.8),
                inbound_bias=0.45,  # More outbound (serving)
                active_hours_mean=20.0,
                business_hours_bias=0.65,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.75,
            ),
            SubTypeProfile(
                name="full_mail_server",
                weight=1.5,
                primary_ports=[25, 143, 993, 587],
                secondary_ports=[465, 110, 995],
                fan_in_params=(3.5, 1.0),
                fan_out_params=(2.0, 0.8),
                inbound_flow_params=(7.0, 1.2),
                outbound_flow_params=(7.0, 1.2),
                bytes_per_flow_params=(8.5, 2.0),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.55,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.72,
            ),
        ],
        "voip_server": [
            SubTypeProfile(
                name="sip_server",
                weight=3.0,
                primary_ports=[5060, 5061],
                secondary_ports=[],
                fan_in_params=(3.5, 1.0),  # Phone endpoints
                fan_out_params=(2.0, 0.8),  # Trunk providers
                inbound_flow_params=(7.0, 1.2),
                outbound_flow_params=(7.0, 1.2),
                bytes_per_flow_params=(6.0, 1.0),  # Signaling is small
                inbound_bias=0.5,
                active_hours_mean=18.0,
                business_hours_bias=0.7,  # Business hours heavy
                tcp_preference=0.35,
                udp_preference=0.63,  # SIP often UDP
                stability=0.7,
            ),
            SubTypeProfile(
                name="media_server",
                weight=2.0,
                primary_ports=[5004, 5005],  # RTP/RTCP
                secondary_ports=[5060],
                fan_in_params=(2.5, 0.9),
                fan_out_params=(2.5, 0.9),  # Bidirectional media
                inbound_flow_params=(7.5, 1.0),
                outbound_flow_params=(7.5, 1.0),
                bytes_per_flow_params=(9.0, 1.2),  # Media streams
                inbound_bias=0.5,
                active_hours_mean=16.0,
                business_hours_bias=0.75,
                tcp_preference=0.1,
                udp_preference=0.88,  # RTP is UDP
                stability=0.65,
            ),
            SubTypeProfile(
                name="stun_turn_server",
                weight=1.0,
                primary_ports=[3478, 3479],
                secondary_ports=[],
                fan_in_params=(4.0, 1.2),  # WebRTC clients
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(7.0, 1.5),
                outbound_flow_params=(7.0, 1.5),
                bytes_per_flow_params=(5.5, 0.8),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.6,
                tcp_preference=0.25,
                udp_preference=0.73,
                stability=0.75,
            ),
        ],
        "vpn_gateway": [
            SubTypeProfile(
                name="ipsec_gateway",
                weight=2.5,
                primary_ports=[500, 4500],
                secondary_ports=[],
                fan_in_params=(4.0, 1.0),  # Many VPN clients
                fan_out_params=(1.0, 0.5),  # Internal resources
                inbound_flow_params=(8.0, 1.2),
                outbound_flow_params=(8.0, 1.2),
                bytes_per_flow_params=(9.0, 1.5),  # Tunnel traffic
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.6,
                tcp_preference=0.15,
                udp_preference=0.83,  # IKE/ESP is UDP
                stability=0.75,
            ),
            SubTypeProfile(
                name="ssl_vpn",
                weight=2.0,
                primary_ports=[443],
                secondary_ports=[8443],
                fan_in_params=(4.5, 1.0),
                fan_out_params=(1.5, 0.6),
                inbound_flow_params=(8.5, 1.0),
                outbound_flow_params=(8.5, 1.0),
                bytes_per_flow_params=(9.5, 1.5),
                inbound_bias=0.5,
                active_hours_mean=18.0,
                business_hours_bias=0.65,
                tcp_preference=0.95,
                udp_preference=0.03,
                stability=0.72,
            ),
            SubTypeProfile(
                name="openvpn_server",
                weight=1.5,
                primary_ports=[1194],
                secondary_ports=[443],
                fan_in_params=(3.5, 1.0),
                fan_out_params=(1.0, 0.5),
                inbound_flow_params=(7.5, 1.2),
                outbound_flow_params=(7.5, 1.2),
                bytes_per_flow_params=(9.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.6,
                tcp_preference=0.4,
                udp_preference=0.58,
                stability=0.7,
            ),
        ],
        "proxy_server": [
            SubTypeProfile(
                name="http_proxy",
                weight=3.0,
                primary_ports=[3128, 8080],
                secondary_ports=[8888],
                fan_in_params=(4.5, 1.0),  # Many workstations
                fan_out_params=(4.0, 1.0),  # Many destinations
                inbound_flow_params=(8.5, 1.0),
                outbound_flow_params=(8.5, 1.0),  # Symmetric
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=18.0,
                business_hours_bias=0.7,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.8,
            ),
            SubTypeProfile(
                name="socks_proxy",
                weight=1.5,
                primary_ports=[1080],
                secondary_ports=[],
                fan_in_params=(3.0, 1.0),
                fan_out_params=(3.5, 1.0),
                inbound_flow_params=(7.5, 1.2),
                outbound_flow_params=(7.5, 1.2),
                bytes_per_flow_params=(8.5, 1.8),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.55,
                tcp_preference=0.95,
                udp_preference=0.03,
                stability=0.75,
            ),
            SubTypeProfile(
                name="transparent_proxy",
                weight=1.0,
                primary_ports=[3128, 8080],
                secondary_ports=[],
                fan_in_params=(5.0, 1.2),  # All subnet traffic
                fan_out_params=(4.5, 1.0),
                inbound_flow_params=(9.0, 1.0),
                outbound_flow_params=(9.0, 1.0),
                bytes_per_flow_params=(7.5, 1.3),
                inbound_bias=0.5,
                active_hours_mean=20.0,
                business_hours_bias=0.6,
                tcp_preference=0.97,
                udp_preference=0.02,
                stability=0.85,
            ),
        ],
        "log_collector": [
            SubTypeProfile(
                name="syslog_server",
                weight=3.0,
                primary_ports=[514, 6514],
                secondary_ports=[],
                fan_in_params=(5.0, 1.0),  # Many sources sending logs
                fan_out_params=(0.5, 0.3),  # Minimal outbound
                inbound_flow_params=(8.0, 1.2),
                outbound_flow_params=(4.0, 1.5),
                bytes_per_flow_params=(7.0, 1.5),
                inbound_bias=0.85,  # Heavily inbound
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.4,
                udp_preference=0.58,  # Traditional syslog is UDP
                stability=0.75,
            ),
            SubTypeProfile(
                name="splunk_forwarder",
                weight=2.0,
                primary_ports=[5000, 9997],
                secondary_ports=[8089],
                fan_in_params=(4.5, 1.0),
                fan_out_params=(0.3, 0.2),  # Sends to indexer
                inbound_flow_params=(8.0, 1.0),
                outbound_flow_params=(7.5, 1.0),
                bytes_per_flow_params=(8.0, 1.5),
                inbound_bias=0.7,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.8,
            ),
            SubTypeProfile(
                name="netflow_collector",
                weight=1.5,
                primary_ports=[2055, 9995, 4739],
                secondary_ports=[],
                fan_in_params=(3.5, 0.9),  # Network devices
                fan_out_params=(0.2, 0.1),
                inbound_flow_params=(8.5, 1.0),
                outbound_flow_params=(3.0, 1.0),
                bytes_per_flow_params=(6.0, 1.0),
                inbound_bias=0.9,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.1,
                udp_preference=0.88,  # NetFlow is UDP
                stability=0.9,
            ),
            SubTypeProfile(
                name="logstash_beats",
                weight=1.0,
                primary_ports=[5044],
                secondary_ports=[9600],
                fan_in_params=(4.0, 1.0),
                fan_out_params=(0.5, 0.3),  # Elasticsearch
                inbound_flow_params=(7.5, 1.0),
                outbound_flow_params=(7.0, 1.0),
                bytes_per_flow_params=(7.5, 1.5),
                inbound_bias=0.6,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.82,
            ),
        ],
        "remote_access": [
            SubTypeProfile(
                name="rdp_server",
                weight=3.0,
                primary_ports=[3389],
                secondary_ports=[],
                fan_in_params=(2.5, 0.9),  # RDP clients
                fan_out_params=(1.5, 0.6),  # Resources accessed
                inbound_flow_params=(6.5, 1.2),
                outbound_flow_params=(7.0, 1.2),
                bytes_per_flow_params=(9.0, 1.5),  # Screen data
                inbound_bias=0.45,  # More outbound (screen)
                active_hours_mean=12.0,
                business_hours_bias=0.8,
                tcp_preference=0.98,
                udp_preference=0.01,  # RDP UDP mode
                stability=0.6,  # Session-based
            ),
            SubTypeProfile(
                name="vnc_server",
                weight=2.0,
                primary_ports=[5900],
                secondary_ports=[5901, 5902],
                fan_in_params=(1.5, 0.7),
                fan_out_params=(0.5, 0.3),
                inbound_flow_params=(5.5, 1.2),
                outbound_flow_params=(6.5, 1.2),
                bytes_per_flow_params=(8.5, 1.5),
                inbound_bias=0.4,
                active_hours_mean=10.0,
                business_hours_bias=0.75,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.55,
            ),
            SubTypeProfile(
                name="pcoip_server",
                weight=1.0,
                primary_ports=[4172],
                secondary_ports=[443],
                fan_in_params=(2.0, 0.8),
                fan_out_params=(1.0, 0.5),
                inbound_flow_params=(6.0, 1.0),
                outbound_flow_params=(7.0, 1.0),
                bytes_per_flow_params=(9.5, 1.3),
                inbound_bias=0.4,
                active_hours_mean=10.0,
                business_hours_bias=0.85,
                tcp_preference=0.6,
                udp_preference=0.38,  # PCoIP uses UDP
                stability=0.65,
            ),
        ],
        "printer": [
            SubTypeProfile(
                name="network_printer",
                weight=3.0,
                primary_ports=[9100],
                secondary_ports=[631, 515],
                fan_in_params=(2.5, 1.0),  # Print clients
                fan_out_params=(0.2, 0.1),  # Minimal outbound
                inbound_flow_params=(4.5, 1.5),  # Low volume
                outbound_flow_params=(3.0, 1.5),
                bytes_per_flow_params=(10.0, 2.0),  # Print jobs vary
                inbound_bias=0.8,  # Mostly inbound print jobs
                active_hours_mean=10.0,
                business_hours_bias=0.9,  # Business hours
                tcp_preference=0.95,
                udp_preference=0.03,
                stability=0.3,  # Very bursty
            ),
            SubTypeProfile(
                name="ipp_printer",
                weight=2.0,
                primary_ports=[631],
                secondary_ports=[9100],
                fan_in_params=(2.0, 0.9),
                fan_out_params=(0.1, 0.1),
                inbound_flow_params=(4.0, 1.5),
                outbound_flow_params=(3.5, 1.5),
                bytes_per_flow_params=(9.5, 2.0),
                inbound_bias=0.75,
                active_hours_mean=9.0,
                business_hours_bias=0.92,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.25,
            ),
            SubTypeProfile(
                name="print_server",
                weight=1.0,
                primary_ports=[515, 631, 9100],
                secondary_ports=[445],  # Windows sharing
                fan_in_params=(3.5, 1.0),  # Many clients
                fan_out_params=(1.5, 0.6),  # Physical printers
                inbound_flow_params=(5.5, 1.2),
                outbound_flow_params=(5.0, 1.2),
                bytes_per_flow_params=(10.0, 1.8),
                inbound_bias=0.6,
                active_hours_mean=12.0,
                business_hours_bias=0.85,
                tcp_preference=0.92,
                udp_preference=0.05,
                stability=0.4,
            ),
        ],
        "iot_device": [
            SubTypeProfile(
                name="mqtt_device",
                weight=3.0,
                primary_ports=[1883, 8883],
                secondary_ports=[],
                fan_in_params=(0.5, 0.3),  # Broker initiates
                fan_out_params=(1.0, 0.5),  # Publishes to broker
                inbound_flow_params=(4.5, 1.5),
                outbound_flow_params=(5.0, 1.5),
                bytes_per_flow_params=(5.0, 1.0),  # Small telemetry
                inbound_bias=0.4,  # More outbound (publishing)
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.85,  # Regular heartbeats
            ),
            SubTypeProfile(
                name="coap_device",
                weight=1.5,
                primary_ports=[5683, 5684],
                secondary_ports=[],
                fan_in_params=(0.8, 0.4),
                fan_out_params=(1.2, 0.5),
                inbound_flow_params=(4.0, 1.2),
                outbound_flow_params=(4.5, 1.2),
                bytes_per_flow_params=(4.5, 0.8),  # Very small
                inbound_bias=0.4,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.05,
                udp_preference=0.93,  # CoAP is UDP
                stability=0.82,
            ),
            SubTypeProfile(
                name="generic_iot",
                weight=1.0,
                primary_ports=[],
                secondary_ports=[80, 443, 1883],
                fan_in_params=(0.3, 0.2),
                fan_out_params=(1.5, 0.7),  # Cloud connectivity
                inbound_flow_params=(3.5, 1.5),
                outbound_flow_params=(4.0, 1.5),
                bytes_per_flow_params=(5.5, 1.2),
                inbound_bias=0.35,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.75,
                udp_preference=0.2,
                stability=0.7,
            ),
        ],
        "ip_camera": [
            SubTypeProfile(
                name="rtsp_camera",
                weight=3.0,
                primary_ports=[554],
                secondary_ports=[80, 443],
                fan_in_params=(2.0, 0.8),  # Viewers/NVR
                fan_out_params=(1.0, 0.5),  # NVR/cloud
                inbound_flow_params=(5.0, 1.2),
                outbound_flow_params=(8.0, 0.8),  # Constant streaming
                bytes_per_flow_params=(11.0, 1.0),  # High bandwidth video
                inbound_bias=0.15,  # Mostly outbound (streaming)
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.7,
                udp_preference=0.28,  # RTP over UDP
                stability=0.9,  # Constant stream
            ),
            SubTypeProfile(
                name="onvif_camera",
                weight=2.0,
                primary_ports=[80, 554],
                secondary_ports=[8080, 443],
                fan_in_params=(1.5, 0.7),
                fan_out_params=(1.2, 0.5),
                inbound_flow_params=(4.5, 1.0),
                outbound_flow_params=(7.5, 0.9),
                bytes_per_flow_params=(10.5, 1.2),
                inbound_bias=0.2,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.75,
                udp_preference=0.22,
                stability=0.88,
            ),
            SubTypeProfile(
                name="dahua_hikvision",
                weight=1.0,
                primary_ports=[37777, 554],
                secondary_ports=[80, 8000],
                fan_in_params=(1.5, 0.6),
                fan_out_params=(1.0, 0.4),
                inbound_flow_params=(4.0, 1.0),
                outbound_flow_params=(7.5, 0.8),
                bytes_per_flow_params=(11.0, 1.0),
                inbound_bias=0.18,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.72,
                udp_preference=0.25,
                stability=0.92,
            ),
        ],
        "message_queue": [
            SubTypeProfile(
                name="rabbitmq",
                weight=2.5,
                primary_ports=[5672, 5671],
                secondary_ports=[15672],  # Management
                fan_in_params=(3.5, 0.9),  # Producers
                fan_out_params=(3.5, 0.9),  # Consumers
                inbound_flow_params=(7.5, 1.0),
                outbound_flow_params=(7.5, 1.0),  # Balanced
                bytes_per_flow_params=(7.5, 1.5),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.55,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.85,
            ),
            SubTypeProfile(
                name="kafka_broker",
                weight=2.0,
                primary_ports=[9092, 9093],
                secondary_ports=[2181],  # ZooKeeper (if collocated)
                fan_in_params=(4.0, 1.0),  # Many producers
                fan_out_params=(4.0, 1.0),  # Many consumers
                inbound_flow_params=(8.5, 1.0),
                outbound_flow_params=(8.5, 1.0),
                bytes_per_flow_params=(9.0, 1.5),  # Higher throughput
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.88,
            ),
            SubTypeProfile(
                name="activemq",
                weight=1.0,
                primary_ports=[61616],
                secondary_ports=[8161],  # Web console
                fan_in_params=(3.0, 0.9),
                fan_out_params=(3.0, 0.9),
                inbound_flow_params=(7.0, 1.2),
                outbound_flow_params=(7.0, 1.2),
                bytes_per_flow_params=(7.0, 1.5),
                inbound_bias=0.5,
                active_hours_mean=24.0,
                business_hours_bias=0.55,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.8,
            ),
        ],
        "monitoring_server": [
            SubTypeProfile(
                name="prometheus",
                weight=3.0,
                primary_ports=[9090],
                secondary_ports=[9091],  # Pushgateway
                fan_in_params=(2.0, 0.8),  # Queries/dashboards
                fan_out_params=(5.0, 1.0),  # Scraping many targets
                inbound_flow_params=(6.0, 1.0),
                outbound_flow_params=(7.5, 1.0),
                bytes_per_flow_params=(6.0, 1.0),  # Metrics are small
                inbound_bias=0.35,  # More outbound (scraping)
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.98,
                udp_preference=0.01,
                stability=0.9,  # Regular scrape intervals
            ),
            SubTypeProfile(
                name="grafana",
                weight=2.0,
                primary_ports=[3000],
                secondary_ports=[],
                fan_in_params=(3.0, 1.0),  # Dashboard viewers
                fan_out_params=(2.0, 0.7),  # Data sources
                inbound_flow_params=(6.5, 1.2),
                outbound_flow_params=(6.0, 1.2),
                bytes_per_flow_params=(7.0, 1.3),
                inbound_bias=0.55,
                active_hours_mean=18.0,
                business_hours_bias=0.65,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.7,
            ),
            SubTypeProfile(
                name="kibana",
                weight=1.5,
                primary_ports=[5601],
                secondary_ports=[],
                fan_in_params=(2.5, 0.9),
                fan_out_params=(1.0, 0.5),  # Elasticsearch backend
                inbound_flow_params=(6.0, 1.2),
                outbound_flow_params=(6.5, 1.2),
                bytes_per_flow_params=(7.5, 1.5),
                inbound_bias=0.45,
                active_hours_mean=16.0,
                business_hours_bias=0.7,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.65,
            ),
            SubTypeProfile(
                name="influxdb",
                weight=1.0,
                primary_ports=[8086],
                secondary_ports=[8088],
                fan_in_params=(3.5, 1.0),  # Write sources
                fan_out_params=(1.5, 0.6),  # Query clients
                inbound_flow_params=(7.5, 1.0),
                outbound_flow_params=(6.5, 1.0),
                bytes_per_flow_params=(6.5, 1.2),
                inbound_bias=0.6,
                active_hours_mean=24.0,
                business_hours_bias=0.5,
                tcp_preference=0.99,
                udp_preference=0.005,
                stability=0.85,
            ),
        ],
    }

    # Legacy profiles for backward compatibility
    PROFILES: ClassVar[dict[str, FeatureProfile]] = {
        "server": FeatureProfile(
            fan_in_range=(30, 100),
            fan_out_range=(2, 10),
            inbound_flows_range=(500, 5000),
            outbound_flows_range=(50, 500),
            bytes_per_flow_range=(500, 5000),
            listener_ports=list(WEB_PORTS | {22}),
            unique_dst_ports_range=(2, 10),
            active_hours_range=(18, 24),
            business_hours_ratio_range=(0.3, 0.5),
            tcp_ratio_range=(0.85, 0.98),
            udp_ratio_range=(0.01, 0.1),
        ),
        "workstation": FeatureProfile(
            fan_in_range=(0, 5),
            fan_out_range=(50, 150),
            inbound_flows_range=(20, 200),
            outbound_flows_range=(200, 2000),
            bytes_per_flow_range=(1000, 8000),
            listener_ports=[],
            unique_dst_ports_range=(20, 100),
            active_hours_range=(8, 14),
            business_hours_ratio_range=(0.7, 0.95),
            tcp_ratio_range=(0.6, 0.85),
            udp_ratio_range=(0.1, 0.3),
        ),
        "database": FeatureProfile(
            fan_in_range=(5, 30),
            fan_out_range=(1, 5),
            inbound_flows_range=(200, 2000),
            outbound_flows_range=(20, 200),
            bytes_per_flow_range=(5000, 50000),
            listener_ports=list(DATABASE_PORTS)[:3],
            unique_dst_ports_range=(1, 5),
            active_hours_range=(20, 24),
            business_hours_ratio_range=(0.4, 0.6),
            tcp_ratio_range=(0.95, 0.99),
            udp_ratio_range=(0.005, 0.03),
        ),
        "load_balancer": FeatureProfile(
            fan_in_range=(100, 500),
            fan_out_range=(5, 20),
            inbound_flows_range=(5000, 50000),
            outbound_flows_range=(5000, 50000),
            bytes_per_flow_range=(500, 3000),
            listener_ports=list(LOAD_BALANCER_PORTS)[:3],
            unique_dst_ports_range=(2, 8),
            active_hours_range=(24, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.9, 0.98),
            udp_ratio_range=(0.01, 0.08),
        ),
        "network_device": FeatureProfile(
            fan_in_range=(5, 20),
            fan_out_range=(5, 20),
            inbound_flows_range=(500, 5000),
            outbound_flows_range=(500, 5000),
            bytes_per_flow_range=(100, 1000),
            listener_ports=list(NETWORK_DEVICE_PORTS)[:3],
            unique_dst_ports_range=(3, 15),
            active_hours_range=(24, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.3, 0.6),
            udp_ratio_range=(0.2, 0.5),
        ),
        "storage": FeatureProfile(
            fan_in_range=(10, 50),
            fan_out_range=(1, 5),
            inbound_flows_range=(500, 5000),
            outbound_flows_range=(100, 1000),
            bytes_per_flow_range=(10000, 100000),
            listener_ports=list(STORAGE_PORTS)[:3],
            unique_dst_ports_range=(1, 5),
            active_hours_range=(22, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.9, 0.99),
            udp_ratio_range=(0.005, 0.05),
        ),
        "container": FeatureProfile(
            fan_in_range=(5, 30),
            fan_out_range=(5, 30),
            inbound_flows_range=(100, 2000),
            outbound_flows_range=(100, 2000),
            bytes_per_flow_range=(500, 5000),
            listener_ports=[3000, 8000, 8080, 9000],
            unique_dst_ports_range=(5, 30),
            active_hours_range=(16, 22),
            business_hours_ratio_range=(0.5, 0.7),
            tcp_ratio_range=(0.85, 0.98),
            udp_ratio_range=(0.01, 0.1),
        ),
        "cloud_service": FeatureProfile(
            fan_in_range=(200, 1000),
            fan_out_range=(1, 10),
            inbound_flows_range=(10000, 100000),
            outbound_flows_range=(1000, 10000),
            bytes_per_flow_range=(500, 3000),
            listener_ports=[443, 80],
            unique_dst_ports_range=(1, 5),
            active_hours_range=(24, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.95, 0.99),
            udp_ratio_range=(0.005, 0.03),
        ),
        "virtual_machine": FeatureProfile(
            fan_in_range=(5, 30),
            fan_out_range=(5, 30),
            inbound_flows_range=(100, 2000),
            outbound_flows_range=(100, 2000),
            bytes_per_flow_range=(1000, 10000),
            listener_ports=[22, 80, 443],
            unique_dst_ports_range=(5, 30),
            active_hours_range=(14, 20),
            business_hours_ratio_range=(0.5, 0.7),
            tcp_ratio_range=(0.8, 0.95),
            udp_ratio_range=(0.03, 0.15),
        ),
    }

    # Workload mode multipliers
    WORKLOAD_MULTIPLIERS: ClassVar[dict[WorkloadMode, dict[str, float]]] = {
        WorkloadMode.IDLE: {
            "flow_mult": 0.05,
            "byte_mult": 0.03,
            "fan_mult": 0.1,
            "active_hours_mult": 0.2,
            "stability_bonus": 0.3,
        },
        WorkloadMode.LIGHT: {
            "flow_mult": 0.25,
            "byte_mult": 0.2,
            "fan_mult": 0.4,
            "active_hours_mult": 0.5,
            "stability_bonus": 0.1,
        },
        WorkloadMode.NORMAL: {
            "flow_mult": 1.0,
            "byte_mult": 1.0,
            "fan_mult": 1.0,
            "active_hours_mult": 1.0,
            "stability_bonus": 0.0,
        },
        WorkloadMode.HEAVY: {
            "flow_mult": 2.5,
            "byte_mult": 3.0,
            "fan_mult": 1.8,
            "active_hours_mult": 1.1,
            "stability_bonus": -0.1,
        },
        WorkloadMode.BURST: {
            "flow_mult": 5.0,
            "byte_mult": 4.0,
            "fan_mult": 2.0,
            "active_hours_mult": 0.6,
            "stability_bonus": -0.4,
        },
    }

    def __init__(self, seed: int | None = None) -> None:
        """Initialize the generator.

        Args:
            seed: Random seed for reproducibility.
        """
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.transformer = FeatureTransformer()

    def generate_sample(self, asset_type: str) -> BehavioralFeatures:
        """Generate a single synthetic sample for an asset type.

        Uses the improved sub-type based generation for more realistic data.

        Args:
            asset_type: One of the supported asset types.

        Returns:
            BehavioralFeatures with realistic values for the type.

        Raises:
            ValueError: If asset_type is not supported.
        """
        if asset_type not in self.SUBTYPES:
            raise ValueError(
                f"Unknown asset type: {asset_type}. "
                f"Supported: {list(self.SUBTYPES.keys())}"
            )

        # Select a random sub-type weighted by their weights
        subtypes = self.SUBTYPES[asset_type]
        weights = [st.weight for st in subtypes]
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        subtype = self.np_rng.choice(subtypes, p=weights)

        # Select a random workload mode (weighted toward normal)
        workload = self._select_workload()

        return self._generate_from_subtype(subtype, asset_type, workload)

    def generate_samples(
        self,
        asset_type: str,
        n: int,
    ) -> list[BehavioralFeatures]:
        """Generate multiple samples for an asset type.

        Args:
            asset_type: One of the supported asset types.
            n: Number of samples to generate.

        Returns:
            List of BehavioralFeatures instances.
        """
        return [self.generate_sample(asset_type) for _ in range(n)]

    def generate_balanced_dataset(
        self,
        samples_per_class: int = 500,
    ) -> TrainingDataset:
        """Generate a balanced dataset with equal samples per class.

        Args:
            samples_per_class: Number of samples per asset type.

        Returns:
            TrainingDataset with all asset types equally represented.
        """
        features_list: list[BehavioralFeatures] = []
        labels: list[str] = []

        for asset_type in self.SUBTYPES:
            samples = self.generate_samples(asset_type, samples_per_class)
            features_list.extend(samples)
            labels.extend([asset_type] * samples_per_class)

        logger.info(
            "Generated balanced synthetic dataset",
            samples_per_class=samples_per_class,
            total_samples=len(features_list),
            classes=list(self.SUBTYPES.keys()),
        )

        builder = DatasetBuilder()
        return builder.from_behavioral_features(features_list, labels)

    def generate_diverse_dataset(
        self,
        samples_per_class: int = 500,
        include_edge_cases: bool = True,
        edge_case_ratio: float = 0.15,
    ) -> TrainingDataset:
        """Generate a diverse dataset with edge cases and variations.

        Args:
            samples_per_class: Base number of samples per asset type.
            include_edge_cases: Whether to include edge case samples.
            edge_case_ratio: Proportion of samples that are edge cases.

        Returns:
            TrainingDataset with diverse, realistic samples.
        """
        features_list: list[BehavioralFeatures] = []
        labels: list[str] = []

        for asset_type in self.SUBTYPES:
            n_edge = int(samples_per_class * edge_case_ratio) if include_edge_cases else 0
            n_normal = samples_per_class - n_edge

            # Generate normal samples
            for _ in range(n_normal):
                features_list.append(self.generate_sample(asset_type))
                labels.append(asset_type)

            # Generate edge cases
            if include_edge_cases:
                edge_samples = self._generate_edge_cases(asset_type, n_edge)
                features_list.extend(edge_samples)
                labels.extend([asset_type] * n_edge)

        logger.info(
            "Generated diverse synthetic dataset",
            samples_per_class=samples_per_class,
            total_samples=len(features_list),
            edge_case_ratio=edge_case_ratio,
            classes=list(self.SUBTYPES.keys()),
        )

        builder = DatasetBuilder()
        return builder.from_behavioral_features(features_list, labels)

    def _select_workload(self) -> WorkloadMode:
        """Select a workload mode with realistic distribution."""
        modes = list(WorkloadMode)
        # Normal is most common, idle/burst are rare
        weights = [0.05, 0.15, 0.55, 0.20, 0.05]
        return self.np_rng.choice(modes, p=weights)

    def _generate_from_subtype(
        self,
        subtype: SubTypeProfile,
        _asset_type: str,
        workload: WorkloadMode,
    ) -> BehavioralFeatures:
        """Generate features from a sub-type profile with realistic distributions.

        Uses log-normal and beta distributions for more realistic traffic patterns.
        """
        mults = self.WORKLOAD_MULTIPLIERS[workload]

        # Sample fan-in/out from log-normal
        fan_in = max(
            0,
            int(
                self.np_rng.lognormal(*subtype.fan_in_params)
                * mults["fan_mult"]
            ),
        )
        fan_out = max(
            0,
            int(
                self.np_rng.lognormal(*subtype.fan_out_params)
                * mults["fan_mult"]
            ),
        )

        # Sample flows from log-normal
        inbound_flows = max(
            1,
            int(
                self.np_rng.lognormal(*subtype.inbound_flow_params)
                * mults["flow_mult"]
            ),
        )
        outbound_flows = max(
            1,
            int(
                self.np_rng.lognormal(*subtype.outbound_flow_params)
                * mults["flow_mult"]
            ),
        )

        # Apply inbound bias (shift traffic direction)
        if subtype.inbound_bias > 0.5:
            # More inbound
            factor = 1 + (subtype.inbound_bias - 0.5) * 2
            inbound_flows = int(inbound_flows * factor)
            outbound_flows = max(1, int(outbound_flows / factor))
        elif subtype.inbound_bias < 0.5:
            # More outbound
            factor = 1 + (0.5 - subtype.inbound_bias) * 2
            outbound_flows = int(outbound_flows * factor)
            inbound_flows = max(1, int(inbound_flows / factor))

        # Bytes per flow from log-normal
        bytes_per_flow = max(
            100,
            int(
                self.np_rng.lognormal(*subtype.bytes_per_flow_params)
                * mults["byte_mult"]
            ),
        )

        inbound_bytes = inbound_flows * bytes_per_flow
        outbound_bytes = outbound_flows * bytes_per_flow

        # Add realistic variance to bytes (not perfectly correlated with flows)
        inbound_bytes = int(inbound_bytes * self.np_rng.uniform(0.7, 1.4))
        outbound_bytes = int(outbound_bytes * self.np_rng.uniform(0.7, 1.4))

        # Temporal patterns
        active_hours_raw = self.np_rng.normal(
            subtype.active_hours_mean * mults["active_hours_mult"],
            subtype.active_hours_std,
        )
        active_hours = max(1, min(24, int(active_hours_raw)))

        # Business hours ratio using beta distribution
        business_alpha = subtype.business_hours_bias * 10 + 1
        business_beta = (1 - subtype.business_hours_bias) * 10 + 1
        business_hours_ratio = float(self.np_rng.beta(business_alpha, business_beta))

        # Port diversity correlates with fan-out
        base_dst_ports = max(1, int(self.np_rng.poisson(max(3, fan_out * 0.3))))
        unique_dst_ports = min(100, base_dst_ports + self.rng.randint(0, 5))

        # Determine listener ports
        listener_ports = []
        if subtype.primary_ports:
            # Always include at least one primary port
            n_primary = min(len(subtype.primary_ports), self.rng.randint(1, 3))
            listener_ports.extend(self.rng.sample(subtype.primary_ports, n_primary))

        if subtype.secondary_ports and self.rng.random() < 0.4:
            n_secondary = self.rng.randint(1, min(2, len(subtype.secondary_ports)))
            listener_ports.extend(self.rng.sample(subtype.secondary_ports, n_secondary))

        # Protocol distribution
        tcp_ratio = min(
            0.99,
            max(0.01, self.np_rng.normal(subtype.tcp_preference, 0.05)),
        )
        udp_ratio = min(
            1 - tcp_ratio - 0.01,
            max(0.001, self.np_rng.normal(subtype.udp_preference, 0.03)),
        )

        total_flows = inbound_flows + outbound_flows
        tcp_flows = int(total_flows * tcp_ratio)
        udp_flows = int(total_flows * udp_ratio)
        other_flows = max(0, total_flows - tcp_flows - udp_flows)

        protocol_distribution = {
            6: tcp_flows,
            17: udp_flows,
            1: other_flows,
        }

        # Stability -> traffic variance
        base_stability = subtype.stability + mults["stability_bonus"]
        stability = max(0.1, min(0.95, base_stability))
        traffic_variance = (1 - stability) * 0.8 + self.np_rng.uniform(0, 0.2)

        # Compute derived features
        total_connections = fan_in + fan_out
        fan_in_ratio = fan_in / total_connections if total_connections > 0 else 0.5

        if listener_ports:
            well_known_count = sum(1 for p in listener_ports if p < 1024)
            well_known_port_ratio = well_known_count / len(listener_ports)
        else:
            well_known_port_ratio = 0.0

        ephemeral_port_ratio = max(0.0, 1.0 - well_known_port_ratio - 0.15)

        # Convert to set for port checks
        port_set = set(listener_ports)

        return BehavioralFeatures(
            ip_address=f"10.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}/32",
            window_size="5min",
            computed_at=datetime.now(UTC),
            inbound_flows=inbound_flows,
            outbound_flows=outbound_flows,
            inbound_bytes=inbound_bytes,
            outbound_bytes=outbound_bytes,
            fan_in_count=fan_in,
            fan_out_count=fan_out,
            fan_in_ratio=fan_in_ratio,
            unique_dst_ports=unique_dst_ports,
            unique_src_ports=len(listener_ports),
            well_known_port_ratio=well_known_port_ratio,
            ephemeral_port_ratio=ephemeral_port_ratio,
            persistent_listener_ports=listener_ports,
            protocol_distribution=protocol_distribution,
            total_flows=total_flows,
            active_hours_count=active_hours,
            business_hours_ratio=business_hours_ratio,
            traffic_variance=traffic_variance,
            # Original port flags
            has_db_ports=bool(port_set & DATABASE_PORTS),
            has_storage_ports=bool(port_set & STORAGE_PORTS),
            has_web_ports=bool(port_set & WEB_PORTS),
            has_ssh_ports=22 in port_set,
            # Network services
            has_dns_ports=bool(port_set & DNS_PORTS),
            has_dhcp_ports=bool(port_set & DHCP_SERVER_PORTS),
            has_ntp_ports=bool(port_set & NTP_PORTS),
            has_directory_ports=bool(port_set & DIRECTORY_PORTS),
            # Communication
            has_mail_ports=bool(port_set & MAIL_PORTS),
            has_voip_ports=bool(port_set & VOIP_PORTS),
            # Security & access
            has_vpn_ports=bool(port_set & VPN_PORTS),
            has_proxy_ports=bool(port_set & PROXY_PORTS),
            has_log_collector_ports=bool(port_set & LOG_COLLECTOR_PORTS),
            has_remote_access_ports=bool(port_set & REMOTE_ACCESS_PORTS),
            # Endpoints
            has_printer_ports=bool(port_set & PRINTER_PORTS),
            has_iot_ports=bool(port_set & IOT_PORTS),
            has_camera_ports=bool(port_set & CAMERA_PORTS),
            # App infrastructure
            has_message_queue_ports=bool(port_set & MESSAGE_QUEUE_PORTS),
            has_monitoring_ports=bool(port_set & MONITORING_PORTS),
        )

    def _generate_edge_cases(
        self,
        asset_type: str,
        n: int,
    ) -> list[BehavioralFeatures]:
        """Generate edge case samples for an asset type.

        Edge cases include:
        - Newly deployed (minimal traffic)
        - Under attack (unusual traffic patterns)
        - Maintenance mode (very low activity)
        - Peak load (extreme values)
        - Misconfigured (unusual port usage)
        """
        samples = []
        edge_types = ["minimal", "peak", "unusual_ports", "mixed_role", "intermittent"]

        for i in range(n):
            edge_type = edge_types[i % len(edge_types)]
            sample = self._generate_edge_case_sample(asset_type, edge_type)
            samples.append(sample)

        return samples

    def _generate_edge_case_sample(
        self,
        asset_type: str,
        edge_type: str,
    ) -> BehavioralFeatures:
        """Generate a specific type of edge case sample."""
        # Start with a normal sample
        base = self.generate_sample(asset_type)

        if edge_type == "minimal":
            # Nearly idle - just started or maintenance
            return BehavioralFeatures(
                ip_address=base.ip_address,
                window_size=base.window_size,
                computed_at=base.computed_at,
                inbound_flows=max(1, base.inbound_flows // 50),
                outbound_flows=max(1, base.outbound_flows // 50),
                inbound_bytes=max(100, base.inbound_bytes // 100),
                outbound_bytes=max(100, base.outbound_bytes // 100),
                fan_in_count=max(0, base.fan_in_count // 10),
                fan_out_count=max(0, base.fan_out_count // 10),
                fan_in_ratio=base.fan_in_ratio,
                unique_dst_ports=max(1, base.unique_dst_ports // 5),
                unique_src_ports=base.unique_src_ports,
                well_known_port_ratio=base.well_known_port_ratio,
                ephemeral_port_ratio=base.ephemeral_port_ratio,
                persistent_listener_ports=base.persistent_listener_ports,
                protocol_distribution={
                    k: max(0, v // 50) for k, v in base.protocol_distribution.items()
                },
                total_flows=max(2, base.total_flows // 50),
                active_hours_count=max(1, base.active_hours_count // 4),
                business_hours_ratio=base.business_hours_ratio,
                traffic_variance=0.9,  # Very inconsistent
                has_db_ports=base.has_db_ports,
                has_storage_ports=base.has_storage_ports,
                has_web_ports=base.has_web_ports,
                has_ssh_ports=base.has_ssh_ports,
                has_dns_ports=base.has_dns_ports,
                has_dhcp_ports=base.has_dhcp_ports,
                has_ntp_ports=base.has_ntp_ports,
                has_directory_ports=base.has_directory_ports,
                has_mail_ports=base.has_mail_ports,
                has_voip_ports=base.has_voip_ports,
                has_vpn_ports=base.has_vpn_ports,
                has_proxy_ports=base.has_proxy_ports,
                has_log_collector_ports=base.has_log_collector_ports,
                has_remote_access_ports=base.has_remote_access_ports,
                has_printer_ports=base.has_printer_ports,
                has_iot_ports=base.has_iot_ports,
                has_camera_ports=base.has_camera_ports,
                has_message_queue_ports=base.has_message_queue_ports,
                has_monitoring_ports=base.has_monitoring_ports,
            )

        elif edge_type == "peak":
            # Extreme load
            return BehavioralFeatures(
                ip_address=base.ip_address,
                window_size=base.window_size,
                computed_at=base.computed_at,
                inbound_flows=base.inbound_flows * 10,
                outbound_flows=base.outbound_flows * 10,
                inbound_bytes=base.inbound_bytes * 15,
                outbound_bytes=base.outbound_bytes * 15,
                fan_in_count=min(1000, base.fan_in_count * 5),
                fan_out_count=min(500, base.fan_out_count * 3),
                fan_in_ratio=base.fan_in_ratio,
                unique_dst_ports=min(200, base.unique_dst_ports * 3),
                unique_src_ports=base.unique_src_ports,
                well_known_port_ratio=base.well_known_port_ratio,
                ephemeral_port_ratio=base.ephemeral_port_ratio,
                persistent_listener_ports=base.persistent_listener_ports,
                protocol_distribution={
                    k: v * 10 for k, v in base.protocol_distribution.items()
                },
                total_flows=base.total_flows * 10,
                active_hours_count=24,
                business_hours_ratio=0.5,
                traffic_variance=0.15,  # Very stable at peak
                has_db_ports=base.has_db_ports,
                has_storage_ports=base.has_storage_ports,
                has_web_ports=base.has_web_ports,
                has_ssh_ports=base.has_ssh_ports,
                has_dns_ports=base.has_dns_ports,
                has_dhcp_ports=base.has_dhcp_ports,
                has_ntp_ports=base.has_ntp_ports,
                has_directory_ports=base.has_directory_ports,
                has_mail_ports=base.has_mail_ports,
                has_voip_ports=base.has_voip_ports,
                has_vpn_ports=base.has_vpn_ports,
                has_proxy_ports=base.has_proxy_ports,
                has_log_collector_ports=base.has_log_collector_ports,
                has_remote_access_ports=base.has_remote_access_ports,
                has_printer_ports=base.has_printer_ports,
                has_iot_ports=base.has_iot_ports,
                has_camera_ports=base.has_camera_ports,
                has_message_queue_ports=base.has_message_queue_ports,
                has_monitoring_ports=base.has_monitoring_ports,
            )

        elif edge_type == "unusual_ports":
            # Using non-standard ports
            unusual_ports = [
                p + self.rng.randint(1000, 5000)
                for p in base.persistent_listener_ports
                if p < 1024
            ] or [self.rng.randint(10000, 60000)]

            return BehavioralFeatures(
                ip_address=base.ip_address,
                window_size=base.window_size,
                computed_at=base.computed_at,
                inbound_flows=base.inbound_flows,
                outbound_flows=base.outbound_flows,
                inbound_bytes=base.inbound_bytes,
                outbound_bytes=base.outbound_bytes,
                fan_in_count=base.fan_in_count,
                fan_out_count=base.fan_out_count,
                fan_in_ratio=base.fan_in_ratio,
                unique_dst_ports=base.unique_dst_ports + 5,
                unique_src_ports=len(unusual_ports),
                well_known_port_ratio=0.0,
                ephemeral_port_ratio=0.8,
                persistent_listener_ports=unusual_ports,
                protocol_distribution=base.protocol_distribution,
                total_flows=base.total_flows,
                active_hours_count=base.active_hours_count,
                business_hours_ratio=base.business_hours_ratio,
                traffic_variance=base.traffic_variance,
                # All port flags False for non-standard ports
                has_db_ports=False,
                has_storage_ports=False,
                has_web_ports=False,
                has_ssh_ports=False,
                has_dns_ports=False,
                has_dhcp_ports=False,
                has_ntp_ports=False,
                has_directory_ports=False,
                has_mail_ports=False,
                has_voip_ports=False,
                has_vpn_ports=False,
                has_proxy_ports=False,
                has_log_collector_ports=False,
                has_remote_access_ports=False,
                has_printer_ports=False,
                has_iot_ports=False,
                has_camera_ports=False,
                has_message_queue_ports=False,
                has_monitoring_ports=False,
            )

        elif edge_type == "mixed_role":
            # Asset serving multiple roles (e.g., web + database)
            mixed_ports = list(base.persistent_listener_ports)
            if asset_type == "server":
                mixed_ports.extend([3306, 5432])  # Add DB ports
            elif asset_type == "database":
                mixed_ports.extend([80, 443])  # Add web ports
            else:
                mixed_ports.extend([22, 80, 443])

            mixed_ports = list(set(mixed_ports))[:6]
            mixed_port_set = set(mixed_ports)

            return BehavioralFeatures(
                ip_address=base.ip_address,
                window_size=base.window_size,
                computed_at=base.computed_at,
                inbound_flows=int(base.inbound_flows * 1.5),
                outbound_flows=int(base.outbound_flows * 1.3),
                inbound_bytes=int(base.inbound_bytes * 1.4),
                outbound_bytes=int(base.outbound_bytes * 1.4),
                fan_in_count=int(base.fan_in_count * 1.5),
                fan_out_count=int(base.fan_out_count * 1.3),
                fan_in_ratio=base.fan_in_ratio,
                unique_dst_ports=base.unique_dst_ports + 3,
                unique_src_ports=len(mixed_ports),
                well_known_port_ratio=sum(1 for p in mixed_ports if p < 1024)
                / len(mixed_ports)
                if mixed_ports
                else 0,
                ephemeral_port_ratio=0.3,
                persistent_listener_ports=mixed_ports,
                protocol_distribution=base.protocol_distribution,
                total_flows=int(base.total_flows * 1.4),
                active_hours_count=min(24, base.active_hours_count + 4),
                business_hours_ratio=base.business_hours_ratio,
                traffic_variance=base.traffic_variance * 1.2,
                has_db_ports=bool(mixed_port_set & DATABASE_PORTS),
                has_storage_ports=bool(mixed_port_set & STORAGE_PORTS),
                has_web_ports=bool(mixed_port_set & WEB_PORTS),
                has_ssh_ports=22 in mixed_port_set,
                has_dns_ports=bool(mixed_port_set & DNS_PORTS),
                has_dhcp_ports=bool(mixed_port_set & DHCP_SERVER_PORTS),
                has_ntp_ports=bool(mixed_port_set & NTP_PORTS),
                has_directory_ports=bool(mixed_port_set & DIRECTORY_PORTS),
                has_mail_ports=bool(mixed_port_set & MAIL_PORTS),
                has_voip_ports=bool(mixed_port_set & VOIP_PORTS),
                has_vpn_ports=bool(mixed_port_set & VPN_PORTS),
                has_proxy_ports=bool(mixed_port_set & PROXY_PORTS),
                has_log_collector_ports=bool(mixed_port_set & LOG_COLLECTOR_PORTS),
                has_remote_access_ports=bool(mixed_port_set & REMOTE_ACCESS_PORTS),
                has_printer_ports=bool(mixed_port_set & PRINTER_PORTS),
                has_iot_ports=bool(mixed_port_set & IOT_PORTS),
                has_camera_ports=bool(mixed_port_set & CAMERA_PORTS),
                has_message_queue_ports=bool(mixed_port_set & MESSAGE_QUEUE_PORTS),
                has_monitoring_ports=bool(mixed_port_set & MONITORING_PORTS),
            )

        else:  # intermittent
            # Very bursty, on-off pattern
            return BehavioralFeatures(
                ip_address=base.ip_address,
                window_size=base.window_size,
                computed_at=base.computed_at,
                inbound_flows=base.inbound_flows * 3,
                outbound_flows=base.outbound_flows * 3,
                inbound_bytes=base.inbound_bytes * 2,
                outbound_bytes=base.outbound_bytes * 2,
                fan_in_count=base.fan_in_count,
                fan_out_count=base.fan_out_count,
                fan_in_ratio=base.fan_in_ratio,
                unique_dst_ports=base.unique_dst_ports,
                unique_src_ports=base.unique_src_ports,
                well_known_port_ratio=base.well_known_port_ratio,
                ephemeral_port_ratio=base.ephemeral_port_ratio,
                persistent_listener_ports=base.persistent_listener_ports,
                protocol_distribution={
                    k: v * 3 for k, v in base.protocol_distribution.items()
                },
                total_flows=base.total_flows * 3,
                active_hours_count=max(2, base.active_hours_count // 3),
                business_hours_ratio=self.rng.uniform(0.1, 0.9),
                traffic_variance=0.85,
                has_db_ports=base.has_db_ports,
                has_storage_ports=base.has_storage_ports,
                has_web_ports=base.has_web_ports,
                has_ssh_ports=base.has_ssh_ports,
                has_dns_ports=base.has_dns_ports,
                has_dhcp_ports=base.has_dhcp_ports,
                has_ntp_ports=base.has_ntp_ports,
                has_directory_ports=base.has_directory_ports,
                has_mail_ports=base.has_mail_ports,
                has_voip_ports=base.has_voip_ports,
                has_vpn_ports=base.has_vpn_ports,
                has_proxy_ports=base.has_proxy_ports,
                has_log_collector_ports=base.has_log_collector_ports,
                has_remote_access_ports=base.has_remote_access_ports,
                has_printer_ports=base.has_printer_ports,
                has_iot_ports=base.has_iot_ports,
                has_camera_ports=base.has_camera_ports,
                has_message_queue_ports=base.has_message_queue_ports,
                has_monitoring_ports=base.has_monitoring_ports,
            )

    def _generate_from_profile(
        self,
        profile: FeatureProfile,
        _asset_type: str,
    ) -> BehavioralFeatures:
        """Legacy method: Generate features from a profile with realistic noise.

        Kept for backward compatibility. New code should use generate_sample().

        Args:
            profile: Feature profile to sample from.
            asset_type: Asset type name for logging.

        Returns:
            BehavioralFeatures with sampled values.
        """
        # Sample basic metrics
        fan_in = self._sample_int(profile.fan_in_range)
        fan_out = self._sample_int(profile.fan_out_range)
        inbound_flows = self._sample_int(profile.inbound_flows_range)
        outbound_flows = self._sample_int(profile.outbound_flows_range)
        bytes_per_flow = self._sample_int(profile.bytes_per_flow_range)

        # Compute byte volumes
        inbound_bytes = inbound_flows * bytes_per_flow
        outbound_bytes = outbound_flows * bytes_per_flow

        # Sample temporal patterns
        active_hours = self._sample_int(profile.active_hours_range)
        business_hours_ratio = self._sample_float(profile.business_hours_ratio_range)

        # Sample port diversity
        unique_dst_ports = self._sample_int(profile.unique_dst_ports_range)

        # Generate protocol distribution
        tcp_ratio = self._sample_float(profile.tcp_ratio_range)
        udp_ratio = self._sample_float(profile.udp_ratio_range)

        # Ensure ratios sum to <= 1
        if tcp_ratio + udp_ratio > 0.99:
            udp_ratio = 0.99 - tcp_ratio

        total_flows = inbound_flows + outbound_flows
        tcp_flows = int(total_flows * tcp_ratio)
        udp_flows = int(total_flows * udp_ratio)
        other_flows = total_flows - tcp_flows - udp_flows

        protocol_distribution = {
            6: tcp_flows,
            17: udp_flows,
            1: max(0, other_flows),
        }

        # Determine listener ports (with some variation)
        listener_ports = profile.listener_ports.copy()
        if listener_ports and self.rng.random() < 0.3:
            extra_port = self.rng.choice([8080, 8443, 3000, 5000, 9000])
            if extra_port not in listener_ports:
                listener_ports.append(extra_port)

        # Compute derived metrics
        total_connections = fan_in + fan_out
        fan_in_ratio = fan_in / total_connections if total_connections > 0 else 0.5

        if listener_ports:
            well_known_count = sum(1 for p in listener_ports if p < 1024)
            well_known_port_ratio = well_known_count / len(listener_ports)
        else:
            well_known_port_ratio = 0.0

        ephemeral_port_ratio = max(0.0, 1.0 - well_known_port_ratio - 0.2)

        if active_hours >= 22:
            traffic_variance = self._sample_float((0.1, 0.3))
        elif active_hours >= 16:
            traffic_variance = self._sample_float((0.3, 0.5))
        else:
            traffic_variance = self._sample_float((0.5, 0.8))

        # Convert to set for port checks
        port_set = set(listener_ports)

        return BehavioralFeatures(
            ip_address=f"10.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}/32",
            window_size="5min",
            computed_at=datetime.now(UTC),
            inbound_flows=inbound_flows,
            outbound_flows=outbound_flows,
            inbound_bytes=inbound_bytes,
            outbound_bytes=outbound_bytes,
            fan_in_count=fan_in,
            fan_out_count=fan_out,
            fan_in_ratio=fan_in_ratio,
            unique_dst_ports=unique_dst_ports,
            unique_src_ports=len(listener_ports),
            well_known_port_ratio=well_known_port_ratio,
            ephemeral_port_ratio=ephemeral_port_ratio,
            persistent_listener_ports=listener_ports,
            protocol_distribution=protocol_distribution,
            total_flows=total_flows,
            active_hours_count=active_hours,
            business_hours_ratio=business_hours_ratio,
            traffic_variance=traffic_variance,
            # Original port flags
            has_db_ports=bool(port_set & DATABASE_PORTS),
            has_storage_ports=bool(port_set & STORAGE_PORTS),
            has_web_ports=bool(port_set & WEB_PORTS),
            has_ssh_ports=22 in port_set,
            # Network services
            has_dns_ports=bool(port_set & DNS_PORTS),
            has_dhcp_ports=bool(port_set & DHCP_SERVER_PORTS),
            has_ntp_ports=bool(port_set & NTP_PORTS),
            has_directory_ports=bool(port_set & DIRECTORY_PORTS),
            # Communication
            has_mail_ports=bool(port_set & MAIL_PORTS),
            has_voip_ports=bool(port_set & VOIP_PORTS),
            # Security & access
            has_vpn_ports=bool(port_set & VPN_PORTS),
            has_proxy_ports=bool(port_set & PROXY_PORTS),
            has_log_collector_ports=bool(port_set & LOG_COLLECTOR_PORTS),
            has_remote_access_ports=bool(port_set & REMOTE_ACCESS_PORTS),
            # Endpoints
            has_printer_ports=bool(port_set & PRINTER_PORTS),
            has_iot_ports=bool(port_set & IOT_PORTS),
            has_camera_ports=bool(port_set & CAMERA_PORTS),
            # App infrastructure
            has_message_queue_ports=bool(port_set & MESSAGE_QUEUE_PORTS),
            has_monitoring_ports=bool(port_set & MONITORING_PORTS),
        )

    def _sample_int(self, range_tuple: tuple[int, int]) -> int:
        """Sample an integer uniformly from a range."""
        return self.rng.randint(range_tuple[0], range_tuple[1])

    def _sample_float(self, range_tuple: tuple[float, float]) -> float:
        """Sample a float uniformly from a range."""
        return self.rng.uniform(range_tuple[0], range_tuple[1])
