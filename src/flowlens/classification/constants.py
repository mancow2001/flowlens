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

    # Compute
    SERVER = "server"
    WORKSTATION = "workstation"
    VIRTUAL_MACHINE = "virtual_machine"
    CONTAINER = "container"
    CLOUD_SERVICE = "cloud_service"

    # Data
    DATABASE = "database"
    STORAGE = "storage"

    # Network
    LOAD_BALANCER = "load_balancer"
    NETWORK_DEVICE = "network_device"  # Covers router, switch, firewall

    # Network Services
    DNS_SERVER = "dns_server"
    DHCP_SERVER = "dhcp_server"
    NTP_SERVER = "ntp_server"
    DIRECTORY_SERVICE = "directory_service"

    # Communication
    MAIL_SERVER = "mail_server"
    VOIP_SERVER = "voip_server"

    # Security & Access
    VPN_GATEWAY = "vpn_gateway"
    PROXY_SERVER = "proxy_server"
    LOG_COLLECTOR = "log_collector"
    REMOTE_ACCESS = "remote_access"

    # Endpoints
    PRINTER = "printer"
    IOT_DEVICE = "iot_device"
    IP_CAMERA = "ip_camera"

    # Application Infrastructure
    MESSAGE_QUEUE = "message_queue"
    MONITORING_SERVER = "monitoring_server"

    # Default
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
    9300,   # Elasticsearch cluster
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
    10256,  # kube-proxy
    4194,   # cAdvisor
    4789,   # VXLAN overlay
    8001,   # Kubernetes dashboard
    8472,   # Flannel VXLAN
}

# === NEW PORT SETS ===

# Network Services
DNS_PORTS: Final[set[int]] = {
    53,     # DNS
    953,    # RNDC (BIND control)
    5353,   # mDNS
}

DHCP_SERVER_PORTS: Final[set[int]] = {
    67,     # DHCP server listens on port 67
}

# Note: Port 68 is for DHCP clients (receiving responses), not servers
# We only use DHCP_SERVER_PORTS for classification to avoid misclassifying clients

NTP_PORTS: Final[set[int]] = {
    123,    # NTP
}

DIRECTORY_PORTS: Final[set[int]] = {
    88,     # Kerberos
    389,    # LDAP
    464,    # Kerberos password
    636,    # LDAPS
    1812,   # RADIUS auth
    1813,   # RADIUS accounting
    3268,   # AD Global Catalog
    3269,   # AD Global Catalog SSL
}

# Communication
MAIL_PORTS: Final[set[int]] = {
    25,     # SMTP
    110,    # POP3
    143,    # IMAP
    465,    # SMTPS
    587,    # SMTP Submission
    993,    # IMAPS
    995,    # POP3S
}

VOIP_PORTS: Final[set[int]] = {
    3478,   # STUN
    3479,   # STUN alt
    5004,   # RTP
    5005,   # RTCP
    5060,   # SIP
    5061,   # SIPS
}

# Security & Access
VPN_PORTS: Final[set[int]] = {
    443,    # SSL VPN
    500,    # IKE
    1194,   # OpenVPN
    1701,   # L2TP
    1723,   # PPTP
    4500,   # IPSec NAT-T
}

PROXY_PORTS: Final[set[int]] = {
    1080,   # SOCKS
    3128,   # Squid
    8080,   # HTTP proxy
    8888,   # Alt HTTP proxy
}

LOG_COLLECTOR_PORTS: Final[set[int]] = {
    514,    # Syslog
    2055,   # NetFlow
    4739,   # IPFIX
    5000,   # Splunk
    5044,   # Logstash Beats
    6514,   # Syslog TLS
    9995,   # NetFlow alt
}

REMOTE_ACCESS_PORTS: Final[set[int]] = {
    3389,   # RDP
    4172,   # PCoIP
    5900,   # VNC
    8443,   # Alt HTTPS/VDI
}

# Endpoints
PRINTER_PORTS: Final[set[int]] = {
    515,    # LPR
    631,    # IPP/CUPS
    9100,   # RAW printing
    9220,   # PDL Data Stream
}

IOT_PORTS: Final[set[int]] = {
    1883,   # MQTT
    5683,   # CoAP
    5684,   # CoAP DTLS
    8883,   # MQTT TLS
}

CAMERA_PORTS: Final[set[int]] = {
    554,    # RTSP
    8554,   # RTSP alt
    37777,  # Dahua
}

# Application Infrastructure
MESSAGE_QUEUE_PORTS: Final[set[int]] = {
    5671,   # AMQP TLS
    5672,   # AMQP (RabbitMQ)
    9092,   # Kafka
    9093,   # Kafka TLS
    61616,  # ActiveMQ
}

MONITORING_PORTS: Final[set[int]] = {
    3000,   # Grafana
    5601,   # Kibana
    8086,   # InfluxDB (also in DATABASE)
    9090,   # Prometheus
    9091,   # Prometheus pushgateway
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
    # Existing categories
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
    # Network Services
    if port in DNS_PORTS:
        return "dns"
    if port in DHCP_SERVER_PORTS:
        return "dhcp"
    if port in NTP_PORTS:
        return "ntp"
    if port in DIRECTORY_PORTS:
        return "directory"
    # Communication
    if port in MAIL_PORTS:
        return "mail"
    if port in VOIP_PORTS:
        return "voip"
    # Security & Access
    if port in VPN_PORTS:
        return "vpn"
    if port in PROXY_PORTS:
        return "proxy"
    if port in LOG_COLLECTOR_PORTS:
        return "log_collector"
    if port in REMOTE_ACCESS_PORTS:
        return "remote_access"
    # Endpoints
    if port in PRINTER_PORTS:
        return "printer"
    if port in IOT_PORTS:
        return "iot"
    if port in CAMERA_PORTS:
        return "camera"
    # Application Infrastructure
    if port in MESSAGE_QUEUE_PORTS:
        return "message_queue"
    if port in MONITORING_PORTS:
        return "monitoring"
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
