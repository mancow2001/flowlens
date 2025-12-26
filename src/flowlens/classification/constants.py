"""Constants for asset classification.

Defines port lists, thresholds, and asset type definitions used by the
classification engine.
"""

from enum import Enum
from typing import Final


class ClassifiableAssetType(str, Enum):
    """Asset types that can be inferred from network behavior.

    These map to the AssetType enum in models/asset.py but exclude types
    that cannot be reliably detected from flow data alone.
    """

    SERVER = "server"
    WORKSTATION = "workstation"
    DATABASE = "database"
    LOAD_BALANCER = "load_balancer"
    NETWORK_DEVICE = "network_device"  # Covers router, switch, firewall
    STORAGE = "storage"
    CONTAINER = "container"
    VIRTUAL_MACHINE = "virtual_machine"
    CLOUD_SERVICE = "cloud_service"
    UNKNOWN = "unknown"


# Port categories for classification signals
# These are defaults that can be overridden via config

DATABASE_PORTS: Final[set[int]] = {
    1433,   # MSSQL
    1521,   # Oracle
    3306,   # MySQL
    5432,   # PostgreSQL
    27017,  # MongoDB
    6379,   # Redis
    9042,   # Cassandra CQL
    7000,   # Cassandra inter-node
    5984,   # CouchDB
    8086,   # InfluxDB
    9200,   # Elasticsearch
    11211,  # Memcached
}

STORAGE_PORTS: Final[set[int]] = {
    2049,   # NFS
    445,    # SMB/CIFS
    3260,   # iSCSI
    111,    # RPCbind (often for NFS)
    139,    # NetBIOS (SMB legacy)
    548,    # AFP (Apple Filing Protocol)
    873,    # Rsync
}

WEB_PORTS: Final[set[int]] = {
    80,     # HTTP
    443,    # HTTPS
    8080,   # Alt HTTP
    8443,   # Alt HTTPS
    3000,   # Dev servers (Node, Rails)
    5000,   # Flask default
    8000,   # Django/FastAPI default
}

SSH_PORTS: Final[set[int]] = {
    22,     # SSH
}

LOAD_BALANCER_PORTS: Final[set[int]] = {
    80,     # HTTP
    443,    # HTTPS
    8080,   # Alt HTTP
    8443,   # Alt HTTPS
    1936,   # HAProxy stats
}

NETWORK_DEVICE_PORTS: Final[set[int]] = {
    22,     # SSH management
    23,     # Telnet
    161,    # SNMP
    162,    # SNMP trap
    179,    # BGP
    520,    # RIP
    1723,   # PPTP
    500,    # IKE (VPN)
    4500,   # IPSec NAT-T
}

CONTAINER_PORTS: Final[set[int]] = {
    2375,   # Docker API (unencrypted)
    2376,   # Docker API (TLS)
    6443,   # Kubernetes API
    10250,  # Kubelet API
    10255,  # Kubelet read-only
    4194,   # cAdvisor
    8001,   # Kubernetes dashboard
}

# Protocol numbers
PROTOCOL_TCP: Final[int] = 6
PROTOCOL_UDP: Final[int] = 17
PROTOCOL_ICMP: Final[int] = 1
PROTOCOL_ICMPV6: Final[int] = 58

# Port range thresholds
WELL_KNOWN_PORT_MAX: Final[int] = 1023
EPHEMERAL_PORT_MIN: Final[int] = 32768
REGISTERED_PORT_MIN: Final[int] = 1024
REGISTERED_PORT_MAX: Final[int] = 49151

# Classification thresholds
DEFAULT_MIN_FLOWS: Final[int] = 100
DEFAULT_MIN_OBSERVATION_HOURS: Final[int] = 24
DEFAULT_AUTO_UPDATE_THRESHOLD: Final[float] = 0.70
DEFAULT_HIGH_CONFIDENCE_THRESHOLD: Final[float] = 0.85

# Fan-in/fan-out thresholds for classification
HIGH_FAN_IN_THRESHOLD: Final[int] = 20
VERY_HIGH_FAN_IN_THRESHOLD: Final[int] = 100
HIGH_FAN_OUT_THRESHOLD: Final[int] = 50
LOW_FAN_IN_THRESHOLD: Final[int] = 5
LOW_FAN_OUT_THRESHOLD: Final[int] = 5

# Traffic volume thresholds
HIGH_BYTES_PER_FLOW_THRESHOLD: Final[int] = 1_000_000  # 1MB
HIGH_CONNECTION_RATE_THRESHOLD: Final[int] = 5000  # flows per window

# Temporal thresholds
BUSINESS_HOURS_START: Final[int] = 8
BUSINESS_HOURS_END: Final[int] = 18
HIGH_ACTIVE_HOURS_THRESHOLD: Final[int] = 18  # 24x7 indicator
DIURNAL_PATTERN_THRESHOLD: Final[float] = 0.7  # business hours ratio

# Ratio thresholds
HIGH_FAN_IN_RATIO: Final[float] = 0.6
SYMMETRIC_TRAFFIC_THRESHOLD: Final[float] = 0.3  # abs(in-out)/(in+out)


def get_port_category(port: int) -> str | None:
    """Get the category for a port number.

    Args:
        port: TCP/UDP port number.

    Returns:
        Category name or None if not categorized.
    """
    if port in DATABASE_PORTS:
        return "database"
    if port in STORAGE_PORTS:
        return "storage"
    if port in WEB_PORTS:
        return "web"
    if port in SSH_PORTS:
        return "ssh"
    if port in LOAD_BALANCER_PORTS:
        return "load_balancer"
    if port in NETWORK_DEVICE_PORTS:
        return "network_device"
    if port in CONTAINER_PORTS:
        return "container"
    return None


def is_well_known_port(port: int) -> bool:
    """Check if a port is in the well-known range (0-1023)."""
    return 0 <= port <= WELL_KNOWN_PORT_MAX


def is_ephemeral_port(port: int) -> bool:
    """Check if a port is in the ephemeral range (32768+)."""
    return port >= EPHEMERAL_PORT_MIN


def is_registered_port(port: int) -> bool:
    """Check if a port is in the registered range (1024-49151)."""
    return REGISTERED_PORT_MIN <= port <= REGISTERED_PORT_MAX
