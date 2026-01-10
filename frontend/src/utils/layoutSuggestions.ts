/**
 * Layout Suggestions Utility
 *
 * Generates 3 different layout options with semantic groupings:
 * 1. By Function - Groups by service type (databases, web servers, etc.)
 * 2. By Network - Groups by IP subnet
 * 3. By Communication - Clusters by traffic patterns
 */

import type { LayoutSuggestion, SuggestedGroup } from '../types';

// Classification rule for naming network groups
export interface ClassificationRuleForLayout {
  name: string;
  cidr: string;
  priority: number;
}

// Node interface for layout calculations
interface LayoutNode {
  id: string;
  name?: string;
  ip_address?: string;
  asset_type?: string;
  is_internal?: boolean;
  is_entry_point?: boolean;
  is_client_summary?: boolean;
  x?: number;
  y?: number;
}

// Edge interface for layout calculations
interface LayoutEdge {
  source: string | LayoutNode;
  target: string | LayoutNode;
  port?: number;
  total_bytes?: number;
  flow_count?: number;
}

// Port to function mapping for service type inference
const PORT_FUNCTIONS: Record<number, string> = {
  // Databases
  3306: 'Databases',
  5432: 'Databases',
  27017: 'Databases',
  1433: 'Databases',
  1521: 'Databases',
  9042: 'Databases',
  5984: 'Databases',
  7474: 'Databases',
  8529: 'Databases',
  // Caches
  6379: 'Caches',
  11211: 'Caches',
  // Web Servers
  80: 'Web Servers',
  443: 'Web Servers',
  8080: 'Web Servers',
  8443: 'Web Servers',
  3000: 'Web Servers',
  5000: 'Web Servers',
  // Load Balancers / Proxies
  8081: 'Load Balancers',
  8082: 'Load Balancers',
  // Message Queues
  5672: 'Message Queues',
  5671: 'Message Queues',
  9092: 'Message Queues',
  61616: 'Message Queues',
  // Search Engines
  9200: 'Search',
  9300: 'Search',
  8983: 'Search',
  // Monitoring
  9090: 'Monitoring',
  3100: 'Monitoring',
  9411: 'Monitoring',
  // SSH/Admin
  22: 'Infrastructure',
  // DNS
  53: 'Infrastructure',
};

// Color palette for groups
const GROUP_COLORS = [
  '#3B82F6', // blue
  '#10B981', // emerald
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // violet
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#84CC16', // lime
  '#F97316', // orange
  '#6366F1', // indigo
];

// Function tier ordering (bottom to top in horizontal layout)
const FUNCTION_TIER_ORDER: Record<string, number> = {
  'Infrastructure': 1,
  'Databases': 2,
  'Caches': 3,
  'Message Queues': 4,
  'Search': 5,
  'Application Servers': 6,
  'Monitoring': 7,
  'Load Balancers': 8,
  'Web Servers': 9,
};

// UUID regex to identify real asset IDs vs synthetic IDs (like client-summary-...)
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Check if a node ID is a valid UUID (i.e., a real asset)
 */
function isAssetNode(nodeId: string): boolean {
  return UUID_REGEX.test(nodeId);
}

/**
 * Check if a node should be included in groups
 * Excludes: entry points, client summaries, external assets, and non-UUID nodes
 */
function isGroupableNode(node: LayoutNode): boolean {
  if (!isAssetNode(node.id)) return false;
  if (node.is_entry_point) return false;
  if (node.is_client_summary) return false;
  if (node.is_internal === false) return false; // Exclude external assets
  return true;
}

/**
 * Check if an IP address matches a CIDR block
 */
function ipMatchesCidr(ip: string, cidr: string): boolean {
  const [cidrIp, prefixStr] = cidr.split('/');
  if (!cidrIp || !prefixStr) return false;

  const prefix = parseInt(prefixStr, 10);
  if (isNaN(prefix) || prefix < 0 || prefix > 32) return false;

  const ipParts = ip.split('.').map(p => parseInt(p, 10));
  const cidrParts = cidrIp.split('.').map(p => parseInt(p, 10));

  if (ipParts.length !== 4 || cidrParts.length !== 4) return false;
  if (ipParts.some(p => isNaN(p)) || cidrParts.some(p => isNaN(p))) return false;

  const ipNum = (ipParts[0] << 24) | (ipParts[1] << 16) | (ipParts[2] << 8) | ipParts[3];
  const cidrNum = (cidrParts[0] << 24) | (cidrParts[1] << 16) | (cidrParts[2] << 8) | cidrParts[3];
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;

  return ((ipNum >>> 0) & mask) === ((cidrNum >>> 0) & mask);
}

