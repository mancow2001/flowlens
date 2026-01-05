"""Protocol and service inference from port numbers.

Maps well-known ports to service types and protocols.
"""

from dataclasses import dataclass


@dataclass
class ServiceInfo:
    """Information about a network service."""

    name: str
    protocol: str  # TCP, UDP, or BOTH
    category: str  # web, database, mail, etc.
    encrypted: bool = False
    description: str | None = None


# Well-known port mappings
# Based on IANA Service Name and Transport Protocol Port Number Registry
WELL_KNOWN_PORTS: dict[int, ServiceInfo] = {
    # System ports (0-1023)
    20: ServiceInfo("ftp-data", "TCP", "file_transfer", description="FTP data transfer"),
    21: ServiceInfo("ftp", "TCP", "file_transfer", description="FTP control"),
    22: ServiceInfo("ssh", "TCP", "remote_access", encrypted=True, description="SSH"),
    23: ServiceInfo("telnet", "TCP", "remote_access", description="Telnet"),
    25: ServiceInfo("smtp", "TCP", "mail", description="Simple Mail Transfer"),
    53: ServiceInfo("dns", "BOTH", "infrastructure", description="Domain Name System"),
    67: ServiceInfo("dhcp-server", "UDP", "infrastructure", description="DHCP server"),
    68: ServiceInfo("dhcp-client", "UDP", "infrastructure", description="DHCP client"),
    69: ServiceInfo("tftp", "UDP", "file_transfer", description="Trivial FTP"),
    80: ServiceInfo("http", "TCP", "web", description="HTTP"),
    110: ServiceInfo("pop3", "TCP", "mail", description="POP3"),
    111: ServiceInfo("rpcbind", "BOTH", "infrastructure", description="ONC RPC"),
    123: ServiceInfo("ntp", "UDP", "infrastructure", description="Network Time Protocol"),
    135: ServiceInfo("msrpc", "TCP", "infrastructure", description="Microsoft RPC"),
    137: ServiceInfo("netbios-ns", "UDP", "infrastructure", description="NetBIOS Name Service"),
    138: ServiceInfo("netbios-dgm", "UDP", "infrastructure", description="NetBIOS Datagram"),
    139: ServiceInfo("netbios-ssn", "TCP", "infrastructure", description="NetBIOS Session"),
    143: ServiceInfo("imap", "TCP", "mail", description="IMAP"),
    161: ServiceInfo("snmp", "UDP", "monitoring", description="SNMP"),
    162: ServiceInfo("snmptrap", "UDP", "monitoring", description="SNMP Trap"),
    389: ServiceInfo("ldap", "TCP", "directory", description="LDAP"),
    443: ServiceInfo("https", "TCP", "web", encrypted=True, description="HTTPS"),
    445: ServiceInfo("smb", "TCP", "file_transfer", description="SMB/CIFS"),
    465: ServiceInfo("smtps", "TCP", "mail", encrypted=True, description="SMTP over TLS"),
    500: ServiceInfo("isakmp", "UDP", "vpn", encrypted=True, description="IKE"),
    514: ServiceInfo("syslog", "UDP", "logging", description="Syslog"),
    515: ServiceInfo("lpd", "TCP", "printing", description="Line Printer Daemon"),
    520: ServiceInfo("rip", "UDP", "infrastructure", description="RIP"),
    546: ServiceInfo("dhcpv6-client", "UDP", "infrastructure", description="DHCPv6 client"),
    547: ServiceInfo("dhcpv6-server", "UDP", "infrastructure", description="DHCPv6 server"),
    587: ServiceInfo("submission", "TCP", "mail", description="Mail submission"),
    636: ServiceInfo("ldaps", "TCP", "directory", encrypted=True, description="LDAPS"),
    873: ServiceInfo("rsync", "TCP", "file_transfer", description="rsync"),
    993: ServiceInfo("imaps", "TCP", "mail", encrypted=True, description="IMAP over TLS"),
    995: ServiceInfo("pop3s", "TCP", "mail", encrypted=True, description="POP3 over TLS"),

    # Registered ports (1024-49151)
    1080: ServiceInfo("socks", "TCP", "proxy", description="SOCKS proxy"),
    1433: ServiceInfo("mssql", "TCP", "database", description="Microsoft SQL Server"),
    1434: ServiceInfo("mssql-udp", "UDP", "database", description="MS SQL Server Browser"),
    1521: ServiceInfo("oracle", "TCP", "database", description="Oracle Database"),
    1723: ServiceInfo("pptp", "TCP", "vpn", description="PPTP"),
    1883: ServiceInfo("mqtt", "TCP", "messaging", description="MQTT"),
    2049: ServiceInfo("nfs", "BOTH", "file_transfer", description="NFS"),
    2055: ServiceInfo("netflow", "UDP", "monitoring", description="NetFlow"),
    2181: ServiceInfo("zookeeper", "TCP", "coordination", description="ZooKeeper"),
    2375: ServiceInfo("docker", "TCP", "container", description="Docker API (unencrypted)"),
    2376: ServiceInfo("docker-tls", "TCP", "container", encrypted=True, description="Docker API (TLS)"),
    2379: ServiceInfo("etcd-client", "TCP", "coordination", description="etcd client"),
    2380: ServiceInfo("etcd-peer", "TCP", "coordination", description="etcd peer"),
    3000: ServiceInfo("grafana", "TCP", "monitoring", description="Grafana"),
    3306: ServiceInfo("mysql", "TCP", "database", description="MySQL"),
    3389: ServiceInfo("rdp", "TCP", "remote_access", description="Remote Desktop"),
    4369: ServiceInfo("epmd", "TCP", "messaging", description="Erlang Port Mapper"),
    5000: ServiceInfo("upnp", "TCP", "infrastructure", description="UPnP"),
    5432: ServiceInfo("postgresql", "TCP", "database", description="PostgreSQL"),
    5601: ServiceInfo("kibana", "TCP", "monitoring", description="Kibana"),
    5672: ServiceInfo("amqp", "TCP", "messaging", description="AMQP/RabbitMQ"),
    5900: ServiceInfo("vnc", "TCP", "remote_access", description="VNC"),
    6343: ServiceInfo("sflow", "UDP", "monitoring", description="sFlow"),
    6379: ServiceInfo("redis", "TCP", "cache", description="Redis"),
    6443: ServiceInfo("kubernetes-api", "TCP", "container", encrypted=True, description="Kubernetes API"),
    7001: ServiceInfo("weblogic", "TCP", "application", description="WebLogic"),
    8000: ServiceInfo("http-alt", "TCP", "web", description="HTTP alternate"),
    8080: ServiceInfo("http-proxy", "TCP", "web", description="HTTP proxy/alternate"),
    8443: ServiceInfo("https-alt", "TCP", "web", encrypted=True, description="HTTPS alternate"),
    8883: ServiceInfo("mqtt-tls", "TCP", "messaging", encrypted=True, description="MQTT over TLS"),
    9000: ServiceInfo("portainer", "TCP", "container", description="Portainer"),
    9090: ServiceInfo("prometheus", "TCP", "monitoring", description="Prometheus"),
    9092: ServiceInfo("kafka", "TCP", "messaging", description="Apache Kafka"),
    9200: ServiceInfo("elasticsearch", "TCP", "search", description="Elasticsearch HTTP"),
    9300: ServiceInfo("elasticsearch-transport", "TCP", "search", description="Elasticsearch Transport"),
    10250: ServiceInfo("kubelet", "TCP", "container", description="Kubernetes Kubelet"),
    11211: ServiceInfo("memcached", "TCP", "cache", description="Memcached"),
    15672: ServiceInfo("rabbitmq-mgmt", "TCP", "messaging", description="RabbitMQ Management"),
    27017: ServiceInfo("mongodb", "TCP", "database", description="MongoDB"),
}


