/**
 * Static Graph Layout Algorithms
 *
 * Pre-computed layouts for large graphs where force simulation is too slow.
 * These algorithms run in O(n) or O(n log n) time.
 */

export interface LayoutNode {
  id: string;
  x?: number;
  y?: number;
  groupKey?: string;
  is_internal?: boolean;
  connections_in?: number;
  connections_out?: number;
}

export interface LayoutEdge {
  source: string;
  target: string;
}

export interface LayoutResult {
  nodes: Map<string, { x: number; y: number }>;
  bounds: { minX: number; minY: number; maxX: number; maxY: number };
}

/**
 * Grid Layout
 * Simple, fast layout arranging nodes in a grid pattern.
 * O(n) time complexity.
 */
export function gridLayout(
  nodes: LayoutNode[],
  width: number,
  height: number,
  options: {
    padding?: number;
    columns?: number;
  } = {}
): LayoutResult {
  const padding = options.padding ?? 50;
  const availableWidth = width - padding * 2;
  const availableHeight = height - padding * 2;

  const columns = options.columns ?? Math.ceil(Math.sqrt(nodes.length));
  const rows = Math.ceil(nodes.length / columns);

  const cellWidth = availableWidth / columns;
  const cellHeight = availableHeight / rows;

  const result = new Map<string, { x: number; y: number }>();

  nodes.forEach((node, i) => {
    const col = i % columns;
    const row = Math.floor(i / columns);

    result.set(node.id, {
      x: padding + cellWidth * (col + 0.5),
      y: padding + cellHeight * (row + 0.5),
    });
  });

  return {
    nodes: result,
    bounds: {
      minX: padding,
      minY: padding,
      maxX: width - padding,
      maxY: height - padding,
    },
  };
}

/**
 * Circular Layout
 * Arranges nodes in a circle. Good for showing relationships.
 * O(n) time complexity.
 */
export function circularLayout(
  nodes: LayoutNode[],
  width: number,
  height: number,
  options: {
    padding?: number;
    startAngle?: number;
    sortBy?: 'none' | 'group' | 'connections';
  } = {}
): LayoutResult {
  const padding = options.padding ?? 50;
  const startAngle = options.startAngle ?? -Math.PI / 2;

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) / 2 - padding;

  // Sort nodes if requested
  let sortedNodes = [...nodes];
  if (options.sortBy === 'group') {
    sortedNodes.sort((a, b) => (a.groupKey ?? '').localeCompare(b.groupKey ?? ''));
  } else if (options.sortBy === 'connections') {
    sortedNodes.sort((a, b) => {
      const aConn = (a.connections_in ?? 0) + (a.connections_out ?? 0);
      const bConn = (b.connections_in ?? 0) + (b.connections_out ?? 0);
      return bConn - aConn;
    });
  }

  const result = new Map<string, { x: number; y: number }>();
  const angleStep = (2 * Math.PI) / sortedNodes.length;

  sortedNodes.forEach((node, i) => {
    const angle = startAngle + angleStep * i;
    result.set(node.id, {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    });
  });

  return {
    nodes: result,
    bounds: {
      minX: centerX - radius,
      minY: centerY - radius,
      maxX: centerX + radius,
      maxY: centerY + radius,
    },
  };
}

/**
 * Grouped Circular Layout
 * Arranges nodes in concentric circles by group.
 * Groups are arranged radially, with group members on arcs.
 */
export function groupedCircularLayout(
  nodes: LayoutNode[],
  width: number,
  height: number,
  options: {
    padding?: number;
    groupSpacing?: number;
  } = {}
): LayoutResult {
  const padding = options.padding ?? 50;
  const groupSpacing = options.groupSpacing ?? 0.1; // Fraction of arc to leave as spacing

  const centerX = width / 2;
  const centerY = height / 2;
  const maxRadius = Math.min(width, height) / 2 - padding;

  // Group nodes
  const groups = new Map<string, LayoutNode[]>();
  nodes.forEach(node => {
    const key = node.groupKey ?? 'default';
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(node);
  });

  const groupKeys = Array.from(groups.keys()).sort();
  const result = new Map<string, { x: number; y: number }>();

  // Calculate arc per group
  const totalArc = 2 * Math.PI;
  const arcPerGroup = totalArc / groupKeys.length;
  const usableArc = arcPerGroup * (1 - groupSpacing);

  groupKeys.forEach((groupKey, groupIndex) => {
    const groupNodes = groups.get(groupKey)!;
    const startAngle = -Math.PI / 2 + groupIndex * arcPerGroup;

    // Distribute nodes along the arc
    if (groupNodes.length === 1) {
      const angle = startAngle + usableArc / 2;
      result.set(groupNodes[0].id, {
        x: centerX + maxRadius * Math.cos(angle),
        y: centerY + maxRadius * Math.sin(angle),
      });
    } else {
      const angleStep = usableArc / (groupNodes.length - 1);
      groupNodes.forEach((node, i) => {
        const angle = startAngle + angleStep * i;
        result.set(node.id, {
          x: centerX + maxRadius * Math.cos(angle),
          y: centerY + maxRadius * Math.sin(angle),
        });
      });
    }
  });

  return {
    nodes: result,
    bounds: {
      minX: centerX - maxRadius,
      minY: centerY - maxRadius,
      maxX: centerX + maxRadius,
      maxY: centerY + maxRadius,
    },
  };
}