/**
 * Find the best matching classification rule for an IP address
 */
function findMatchingRule(ip: string, rules: ClassificationRuleForLayout[]): ClassificationRuleForLayout | null {
  // Sort by priority (lower = higher priority) and find first match
  const sortedRules = [...rules].sort((a, b) => a.priority - b.priority);
  for (const rule of sortedRules) {
    if (ipMatchesCidr(ip, rule.cidr)) {
      return rule;
    }
  }
  return null;
}

/**
 * Generate 3 layout suggestions with different grouping strategies
 */
export function generateLayoutSuggestions(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  canvasWidth: number = 1200,
  canvasHeight: number = 800,
  classificationRules: ClassificationRuleForLayout[] = []
): LayoutSuggestion[] {
  // Filter to only include groupable nodes (excludes entry points, client summaries)
  const groupableNodes = nodes.filter(n => isGroupableNode(n));

  return [
    generateFunctionalLayout(nodes, edges, canvasWidth, canvasHeight, groupableNodes),
    generateNetworkLayout(nodes, edges, canvasWidth, canvasHeight, groupableNodes, classificationRules),
    generateCommunicationLayout(nodes, edges, canvasWidth, canvasHeight, groupableNodes),
  ];
}

/**
 * Option 1: Group by Function (Horizontal Layers)
 * Groups assets by their inferred service type based on ports
 */
function generateFunctionalLayout(
  _nodes: LayoutNode[],
  edges: LayoutEdge[],
  canvasWidth: number,
  canvasHeight: number,
  groupableNodes: LayoutNode[]
): LayoutSuggestion {
  // Build a map of node IDs to ports they serve
  const nodePortsServed = new Map<string, Set<number>>();

  edges.forEach(edge => {
    const targetId = typeof edge.target === 'string' ? edge.target : edge.target.id;
    if (edge.port) {
      if (!nodePortsServed.has(targetId)) {
        nodePortsServed.set(targetId, new Set());
      }
      nodePortsServed.get(targetId)!.add(edge.port);
    }
  });

  // Assign each asset node to a functional group (excludes entry points, client summaries, external)
  const groupAssignments = new Map<string, string>();

  groupableNodes.forEach(node => {
    // Check ports served
    const ports = nodePortsServed.get(node.id);
    if (ports) {
      for (const port of ports) {
        const func = PORT_FUNCTIONS[port];
        if (func) {
          groupAssignments.set(node.id, func);
          return;
        }
      }
    }

    // Check asset type
    if (node.asset_type) {
      const type = node.asset_type.toLowerCase();
      if (type.includes('database') || type.includes('db')) {
        groupAssignments.set(node.id, 'Databases');
        return;
      }
      if (type.includes('cache') || type.includes('redis')) {
        groupAssignments.set(node.id, 'Caches');
        return;
      }
      if (type.includes('web') || type.includes('http')) {
        groupAssignments.set(node.id, 'Web Servers');
        return;
      }
      if (type.includes('load') || type.includes('balancer') || type.includes('proxy')) {
        groupAssignments.set(node.id, 'Load Balancers');
        return;
      }
    }

    // Default to Application Servers
    groupAssignments.set(node.id, 'Application Servers');
  });

  // Build groups
  const groupMembers = new Map<string, string[]>();
  groupAssignments.forEach((groupName, nodeId) => {
    if (!groupMembers.has(groupName)) {
      groupMembers.set(groupName, []);
    }
    groupMembers.get(groupName)!.push(nodeId);
  });

  // Sort groups by tier order
  const sortedGroupNames = Array.from(groupMembers.keys()).sort(
    (a, b) => (FUNCTION_TIER_ORDER[a] ?? 5) - (FUNCTION_TIER_ORDER[b] ?? 5)
  );

  // Create groups with colors
  const groups: SuggestedGroup[] = sortedGroupNames.map((name, index) => ({
    id: `func-${name.toLowerCase().replace(/\s+/g, '-')}`,
    name,
    color: GROUP_COLORS[index % GROUP_COLORS.length],
    asset_ids: groupMembers.get(name) || [],
  }));

  // Calculate positions (horizontal layers, bottom to top)
  const positions: Record<string, { x: number; y: number }> = {};
  const padding = 100;
  const layerHeight = (canvasHeight - padding * 2) / Math.max(groups.length, 1);

  groups.forEach((group, layerIndex) => {
    const y = canvasHeight - padding - (layerIndex + 0.5) * layerHeight;
    const nodeSpacing = (canvasWidth - padding * 2) / Math.max(group.asset_ids.length + 1, 2);

    group.asset_ids.forEach((nodeId, nodeIndex) => {
      positions[nodeId] = {
        x: padding + (nodeIndex + 1) * nodeSpacing,
        y,
      };
    });

    // Calculate group bounds
    if (group.asset_ids.length > 0) {
      const xs = group.asset_ids.map(id => positions[id].x);
      const minX = Math.min(...xs) - 40;
      const maxX = Math.max(...xs) + 40;
      group.bounds = {
        x: minX,
        y: y - layerHeight / 3,
        width: maxX - minX,
        height: layerHeight * 0.6,
      };
    }
  });

  return {
    id: 'functional',
    name: 'By Function',
    description: 'Groups assets by service type (databases, web servers, caches, etc.) in horizontal layers',
    groups,
    positions,
  };
}

