/**
 * Asset type configuration for UI components.
 *
 * Provides consistent labels, colors, icons, and grouping for all asset types.
 */

import { AssetType } from '@/types';

export interface AssetTypeConfig {
  label: string;
  color: string;
  icon: string; // Heroicon name
  group: string;
}

/**
 * Groups for organizing asset types in dropdowns and filters.
 */
export const ASSET_TYPE_GROUPS = [
  'Compute',
  'Data',
  'Network',
  'Network Services',
  'Communication',
  'Security & Access',
  'Endpoints',
  'App Infrastructure',
  'Other',
] as const;

export type AssetTypeGroup = (typeof ASSET_TYPE_GROUPS)[number];

/**
 * Asset types organized by group for grouped dropdowns.
 */
export const ASSET_TYPES_BY_GROUP: Record<AssetTypeGroup, AssetType[]> = {
  Compute: ['server', 'workstation', 'virtual_machine', 'container', 'cloud_service'],
  Data: ['database', 'storage'],
  Network: ['network_device', 'load_balancer', 'router', 'switch', 'firewall'],
  'Network Services': ['dns_server', 'dhcp_server', 'ntp_server', 'directory_service'],
  Communication: ['mail_server', 'voip_server'],
  'Security & Access': ['vpn_gateway', 'proxy_server', 'log_collector', 'remote_access'],
  Endpoints: ['printer', 'iot_device', 'ip_camera'],
  'App Infrastructure': ['message_queue', 'monitoring_server'],
  Other: ['unknown', 'group'],
};

/**
 * Configuration for each asset type including label, color, icon, and group.
 */
export const ASSET_TYPE_CONFIG: Record<AssetType, AssetTypeConfig> = {
  // Compute (Green tones)
  server: {
    label: 'Server',
    color: '#10b981',
    icon: 'ServerIcon',
    group: 'Compute',
  },
  workstation: {
    label: 'Workstation',
    color: '#34d399',
    icon: 'ComputerDesktopIcon',
    group: 'Compute',
  },
  virtual_machine: {
    label: 'Virtual Machine',
    color: '#6ee7b7',
    icon: 'CubeIcon',
    group: 'Compute',
  },
  container: {
    label: 'Container',
    color: '#a7f3d0',
    icon: 'CubeTransparentIcon',
    group: 'Compute',
  },
  cloud_service: {
    label: 'Cloud Service',
    color: '#059669',
    icon: 'CloudIcon',
    group: 'Compute',
  },

  // Data (Cyan tones)
  database: {
    label: 'Database',
    color: '#06b6d4',
    icon: 'CircleStackIcon',
    group: 'Data',
  },
  storage: {
    label: 'Storage',
    color: '#22d3ee',
    icon: 'ArchiveBoxIcon',
    group: 'Data',
  },

  // Network (Indigo tones)
  network_device: {
    label: 'Network Device',
    color: '#6366f1',
    icon: 'SignalIcon',
    group: 'Network',
  },
  load_balancer: {
    label: 'Load Balancer',
    color: '#818cf8',
    icon: 'ScaleIcon',
    group: 'Network',
  },
  router: {
    label: 'Router',
    color: '#a5b4fc',
    icon: 'ArrowsRightLeftIcon',
    group: 'Network',
  },
  switch: {
    label: 'Switch',
    color: '#c7d2fe',
    icon: 'RectangleGroupIcon',
    group: 'Network',
  },
  firewall: {
    label: 'Firewall',
    color: '#4f46e5',
    icon: 'ShieldExclamationIcon',
    group: 'Network',
  },

  // Network Services (Blue tones)
  dns_server: {
    label: 'DNS Server',
    color: '#3b82f6',
    icon: 'GlobeAltIcon',
    group: 'Network Services',
  },
  dhcp_server: {
    label: 'DHCP Server',
    color: '#60a5fa',
    icon: 'WifiIcon',
    group: 'Network Services',
  },
  ntp_server: {
    label: 'NTP Server',
    color: '#93c5fd',
    icon: 'ClockIcon',
    group: 'Network Services',
  },
  directory_service: {
    label: 'Directory Service',
    color: '#2563eb',
    icon: 'UserGroupIcon',
    group: 'Network Services',
  },

  // Communication (Purple tones)
  mail_server: {
    label: 'Mail Server',
    color: '#8b5cf6',
    icon: 'EnvelopeIcon',
    group: 'Communication',
  },
  voip_server: {
    label: 'VoIP Server',
    color: '#a78bfa',
    icon: 'PhoneIcon',
    group: 'Communication',
  },

  // Security & Access (Red/Orange tones)
  vpn_gateway: {
    label: 'VPN Gateway',
    color: '#ef4444',
    icon: 'ShieldCheckIcon',
    group: 'Security & Access',
  },
  proxy_server: {
    label: 'Proxy Server',
    color: '#f97316',
    icon: 'ArrowsRightLeftIcon',
    group: 'Security & Access',
  },
  log_collector: {
    label: 'Log Collector',
    color: '#fb923c',
    icon: 'DocumentTextIcon',
    group: 'Security & Access',
  },
  remote_access: {
    label: 'Remote Access',
    color: '#dc2626',
    icon: 'ComputerDesktopIcon',
    group: 'Security & Access',
  },

  // Endpoints (Gray/Slate tones)
  printer: {
    label: 'Printer',
    color: '#64748b',
    icon: 'PrinterIcon',
    group: 'Endpoints',
  },
  iot_device: {
    label: 'IoT Device',
    color: '#94a3b8',
    icon: 'CpuChipIcon',
    group: 'Endpoints',
  },
  ip_camera: {
    label: 'IP Camera',
    color: '#475569',
    icon: 'VideoCameraIcon',
    group: 'Endpoints',
  },

  // App Infrastructure (Amber tones)
  message_queue: {
    label: 'Message Queue',
    color: '#f59e0b',
    icon: 'QueueListIcon',
    group: 'App Infrastructure',
  },
  monitoring_server: {
    label: 'Monitoring Server',
    color: '#fbbf24',
    icon: 'ChartBarIcon',
    group: 'App Infrastructure',
  },

  // Special
  group: {
    label: 'Group',
    color: '#9ca3af',
    icon: 'FolderIcon',
    group: 'Other',
  },
  unknown: {
    label: 'Unknown',
    color: '#9ca3af',
    icon: 'QuestionMarkCircleIcon',
    group: 'Other',
  },
};

