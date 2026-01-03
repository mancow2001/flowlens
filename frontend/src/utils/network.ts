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
 * Check if a port is an ephemeral/dynamic port.
 * Ephemeral ports are temporary ports assigned by the OS for client-side connections.
 * These are typically in the range 32768-65535 (Linux) or 49152-65535 (IANA).
 * We use 10000 as a threshold to also catch common high ports that aren't well-known services.
 * @param port - Port number
 * @returns True if the port is likely an ephemeral port
 */
export function isEphemeralPort(port: number): boolean {
  // If the port is in our known services list, it's not ephemeral
  if (PORT_SERVICES[port]) {
    return false;
  }
  // Consider ports > 10000 as ephemeral unless they're known services
  return port > 10000;
}

/**
 * Get a meaningful label for an edge based on port.
 * Returns service name for well-known ports, port number for other recognized ports,
 * or empty string for ephemeral ports.
 * @param port - Port number
 * @returns Label string or empty string for ephemeral ports
 */
export function getEdgeLabelForPort(port: number): string {
  if (!port || port === 0) {
    return '';
  }

  // Check for known service name first
  const service = PORT_SERVICES[port];
  if (service) {
    return service.toLowerCase();
  }

  // Filter out ephemeral ports - they're not meaningful to display
  if (isEphemeralPort(port)) {
    return '';
  }

  // For other low ports without a known service, show the port number
  return port.toString();
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