/**
 * Option 2: Group by Network (Vertical Columns)
 * Groups assets by their IP subnet or classification rule name
 */
function generateNetworkLayout(
  _nodes: LayoutNode[],
  _edges: LayoutEdge[],
  canvasWidth: number,
  canvasHeight: number,
  groupableNodes: LayoutNode[],
  classificationRules: ClassificationRuleForLayout[] = []
): LayoutSuggestion {
  // Extract subnet from IP address (first 3 octets)
  const getSubnet = (ip?: string): string => {
    if (!ip) return 'Unknown';
    const parts = ip.split('.');
    if (parts.length >= 3) {
      return `${parts[0]}.${parts[1]}.${parts[2]}.x`;
    }
    return 'Unknown';
  };

  // Get group name for a node - use classification rule name if matched, otherwise subnet
  const getGroupKey = (node: LayoutNode): { key: string; displayName: string } => {
    if (node.ip_address && classificationRules.length > 0) {
      const matchedRule = findMatchingRule(node.ip_address, classificationRules);
      if (matchedRule) {
        return { key: `rule:${matchedRule.name}`, displayName: matchedRule.name };
      }
    }
    const subnet = getSubnet(node.ip_address);
    return { key: `subnet:${subnet}`, displayName: subnet };
  };

  // Group asset nodes by classification rule or subnet
  const networkGroups = new Map<string, { displayName: string; nodeIds: string[] }>();

  groupableNodes.forEach(node => {
    const { key, displayName } = getGroupKey(node);
    if (!networkGroups.has(key)) {
      networkGroups.set(key, { displayName, nodeIds: [] });
    }
    networkGroups.get(key)!.nodeIds.push(node.id);
  });

  // Sort groups: classification rules first (alphabetically), then subnets (by IP), Unknown last
  const sortedKeys = Array.from(networkGroups.keys()).sort((a, b) => {
    const aIsRule = a.startsWith('rule:');
    const bIsRule = b.startsWith('rule:');
    const aIsUnknown = a === 'subnet:Unknown';
    const bIsUnknown = b === 'subnet:Unknown';

    if (aIsUnknown) return 1;
    if (bIsUnknown) return -1;
    if (aIsRule && !bIsRule) return -1;
    if (!aIsRule && bIsRule) return 1;
    return a.localeCompare(b);
  });

  // Create groups with colors
  const groups: SuggestedGroup[] = sortedKeys.map((key, index) => {
    const group = networkGroups.get(key)!;
    return {
      id: `net-${key.replace(/[^a-zA-Z0-9]/g, '-')}`,
      name: group.displayName,
      color: GROUP_COLORS[index % GROUP_COLORS.length],
      asset_ids: group.nodeIds,
    };
  });

  // Calculate positions (vertical columns)
  const positions: Record<string, { x: number; y: number }> = {};
  const padding = 100;
  const columnWidth = (canvasWidth - padding * 2) / Math.max(groups.length, 1);

  groups.forEach((group, colIndex) => {
    const x = padding + (colIndex + 0.5) * columnWidth;
    const nodeSpacing = (canvasHeight - padding * 2) / Math.max(group.asset_ids.length + 1, 2);

    group.asset_ids.forEach((nodeId, nodeIndex) => {
      positions[nodeId] = {
        x,
        y: padding + (nodeIndex + 1) * nodeSpacing,
      };
    });

    // Calculate group bounds
    if (group.asset_ids.length > 0) {
      const ys = group.asset_ids.map(id => positions[id].y);
      const minY = Math.min(...ys) - 40;
      const maxY = Math.max(...ys) + 40;
      group.bounds = {
        x: x - columnWidth / 3,
        y: minY,
        width: columnWidth * 0.6,
        height: maxY - minY,
      };
    }
  });

  return {
    id: 'network',
    name: 'By Network',
    description: 'Groups assets by IP subnet in vertical columns',
    groups,
    positions,
  };
}

