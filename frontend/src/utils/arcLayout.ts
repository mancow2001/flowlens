/**
 * Arc layout utilities for D3 sunburst/partition visualization.
 * Converts folder hierarchy to D3-compatible layout for arc rendering.
 */

import * as d3 from 'd3';
import type {
  ArcTopologyData,
  FolderTreeNode,
  ApplicationInFolder,
  ArcDependency,
} from '../types';

// Types for arc layout
export interface ArcNode {
  id: string;
  name: string;
  displayName: string | null;
  type: 'root' | 'folder' | 'application';
  color: string | null;
  depth: number;
  parent: ArcNode | null;
  children: ArcNode[];
  data: FolderTreeNode | ApplicationInFolder | null;
  // D3 partition layout values (set after layout)
  x0?: number;
  x1?: number;
  y0?: number;
  y1?: number;
  value?: number;
}

export interface ArcLayoutConfig {
  innerRadius: number;
  outerRadius: number;
  padAngle: number;
  cornerRadius: number;
}

export interface ArcSegment {
  node: ArcNode;
  startAngle: number;
  endAngle: number;
  innerRadius: number;
  outerRadius: number;
  centroid: [number, number];
}

// Default colors for folders without explicit color
const DEFAULT_FOLDER_COLORS = [
  '#2563eb', // blue
  '#16a34a', // green
  '#dc2626', // red
  '#9333ea', // purple
  '#ea580c', // orange
  '#0891b2', // cyan
  '#4f46e5', // indigo
  '#be185d', // pink
];

/**
 * Convert folder tree to flat arc node structure for D3.
 */
export function buildArcHierarchy(data: ArcTopologyData): d3.HierarchyNode<ArcNode> {
  // Create root node
  const root: ArcNode = {
    id: 'root',
    name: 'All',
    displayName: 'All Applications',
    type: 'root',
    color: null,
    depth: 0,
    parent: null,
    children: [],
    data: null,
  };

  let colorIndex = 0;

  function processFolderNode(
    folder: FolderTreeNode,
    parent: ArcNode,
    depth: number
  ): ArcNode {
    const folderColor = folder.color || DEFAULT_FOLDER_COLORS[colorIndex++ % DEFAULT_FOLDER_COLORS.length];

    const node: ArcNode = {
      id: folder.id,
      name: folder.name,
      displayName: folder.display_name,
      type: 'folder',
      color: folderColor,
      depth,
      parent,
      children: [],
      data: folder,
    };

    // Add child folders
    for (const child of folder.children) {
      const childNode = processFolderNode(child, node, depth + 1);
      node.children.push(childNode);
    }

    // Add applications as leaf nodes
    for (const app of folder.applications) {
      const appNode: ArcNode = {
        id: app.id,
        name: app.name,
        displayName: app.display_name,
        type: 'application',
        color: folderColor, // Inherit folder color
        depth: depth + 1,
        parent: node,
        children: [],
        data: app,
      };
      node.children.push(appNode);
    }

    return node;
  }

  // Process root folders
  for (const folder of data.hierarchy.roots) {
    const folderNode = processFolderNode(folder, root, 1);
    root.children.push(folderNode);
  }

  // Create D3 hierarchy
  const hierarchy = d3.hierarchy(root)
    .sum(d => d.type === 'application' ? 1 : 0)
    .sort((a, b) => (b.value || 0) - (a.value || 0));

  return hierarchy;
}

/**
 * Apply partition layout to hierarchy.
 */
export function applyPartitionLayout(
  hierarchy: d3.HierarchyNode<ArcNode>,
  config: ArcLayoutConfig
): d3.HierarchyRectangularNode<ArcNode> {
  const partition = d3.partition<ArcNode>()
    .size([2 * Math.PI, config.outerRadius - config.innerRadius]);

  return partition(hierarchy);
}

/**
 * Create D3 arc generator.
 */
export function createArcGenerator(config: ArcLayoutConfig) {
  return d3.arc<d3.HierarchyRectangularNode<ArcNode>>()
    .startAngle(d => d.x0!)
    .endAngle(d => d.x1!)
    .padAngle(d => Math.min((d.x1! - d.x0!) / 2, config.padAngle))
    .innerRadius(d => config.innerRadius + d.y0!)
    .outerRadius(d => config.innerRadius + d.y1! - 1)
    .cornerRadius(config.cornerRadius);
}

/**
 * Calculate arc centroid for connection endpoints.
 */
export function getArcCentroid(
  node: d3.HierarchyRectangularNode<ArcNode>,
  config: ArcLayoutConfig
): [number, number] {
  const angle = (node.x0! + node.x1!) / 2;
  const radius = config.innerRadius + (node.y0! + node.y1!) / 2;
  return [
    Math.cos(angle - Math.PI / 2) * radius,
    Math.sin(angle - Math.PI / 2) * radius,
  ];
}

/**
 * Check if a point is inside an arc segment.
 */
export function isPointInArc(
  x: number,
  y: number,
  node: d3.HierarchyRectangularNode<ArcNode>,
  config: ArcLayoutConfig
): boolean {
  const angle = Math.atan2(y, x) + Math.PI / 2;
  const normalizedAngle = angle < 0 ? angle + 2 * Math.PI : angle;
  const radius = Math.sqrt(x * x + y * y);

  const innerR = config.innerRadius + node.y0!;
  const outerR = config.innerRadius + node.y1!;

  return (
    normalizedAngle >= node.x0! &&
    normalizedAngle <= node.x1! &&
    radius >= innerR &&
    radius <= outerR
  );
}

/**
 * Find node at point for hit testing.
 */