/**
 * Get the display label for an asset type.
 */
export function getAssetTypeLabel(type: AssetType): string {
  return ASSET_TYPE_CONFIG[type]?.label ?? type;
}

/**
 * Get the color for an asset type.
 */
export function getAssetTypeColor(type: AssetType): string {
  return ASSET_TYPE_CONFIG[type]?.color ?? '#9ca3af';
}

/**
 * Get all asset types as a flat array with labels (for simple dropdowns).
 */
export function getAssetTypeOptions(): { value: AssetType; label: string }[] {
  return Object.entries(ASSET_TYPE_CONFIG)
    .filter(([type]) => type !== 'group') // Exclude 'group' from selection
    .map(([type, config]) => ({
      value: type as AssetType,
      label: config.label,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Get asset types grouped by category (for grouped dropdowns).
 */
export function getGroupedAssetTypeOptions(): {
  group: AssetTypeGroup;
  options: { value: AssetType; label: string }[];
}[] {
  return ASSET_TYPE_GROUPS.filter((group) => group !== 'Other').map((group) => ({
    group,
    options: ASSET_TYPES_BY_GROUP[group]
      .filter((type) => type !== 'group')
      .map((type) => ({
        value: type,
        label: ASSET_TYPE_CONFIG[type].label,
      })),
  }));
}

/**
 * List of all classifiable asset types (excludes 'unknown' and 'group').
 */
export const CLASSIFIABLE_ASSET_TYPES: AssetType[] = Object.keys(ASSET_TYPE_CONFIG)
  .filter((type) => type !== 'unknown' && type !== 'group')
  .sort((a, b) => getAssetTypeLabel(a as AssetType).localeCompare(getAssetTypeLabel(b as AssetType))) as AssetType[];