class ProtocolResolver:
    """Resolve port numbers to service information."""

    def __init__(self) -> None:
        """Initialize protocol resolver."""
        self._ports = WELL_KNOWN_PORTS
        self._custom_ports: dict[int, ServiceInfo] = {}

    def add_custom_port(
        self,
        port: int,
        service_info: ServiceInfo,
    ) -> None:
        """Add custom port mapping.

        Args:
            port: Port number.
            service_info: Service information.
        """
        self._custom_ports[port] = service_info

    def resolve(
        self,
        port: int,
        protocol: int | None = None,
    ) -> ServiceInfo | None:
        """Resolve port to service information.

        Args:
            port: Port number.
            protocol: IP protocol (6=TCP, 17=UDP). Used for filtering.

        Returns:
            ServiceInfo if known, None otherwise.
        """
        # Check custom ports first
        if port in self._custom_ports:
            return self._custom_ports[port]

        # Check well-known ports
        if port in self._ports:
            info = self._ports[port]

            # Filter by protocol if specified
            if protocol is not None:
                proto_str = "TCP" if protocol == 6 else "UDP" if protocol == 17 else None
                if proto_str and info.protocol != "BOTH" and info.protocol != proto_str:
                    return None

            return info

        return None

    def get_service_name(
        self,
        port: int,
        protocol: int | None = None,
    ) -> str | None:
        """Get service name for a port.

        Args:
            port: Port number.
            protocol: IP protocol number.

        Returns:
            Service name if known.
        """
        info = self.resolve(port, protocol)
        return info.name if info else None

    def get_category(
        self,
        port: int,
        protocol: int | None = None,
    ) -> str | None:
        """Get service category for a port.

        Args:
            port: Port number.
            protocol: IP protocol number.

        Returns:
            Category if known.
        """
        info = self.resolve(port, protocol)
        return info.category if info else None

    def is_encrypted(
        self,
        port: int,
        protocol: int | None = None,
    ) -> bool:
        """Check if port typically uses encryption.

        Args:
            port: Port number.
            protocol: IP protocol number.

        Returns:
            True if typically encrypted.
        """
        info = self.resolve(port, protocol)
        return info.encrypted if info else False

    def infer_service_type(
        self,
        port: int,
        protocol: int,
    ) -> str:
        """Infer a service type string for a port.

        Returns a reasonable guess even for unknown ports.

        Args:
            port: Port number.
            protocol: IP protocol number.

        Returns:
            Service type string.
        """
        info = self.resolve(port, protocol)
        if info:
            return info.name

        # Make educated guesses for unknown ports
        proto_str = "tcp" if protocol == 6 else "udp" if protocol == 17 else "unknown"

        if port < 1024:
            return f"system-{proto_str}-{port}"
        elif port < 49152:
            return f"registered-{proto_str}-{port}"
        else:
            return f"dynamic-{proto_str}-{port}"

    def categorize_traffic(
        self,
        port: int,
        protocol: int,
    ) -> str:
        """Categorize traffic by port into broad categories.

        Args:
            port: Port number.
            protocol: IP protocol number.

        Returns:
            Category string.
        """
        info = self.resolve(port, protocol)
        if info:
            return info.category

        # Guess based on port range
        if port in (80, 443, 8080, 8443):
            return "web"
        elif port in (3306, 5432, 1433, 27017):
            return "database"
        elif port in (6379, 11211):
            return "cache"
        elif port < 1024:
            return "infrastructure"
        else:
            return "application"