export function findNodeAtPoint(
  x: number,
  y: number,
  nodes: d3.HierarchyRectangularNode<ArcNode>[],
  config: ArcLayoutConfig
): d3.HierarchyRectangularNode<ArcNode> | null {
  // Check in reverse order (children rendered on top)
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i];
    if (node.data.type !== 'root' && isPointInArc(x, y, node, config)) {
      return node;
    }
  }
  return null;
}

/**
 * Generate curved bezier path between two arc centroids.
 */
export function createConnectionPath(
  source: [number, number],
  target: [number, number]
): string {
  // Calculate control points for smooth curve through center
  const dx = target[0] - source[0];
  const dy = target[1] - source[1];

  // Control point offset (curve through near-center)
  const controlStrength = 0.3;
  const cx = source[0] + dx * 0.5 - dy * controlStrength;
  const cy = source[1] + dy * 0.5 + dx * controlStrength;

  return `M ${source[0]},${source[1]} Q ${cx},${cy} ${target[0]},${target[1]}`;
}

/**
 * Map dependencies to visual connections between arc nodes.
 */
export interface VisualConnection {
  id: string;
  sourceId: string;
  targetId: string;
  sourceName: string;
  targetName: string;
  connectionCount: number;
  bytesTotal: number;
  path: string;
  opacity: number;
  strokeWidth: number;
}

export function mapDependenciesToConnections(
  dependencies: ArcDependency[],
  nodes: d3.HierarchyRectangularNode<ArcNode>[],
  config: ArcLayoutConfig
): VisualConnection[] {
  const nodeMap = new Map<string, d3.HierarchyRectangularNode<ArcNode>>();
  nodes.forEach(n => nodeMap.set(n.data.id, n));

  const maxBytes = Math.max(...dependencies.map(d => d.bytes_total), 1);

  return dependencies
    .map(dep => {
      const sourceNode = nodeMap.get(dep.source_app_id);
      const targetNode = nodeMap.get(dep.target_app_id);

      if (!sourceNode || !targetNode) return null;

      const sourceCentroid = getArcCentroid(sourceNode, config);
      const targetCentroid = getArcCentroid(targetNode, config);
      const path = createConnectionPath(sourceCentroid, targetCentroid);

      // Scale stroke width by bytes (1-5 range)
      const normalizedBytes = dep.bytes_total / maxBytes;
      const strokeWidth = 1 + normalizedBytes * 4;
      const opacity = 0.3 + normalizedBytes * 0.5;

      return {
        id: `${dep.source_app_id}-${dep.target_app_id}`,
        sourceId: dep.source_app_id,
        targetId: dep.target_app_id,
        sourceName: dep.source_app_name,
        targetName: dep.target_app_name,
        connectionCount: dep.connection_count,
        bytesTotal: dep.bytes_total,
        path,
        opacity,
        strokeWidth,
      };
    })
    .filter((c): c is VisualConnection => c !== null);
}

/**
 * Get ancestors of a node for breadcrumb/focus path.
 */
export function getAncestors(node: d3.HierarchyRectangularNode<ArcNode>): d3.HierarchyRectangularNode<ArcNode>[] {
  const ancestors: d3.HierarchyRectangularNode<ArcNode>[] = [];
  let current: d3.HierarchyRectangularNode<ArcNode> | null = node;
  while (current) {
    ancestors.unshift(current);
    current = current.parent;
  }
  return ancestors;
}

/**
 * Get descendants of a node (for focus mode).
 */
export function getDescendants(node: d3.HierarchyRectangularNode<ArcNode>): d3.HierarchyRectangularNode<ArcNode>[] {
  return node.descendants();
}

/**
 * Check if a point is near a bezier curve path.
 * Uses sampling along the curve to find the closest point.
 */
export function isPointNearConnection(
  x: number,
  y: number,
  connection: VisualConnection,
  threshold: number = 15
): boolean {
  // Parse the path to get the control points
  // Path format: "M x1,y1 Q cx,cy x2,y2"
  // Use a more flexible regex that handles various number formats
  const pathMatch = connection.path.match(/M\s*([-\d.e+]+)[,\s]+([-\d.e+]+)\s*Q\s*([-\d.e+]+)[,\s]+([-\d.e+]+)\s*([-\d.e+]+)[,\s]+([-\d.e+]+)/i);
  if (!pathMatch) {
    return false;
  }

  const x1 = parseFloat(pathMatch[1]);
  const y1 = parseFloat(pathMatch[2]);
  const cx = parseFloat(pathMatch[3]);
  const cy = parseFloat(pathMatch[4]);
  const x2 = parseFloat(pathMatch[5]);
  const y2 = parseFloat(pathMatch[6]);

  // Sample points along the quadratic bezier curve
  const samples = 30;
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    // Quadratic bezier formula: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
    const px = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2;
    const py = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2;

    const dist = Math.sqrt((x - px) * (x - px) + (y - py) * (y - py));
    if (dist < threshold) {
      return true;
    }
  }
  return false;
}

/**
 * Find connection at point for hit testing.
 */
export function findConnectionAtPoint(
  x: number,
  y: number,
  connections: VisualConnection[],
  threshold: number = 15
): VisualConnection | null {
  // Check connections in reverse order (last drawn = on top)
  for (let i = connections.length - 1; i >= 0; i--) {
    if (isPointNearConnection(x, y, connections[i], threshold)) {
      return connections[i];
    }
  }
  return null;
}

/**
 * Format bytes to human-readable string.
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * Get protocol name from number.
 */
export function getProtocolName(protocol: number): string {
  switch (protocol) {
    case 6: return 'TCP';
    case 17: return 'UDP';
    case 1: return 'ICMP';
    default: return `Proto ${protocol}`;
  }
}