/**
 * Hierarchical Layout
 * Arranges nodes in a top-down tree structure.
 * Uses BFS to determine levels based on edges.
 * O(n + e) time complexity.
 */
export function hierarchicalLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  options: {
    padding?: number;
    direction?: 'top-down' | 'left-right';
    levelSpacing?: number;
    nodeSpacing?: number;
  } = {}
): LayoutResult {
  const padding = options.padding ?? 50;
  const direction = options.direction ?? 'top-down';
  const levelSpacing = options.levelSpacing ?? 100;
  const nodeSpacing = options.nodeSpacing ?? 60;

  // Build adjacency lists
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const nodeIds = new Set(nodes.map(n => n.id));

  edges.forEach(e => {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return;

    if (!outgoing.has(e.source)) outgoing.set(e.source, []);
    if (!incoming.has(e.target)) incoming.set(e.target, []);
    outgoing.get(e.source)!.push(e.target);
    incoming.get(e.target)!.push(e.source);
  });

  // Find root nodes (nodes with no incoming edges)
  const roots = nodes.filter(n => !incoming.has(n.id) || incoming.get(n.id)!.length === 0);

  // If no clear roots, use nodes with most outgoing connections
  if (roots.length === 0) {
    const sorted = [...nodes].sort((a, b) => {
      const aOut = outgoing.get(a.id)?.length ?? 0;
      const bOut = outgoing.get(b.id)?.length ?? 0;
      return bOut - aOut;
    });
    roots.push(sorted[0]);
  }

  // BFS to assign levels
  const levels = new Map<string, number>();
  const queue: { id: string; level: number }[] = roots.map(n => ({ id: n.id, level: 0 }));
  const visited = new Set<string>();

  while (queue.length > 0) {
    const { id, level } = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    levels.set(id, level);

    const children = outgoing.get(id) ?? [];
    children.forEach(childId => {
      if (!visited.has(childId)) {
        queue.push({ id: childId, level: level + 1 });
      }
    });
  }

  // Add unvisited nodes to level 0
  nodes.forEach(n => {
    if (!levels.has(n.id)) {
      levels.set(n.id, 0);
    }
  });

  // Group nodes by level
  const levelNodes = new Map<number, string[]>();
  levels.forEach((level, id) => {
    if (!levelNodes.has(level)) levelNodes.set(level, []);
    levelNodes.get(level)!.push(id);
  });

  const maxLevel = Math.max(...levels.values());
  const result = new Map<string, { x: number; y: number }>();

  // Calculate positions
  levelNodes.forEach((nodeIds, level) => {
    const levelWidth = nodeIds.length * nodeSpacing;
    const startX = direction === 'top-down'
      ? (width - levelWidth) / 2 + nodeSpacing / 2
      : padding + level * levelSpacing;
    const startY = direction === 'top-down'
      ? padding + level * levelSpacing
      : (height - levelWidth) / 2 + nodeSpacing / 2;

    nodeIds.forEach((id, i) => {
      if (direction === 'top-down') {
        result.set(id, {
          x: startX + i * nodeSpacing,
          y: startY,
        });
      } else {
        result.set(id, {
          x: startX,
          y: startY + i * nodeSpacing,
        });
      }
    });
  });

  const boundsWidth = direction === 'top-down' ? width : padding * 2 + (maxLevel + 1) * levelSpacing;
  const boundsHeight = direction === 'top-down' ? padding * 2 + (maxLevel + 1) * levelSpacing : height;

  return {
    nodes: result,
    bounds: {
      minX: padding,
      minY: padding,
      maxX: Math.max(width, boundsWidth) - padding,
      maxY: Math.max(height, boundsHeight) - padding,
    },
  };
}

/**
 * Radial Layout
 * Arranges nodes in concentric circles based on their distance from root nodes.
 * Similar to hierarchical but radial instead of linear.
 */
