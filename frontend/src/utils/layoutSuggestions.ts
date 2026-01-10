/**
 * Layout Suggestions Utility
 *
 * Generates 3 different layout options with semantic groupings:
 * 1. By Function - Groups by service type (databases, web servers, etc.)
 * 2. By Network - Groups by IP subnet
 * 3. By Communication - Clusters by traffic patterns
 */

import type { LayoutSuggestion, SuggestedGroup } from '../types';

// Node interface for layout calculations
interface LayoutNode {
  id: string;
  name?: string;
  ip_address?: string;
  asset_type?: string;
  is_internal?: boolean;
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
  'External': 0,
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
 * Generate 3 layout suggestions with different grouping strategies
 */
export function generateLayoutSuggestions(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  canvasWidth: number = 1200,
  canvasHeight: number = 800
): LayoutSuggestion[] {
  // Filter to only include real asset nodes (valid UUIDs)
  const assetNodes = nodes.filter(n => isAssetNode(n.id));

  return [
    generateFunctionalLayout(nodes, edges, canvasWidth, canvasHeight, assetNodes),
    generateNetworkLayout(nodes, edges, canvasWidth, canvasHeight, assetNodes),
    generateCommunicationLayout(nodes, edges, canvasWidth, canvasHeight, assetNodes),
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
  assetNodes: LayoutNode[]
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

  // Assign each asset node to a functional group (only real assets, not client summaries)
  const groupAssignments = new Map<string, string>();

  assetNodes.forEach(node => {
    // Check if external
    if (node.is_internal === false) {
      groupAssignments.set(node.id, 'External');
      return;
    }

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
 * Groups assets by their IP subnet
 */
function generateNetworkLayout(
  _nodes: LayoutNode[],
  _edges: LayoutEdge[],
  canvasWidth: number,
  canvasHeight: number,
  assetNodes: LayoutNode[]
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

  // Group asset nodes by subnet (only real assets, not client summaries)
  const subnetGroups = new Map<string, string[]>();

  assetNodes.forEach(node => {
    // External nodes get their own group
    if (node.is_internal === false) {
      if (!subnetGroups.has('External')) {
        subnetGroups.set('External', []);
      }
      subnetGroups.get('External')!.push(node.id);
      return;
    }

    const subnet = getSubnet(node.ip_address);
    if (!subnetGroups.has(subnet)) {
      subnetGroups.set(subnet, []);
    }
    subnetGroups.get(subnet)!.push(node.id);
  });

  // Sort subnets (External first, then by IP)
  const sortedSubnets = Array.from(subnetGroups.keys()).sort((a, b) => {
    if (a === 'External') return -1;
    if (b === 'External') return 1;
    if (a === 'Unknown') return 1;
    if (b === 'Unknown') return -1;
    return a.localeCompare(b);
  });

  // Create groups with colors
  const groups: SuggestedGroup[] = sortedSubnets.map((subnet, index) => ({
    id: `net-${subnet.replace(/\./g, '-').replace(/x/g, '0')}`,
    name: subnet === 'External' ? 'External Network' : `Subnet ${subnet}`,
    color: GROUP_COLORS[index % GROUP_COLORS.length],
    asset_ids: subnetGroups.get(subnet) || [],
  }));

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
  assetNodes: LayoutNode[]
): LayoutSuggestion {
  // Create a set of valid asset IDs for filtering
  const assetNodeIds = new Set(assetNodes.map(n => n.id));

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

    // Check if all external
    if (clusterNodes.every(n => n.is_internal === false)) {
      return 'External Services';
    }

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
    asset_ids: cluster.filter(id => assetNodeIds.has(id)),
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
