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
  20: 'FTP-DATA',
  21: 'FTP',
  22: 'SSH',
  23: 'Telnet',
  25: 'SMTP',
  53: 'DNS',
  67: 'DHCP',
  68: 'DHCP',
  80: 'HTTP',
  110: 'POP3',
  123: 'NTP',
  143: 'IMAP',
  161: 'SNMP',
  162: 'SNMP-Trap',
  389: 'LDAP',
  443: 'HTTPS',
  445: 'SMB',
  465: 'SMTPS',
  514: 'Syslog',
  636: 'LDAPS',
  993: 'IMAPS',
  995: 'POP3S',
  1433: 'MSSQL',
  1521: 'Oracle',
  3306: 'MySQL',
  3389: 'RDP',
  5432: 'PostgreSQL',
  5672: 'AMQP',
  5900: 'VNC',
  6379: 'Redis',
  6443: 'K8s API',
  8080: 'HTTP-Alt',
  8443: 'HTTPS-Alt',
  9000: 'SonarQube',
  9090: 'Prometheus',
  9200: 'Elasticsearch',
  9300: 'ES Transport',
  11211: 'Memcached',
  27017: 'MongoDB',
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

/**
 * Format bytes to human-readable string.
 * @param bytes - Number of bytes
 * @returns Formatted string (e.g., "1.5 GB", "256 KB")
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  if (i === 0) return `${bytes} ${units[0]}`;

  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[i]}`;
}