export function radialLayout(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  options: {
    padding?: number;
    levelSpacing?: number;
    startAngle?: number;
  } = {}
): LayoutResult {
  const padding = options.padding ?? 50;
  const levelSpacing = options.levelSpacing ?? 80;
  const startAngle = options.startAngle ?? -Math.PI / 2;

  const centerX = width / 2;
  const centerY = height / 2;

  // Build adjacency lists
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const nodeIds = new Set(nodes.map(n => n.id));

  edges.forEach(e => {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return;

    if (!outgoing.has(e.source)) outgoing.set(e.source, []);
    if (!incoming.has(e.target)) incoming.set(e.target, []);
    outgoing.get(e.source)!.push(e.target);
    incoming.get(e.target)!.push(e.source);
  });

  // Find root nodes
  const roots = nodes.filter(n => !incoming.has(n.id) || incoming.get(n.id)!.length === 0);

  if (roots.length === 0) {
    const sorted = [...nodes].sort((a, b) => {
      const aOut = outgoing.get(a.id)?.length ?? 0;
      const bOut = outgoing.get(b.id)?.length ?? 0;
      return bOut - aOut;
    });
    roots.push(sorted[0]);
  }

  // BFS to assign levels
  const levels = new Map<string, number>();
  const queue: { id: string; level: number }[] = roots.map(n => ({ id: n.id, level: 0 }));
  const visited = new Set<string>();

  while (queue.length > 0) {
    const { id, level } = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    levels.set(id, level);

    const children = outgoing.get(id) ?? [];
    children.forEach(childId => {
      if (!visited.has(childId)) {
        queue.push({ id: childId, level: level + 1 });
      }
    });
  }

  nodes.forEach(n => {
    if (!levels.has(n.id)) {
      levels.set(n.id, 0);
    }
  });

  // Group nodes by level
  const levelNodes = new Map<number, string[]>();
  levels.forEach((level, id) => {
    if (!levelNodes.has(level)) levelNodes.set(level, []);
    levelNodes.get(level)!.push(id);
  });

  const result = new Map<string, { x: number; y: number }>();

  // Place nodes radially
  levelNodes.forEach((nodeIds, level) => {
    const radius = level * levelSpacing;

    if (level === 0) {
      // Root nodes at center or slightly spread
      const angleStep = (2 * Math.PI) / Math.max(nodeIds.length, 1);
      nodeIds.forEach((id, i) => {
        if (nodeIds.length === 1) {
          result.set(id, { x: centerX, y: centerY });
        } else {
          const angle = startAngle + angleStep * i;
          result.set(id, {
            x: centerX + 30 * Math.cos(angle),
            y: centerY + 30 * Math.sin(angle),
          });
        }
      });
    } else {
      const angleStep = (2 * Math.PI) / nodeIds.length;
      nodeIds.forEach((id, i) => {
        const angle = startAngle + angleStep * i;
        result.set(id, {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        });
      });
    }
  });

  const maxLevel = Math.max(...levels.values(), 0);
  const maxRadius = maxLevel * levelSpacing + padding;

  return {
    nodes: result,
    bounds: {
      minX: centerX - maxRadius,
      minY: centerY - maxRadius,
      maxX: centerX + maxRadius,
      maxY: centerY + maxRadius,
    },
  };
}

/**
 * Internal/External Layout
 * Special layout for network topology: internal nodes in center, external on perimeter.
 */
export function internalExternalLayout(
  nodes: LayoutNode[],
  width: number,
  height: number,
  options: {
    padding?: number;
    internalRadius?: number;
    externalRadius?: number;
  } = {}
): LayoutResult {
  const padding = options.padding ?? 50;
  const centerX = width / 2;
  const centerY = height / 2;

  const maxRadius = Math.min(width, height) / 2 - padding;
  const internalRadius = options.internalRadius ?? maxRadius * 0.4;
  const externalRadius = options.externalRadius ?? maxRadius;

  const internalNodes = nodes.filter(n => n.is_internal);
  const externalNodes = nodes.filter(n => !n.is_internal);

  const result = new Map<string, { x: number; y: number }>();

  // Place internal nodes in inner circle
  const internalAngleStep = (2 * Math.PI) / Math.max(internalNodes.length, 1);
  internalNodes.forEach((node, i) => {
    const angle = -Math.PI / 2 + internalAngleStep * i;
    result.set(node.id, {
      x: centerX + internalRadius * Math.cos(angle),
      y: centerY + internalRadius * Math.sin(angle),
    });
  });

  // Place external nodes on outer circle
  const externalAngleStep = (2 * Math.PI) / Math.max(externalNodes.length, 1);
  externalNodes.forEach((node, i) => {
    const angle = -Math.PI / 2 + externalAngleStep * i;
    result.set(node.id, {
      x: centerX + externalRadius * Math.cos(angle),
      y: centerY + externalRadius * Math.sin(angle),
    });
  });

  return {
    nodes: result,
    bounds: {
      minX: centerX - externalRadius,
      minY: centerY - externalRadius,
      maxX: centerX + externalRadius,
      maxY: centerY + externalRadius,
    },
  };
}

export type LayoutType = 'grid' | 'circular' | 'grouped-circular' | 'hierarchical' | 'radial' | 'internal-external';

/**
 * Apply a layout algorithm to nodes
 */
export function applyLayout(
  layoutType: LayoutType,
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  width: number,
  height: number,
  options?: Record<string, unknown>
): LayoutResult {
  switch (layoutType) {
    case 'grid':
      return gridLayout(nodes, width, height, options);
    case 'circular':
      return circularLayout(nodes, width, height, options);
    case 'grouped-circular':
      return groupedCircularLayout(nodes, width, height, options);
    case 'hierarchical':
      return hierarchicalLayout(nodes, edges, width, height, options);
    case 'radial':
      return radialLayout(nodes, edges, width, height, options);
    case 'internal-external':
      return internalExternalLayout(nodes, width, height, options);
    default:
      return gridLayout(nodes, width, height, options);
  }
}
