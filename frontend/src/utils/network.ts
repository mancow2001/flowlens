/**
 * Network utility functions for protocol and port handling.
 */

// Protocol number to name mapping (IANA assigned numbers)
const PROTOCOL_NAMES: Record<number, string> = {
  1: 'ICMP',
  2: 'IGMP',
  6: 'TCP',
  17: 'UDP',
  41: 'IPv6',
  47: 'GRE',
  50: 'ESP',
  51: 'AH',
  58: 'ICMPv6',
  89: 'OSPF',
  103: 'PIM',
  112: 'VRRP',
  132: 'SCTP',
};

// Common port to service name mapping
const PORT_SERVICES: Record<number, string> = {
  // File transfer
  20: 'FTP-Data',
  21: 'FTP',
  22: 'SSH',

  // Email
  25: 'SMTP',
  110: 'POP3',
  143: 'IMAP',
  465: 'SMTPS',
  587: 'SMTP-TLS',
  993: 'IMAPS',
  995: 'POP3S',

  // Identity & Auth
  49: 'TACACS',
  88: 'Kerberos',
  389: 'LDAP',
  636: 'LDAPS',
  1812: 'RADIUS',
  1813: 'RADIUS-Acct',

  // Infrastructure core
  53: 'DNS',
  67: 'DHCP',
  68: 'DHCP',
  123: 'NTP',
  161: 'SNMP',
  162: 'SNMP-Trap',
  514: 'Syslog',

  // Web & Edge
  80: 'HTTP',
  443: 'HTTPS',
  3128: 'Proxy',
  8080: 'HTTP-Alt',
  8081: 'Proxy-HTTPS',
  8443: 'HTTPS-Alt',

  // Storage
  445: 'SMB',
  2049: 'NFS',

  // Databases - Relational
  1433: 'MSSQL',
  1434: 'MSSQL-Browser',
  1521: 'Oracle',
  3306: 'MySQL',
  5432: 'PostgreSQL',
  50000: 'DB2',

  // Databases - NoSQL
  6379: 'Redis',
  6380: 'Redis-TLS',
  8091: 'Couchbase',
  9042: 'Cassandra',
  11210: 'Couchbase-Data',
  27017: 'MongoDB',

  // Messaging & Streaming
  1883: 'MQTT',
  2181: 'Zookeeper',
  5671: 'RabbitMQ-TLS',
  5672: 'RabbitMQ',
  8883: 'MQTT-TLS',
  9092: 'Kafka',
  9093: 'Kafka-TLS',

  // Management & Monitoring
  3000: 'Grafana',
  3389: 'RDP',
  5900: 'VNC',
  5985: 'WinRM',
  5986: 'WinRM-TLS',
  9090: 'Prometheus',

  // Virtualization & Containers
  2375: 'Docker',
  2376: 'Docker-TLS',
  2379: 'etcd',
  6443: 'K8s-API',

  // Service Mesh & APIs
  9901: 'Envoy',
  15010: 'Istio',
  50051: 'gRPC',

  // Search & Analytics
  9000: 'MinIO',
  9200: 'Elasticsearch',
  9300: 'ES-Transport',

  // Legacy/Other
  11211: 'Memcached',
};

/**
 * Get human-readable protocol name from protocol number.
 * @param protocol - IANA protocol number (e.g., 6 for TCP, 17 for UDP)
 * @returns Protocol name or "Protocol N" for unknown protocols
 */
export function getProtocolName(protocol: number): string {
  return PROTOCOL_NAMES[protocol] || `Protocol ${protocol}`;
}

/**
 * Get service name for a given port number.
 * @param port - Port number
 * @returns Service name or null if unknown
 */
export function getServiceName(port: number): string | null {
  return PORT_SERVICES[port] || null;
}

/**
 * Format port with optional service name.
 * @param port - Port number
 * @param includeService - Whether to include service name if known
 * @returns Formatted port string (e.g., "443 (HTTPS)" or "8080")
 */
export function formatPort(port: number, includeService: boolean = true): string {
  const service = includeService ? getServiceName(port) : null;
  return service ? `${port} (${service})` : `${port}`;
}

/**
 * Format protocol and port together.
 * @param protocol - Protocol number
 * @param port - Port number
 * @returns Formatted string (e.g., "TCP/443 (HTTPS)")
 */
export function formatProtocolPort(protocol: number, port: number): string {
  const protocolName = getProtocolName(protocol);
  const portStr = formatPort(port);
  return `${protocolName}/${portStr}`;
}

/**
 * Check if the protocol is TCP.
 */
export function isTCP(protocol: number): boolean {
  return protocol === 6;
}

/**
 * Check if the protocol is UDP.
 */
export function isUDP(protocol: number): boolean {
  return protocol === 17;
}

/**
 * Check if the protocol is ICMP.
 */
export function isICMP(protocol: number): boolean {
  return protocol === 1 || protocol === 58; // ICMPv4 or ICMPv6
}

/**
 * Check if a port has a known service name.
 * @param port - Port number
 * @returns True if the port has a known service mapping
 */
export function isKnownServicePort(port: number): boolean {
  return !!PORT_SERVICES[port];
}

/**
 * Get a meaningful label for an edge based on port.
 * Only shows labels for well-known service ports to keep the topology clean.
 * Unknown/ephemeral ports show no label.
 * @param port - Port number
 * @returns Service name for known ports, empty string otherwise
 */
export function getEdgeLabelForPort(port: number): string {
  if (!port || port === 0) {
    return '';
  }

  // Only show labels for known services
  const service = PORT_SERVICES[port];
  return service ? service.toLowerCase() : '';
}