/**
 * Option 3: Group by Communication (Radial Clusters)
 * Clusters assets that communicate heavily with each other
 */
function generateCommunicationLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  canvasWidth: number,
  canvasHeight: number,
  groupableNodes: LayoutNode[]
): LayoutSuggestion {
  // Create a set of valid asset IDs for filtering
  const groupableNodeIds = new Set(groupableNodes.map(n => n.id));

  // Build adjacency matrix with weights
  const nodeIds = nodes.map(n => n.id);
  const nodeIndexMap = new Map(nodeIds.map((id, i) => [id, i]));
  const n = nodes.length;

  // Initialize adjacency matrix
  const adjacency: number[][] = Array(n).fill(null).map(() => Array(n).fill(0));

  edges.forEach(edge => {
    const sourceId = typeof edge.source === 'string' ? edge.source : edge.source.id;
    const targetId = typeof edge.target === 'string' ? edge.target : edge.target.id;
    const sourceIdx = nodeIndexMap.get(sourceId);
    const targetIdx = nodeIndexMap.get(targetId);

    if (sourceIdx !== undefined && targetIdx !== undefined) {
      // Weight by traffic volume (bytes) or flow count
      const weight = edge.total_bytes ?? edge.flow_count ?? 1;
      adjacency[sourceIdx][targetIdx] += weight;
      adjacency[targetIdx][sourceIdx] += weight; // Symmetric
    }
  });

  // Simple clustering: group nodes that have high connectivity
  const clusters: string[][] = [];
  const assigned = new Set<string>();

  // Start with nodes that have highest total traffic
  const nodeTotalTraffic = nodes.map((node, idx) => ({
    id: node.id,
    traffic: adjacency[idx].reduce((sum, w) => sum + w, 0),
  })).sort((a, b) => b.traffic - a.traffic);

  nodeTotalTraffic.forEach(({ id }) => {
    if (assigned.has(id)) return;

    const nodeIdx = nodeIndexMap.get(id)!;
    const cluster = [id];
    assigned.add(id);

    // Find nodes that communicate heavily with this one
    const connections = adjacency[nodeIdx]
      .map((weight, idx) => ({ idx, weight }))
      .filter(({ weight }) => weight > 0)
      .sort((a, b) => b.weight - a.weight);

    // Add top connected nodes to cluster (up to 5)
    for (const { idx } of connections.slice(0, 5)) {
      const connectedId = nodeIds[idx];
      if (!assigned.has(connectedId)) {
        cluster.push(connectedId);
        assigned.add(connectedId);
      }
    }

    if (cluster.length > 0) {
      clusters.push(cluster);
    }
  });

  // Add any remaining unassigned nodes
  nodes.forEach(node => {
    if (!assigned.has(node.id)) {
      clusters.push([node.id]);
    }
  });

  // Merge very small clusters (1-2 nodes) into an "Others" cluster
  const significantClusters: string[][] = [];
  const smallNodes: string[] = [];

  clusters.forEach(cluster => {
    if (cluster.length <= 2 && clusters.length > 3) {
      smallNodes.push(...cluster);
    } else {
      significantClusters.push(cluster);
    }
  });

  if (smallNodes.length > 0) {
    significantClusters.push(smallNodes);
  }

  // Name clusters based on their members
  const getClusterName = (cluster: string[], index: number): string => {
    if (cluster.length === 0) return `Cluster ${index + 1}`;

    // Find common characteristics
    const clusterNodes = cluster.map(id => nodes.find(n => n.id === id)).filter(Boolean) as LayoutNode[];

    // Check for common subnet
    const subnets = new Set(clusterNodes.map(n => {
      if (!n.ip_address) return null;
      const parts = n.ip_address.split('.');
      return parts.length >= 3 ? `${parts[0]}.${parts[1]}.${parts[2]}` : null;
    }).filter(Boolean));

    if (subnets.size === 1) {
      return `${Array.from(subnets)[0]}.x Group`;
    }

    // Default naming
    if (index === significantClusters.length - 1 && smallNodes.length > 0) {
      return 'Other Services';
    }

    return `Service Group ${index + 1}`;
  };

  // Create groups with colors (only include valid asset IDs in groups)
  const groups: SuggestedGroup[] = significantClusters.map((cluster, index) => ({
    id: `comm-cluster-${index}`,
    name: getClusterName(cluster, index),
    color: GROUP_COLORS[index % GROUP_COLORS.length],
    asset_ids: cluster.filter(id => groupableNodeIds.has(id)),
  })).filter(g => g.asset_ids.length > 0);

  // Calculate positions (radial layout)
  const positions: Record<string, { x: number; y: number }> = {};
  const centerX = canvasWidth / 2;
  const centerY = canvasHeight / 2;
  const maxRadius = Math.min(canvasWidth, canvasHeight) / 2 - 100;

  if (groups.length === 1) {
    // Single cluster: arrange in circle
    const group = groups[0];
    const angleStep = (2 * Math.PI) / Math.max(group.asset_ids.length, 1);
    group.asset_ids.forEach((nodeId, i) => {
      const angle = i * angleStep - Math.PI / 2;
      positions[nodeId] = {
        x: centerX + maxRadius * 0.6 * Math.cos(angle),
        y: centerY + maxRadius * 0.6 * Math.sin(angle),
      };
    });
  } else {
    // Multiple clusters: arrange clusters radially, nodes within clusters
    const clusterAngleStep = (2 * Math.PI) / groups.length;

    groups.forEach((group, clusterIndex) => {
      const clusterAngle = clusterIndex * clusterAngleStep - Math.PI / 2;
      const clusterCenterX = centerX + maxRadius * 0.5 * Math.cos(clusterAngle);
      const clusterCenterY = centerY + maxRadius * 0.5 * Math.sin(clusterAngle);
      const clusterRadius = Math.min(maxRadius * 0.35, 80 + group.asset_ids.length * 15);

      if (group.asset_ids.length === 1) {
        positions[group.asset_ids[0]] = { x: clusterCenterX, y: clusterCenterY };
      } else {
        const nodeAngleStep = (2 * Math.PI) / group.asset_ids.length;
        group.asset_ids.forEach((nodeId, nodeIndex) => {
          const nodeAngle = nodeIndex * nodeAngleStep;
          positions[nodeId] = {
            x: clusterCenterX + clusterRadius * Math.cos(nodeAngle),
            y: clusterCenterY + clusterRadius * Math.sin(nodeAngle),
          };
        });
      }

      // Calculate group bounds
      if (group.asset_ids.length > 0) {
        const xs = group.asset_ids.map(id => positions[id].x);
        const ys = group.asset_ids.map(id => positions[id].y);
        const minX = Math.min(...xs) - 40;
        const maxX = Math.max(...xs) + 40;
        const minY = Math.min(...ys) - 40;
        const maxY = Math.max(...ys) + 40;
        group.bounds = {
          x: minX,
          y: minY,
          width: maxX - minX,
          height: maxY - minY,
        };
      }
    });
  }

  return {
    id: 'communication',
    name: 'By Communication',
    description: 'Clusters assets that communicate frequently with each other in a radial layout',
    groups,
    positions,
  };
}

export default generateLayoutSuggestions;
