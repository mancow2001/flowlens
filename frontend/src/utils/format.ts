import { format, formatDistanceToNow, parseISO } from 'date-fns';

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? parseISO(date) : date;
  return format(d, 'MMM d, yyyy');
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? parseISO(date) : date;
  return format(d, 'MMM d, yyyy HH:mm:ss');
}

export function formatRelativeTime(date: string | Date): string {
  const d = typeof date === 'string' ? parseISO(date) : date;
  return formatDistanceToNow(d, { addSuffix: true });
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${units[i]}`;
}

export function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M`;
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}K`;
  }
  return num.toLocaleString();
}

export function formatProtocol(protocol: number): string {
  const protocols: Record<number, string> = {
    1: 'ICMP',
    6: 'TCP',
    17: 'UDP',
    47: 'GRE',
    50: 'ESP',
    51: 'AH',
    58: 'ICMPv6',
    89: 'OSPF',
    132: 'SCTP',
  };
  return protocols[protocol] || `Proto ${protocol}`;
}

export function formatPort(port: number, _protocol?: number): string {
  const wellKnownPorts: Record<number, string> = {
    20: 'FTP-DATA',
    21: 'FTP',
    22: 'SSH',
    23: 'Telnet',
    25: 'SMTP',
    53: 'DNS',
    80: 'HTTP',
    110: 'POP3',
    143: 'IMAP',
    443: 'HTTPS',
    465: 'SMTPS',
    587: 'SMTP',
    993: 'IMAPS',
    995: 'POP3S',
    1433: 'MSSQL',
    1521: 'Oracle',
    3306: 'MySQL',
    3389: 'RDP',
    5432: 'PostgreSQL',
    5672: 'AMQP',
    6379: 'Redis',
    8080: 'HTTP-Alt',
    8443: 'HTTPS-Alt',
    9092: 'Kafka',
    27017: 'MongoDB',
  };

  const name = wellKnownPorts[port];
  if (name) {
    return `${port} (${name})`;
  }
  return port.toString();
}

export function getSeverityColor(severity: string): string {
  const colors: Record<string, string> = {
    critical: 'bg-red-600',
    error: 'bg-orange-500',
    warning: 'bg-yellow-500',
    info: 'bg-blue-500',
  };
  return colors[severity] || 'bg-gray-500';
}

export function getAssetTypeIcon(type: string): string {
  const icons: Record<string, string> = {
    server: 'HiServer',
    database: 'HiDatabase',
    workstation: 'HiDesktopComputer',
    network_device: 'HiChip',
    load_balancer: 'HiSwitchHorizontal',
    firewall: 'HiShieldCheck',
    container: 'HiCube',
    cloud_service: 'HiCloud',
    external: 'HiGlobe',
    unknown: 'HiQuestionMarkCircle',
  };
  return icons[type] || icons.unknown;
}
