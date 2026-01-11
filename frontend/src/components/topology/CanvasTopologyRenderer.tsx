/**
 * Canvas-based Topology Renderer
 * High-performance renderer for large graphs using Canvas 2D
 *
 * Key optimizations:
 * 1. Canvas 2D rendering instead of SVG (order of magnitude faster)
 * 2. Viewport culling - only render visible elements
 * 3. Level-of-detail (LOD) - simplify rendering when zoomed out
 * 4. Spatial indexing with quadtree for efficient hit testing
 * 5. Batched rendering with requestAnimationFrame
 * 6. Double buffering for smooth updates
 */

import { useRef, useEffect, useCallback, useMemo } from 'react';
import * as d3 from 'd3';
import type { TopologyNode, TopologyEdge, AssetType } from '../../types';
import { getServiceName } from '../../utils/network';
import { applyLayout, type LayoutType } from '../../utils/graphLayouts';
import { getAssetTypeColor } from '../../constants/assetTypes';

// Calculate distance from point to line segment
function pointToLineDistance(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) {
    // Line segment is a point
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }

  // Project point onto line, clamped to segment
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;

  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
}

// Calculate distance from point to quadratic bezier curve (sampled)
function pointToCurveDistance(
  px: number, py: number,
  x1: number, y1: number,
  cx: number, cy: number,
  x2: number, y2: number,
  samples: number = 10
): number {
  let minDist = Infinity;

  for (let i = 0; i < samples; i++) {
    const t1 = i / samples;
    const t2 = (i + 1) / samples;

    // Quadratic bezier: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
    const bx1 = (1 - t1) ** 2 * x1 + 2 * (1 - t1) * t1 * cx + t1 ** 2 * x2;
    const by1 = (1 - t1) ** 2 * y1 + 2 * (1 - t1) * t1 * cy + t1 ** 2 * y2;
    const bx2 = (1 - t2) ** 2 * x1 + 2 * (1 - t2) * t2 * cx + t2 ** 2 * x2;
    const by2 = (1 - t2) ** 2 * y1 + 2 * (1 - t2) * t2 * cy + t2 ** 2 * y2;

    const dist = pointToLineDistance(px, py, bx1, by1, bx2, by2);
    minDist = Math.min(minDist, dist);
  }

  return minDist;
}

// Get edge label text showing port/service info
function getEdgeLabel(ports: number[] | undefined, targetPort: number): string {
  const portsToShow = ports && ports.length > 0 ? ports : [targetPort];
  if (portsToShow.length === 0 || (portsToShow.length === 1 && portsToShow[0] === 0)) {
    return '';
  }

  if (portsToShow.length === 1) {
    const port = portsToShow[0];
    const service = getServiceName(port);
    return service ? `${service.toLowerCase()}` : `${port}`;
  }

  if (portsToShow.length <= 2) {
    return portsToShow.map(p => {
      const service = getServiceName(p);
      return service ? service.toLowerCase() : `${p}`;
    }).join(', ');
  }

  return `${portsToShow.length} ports`;
}

// Quadtree for efficient spatial queries
interface QuadtreeNode {
  id: string;
  x: number;
  y: number;
  radius: number;
  data: RenderNode;
}

interface RenderNode extends TopologyNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
  isGroupNode?: boolean;
  groupKey?: string;
  groupNodeCount?: number;
}

interface RenderEdge {
  id: string;
  source: RenderNode;
  target: RenderNode;
  targetPort: number;
  targetPorts?: number[];
  protocol: number;
  bytesTotal: number;
  isCritical: boolean;
  isAggregated?: boolean;
  aggregatedCount?: number;
  isGatewayEdge?: boolean;
}

interface Transform {
  x: number;
  y: number;
  k: number; // scale
}

interface CanvasTopologyRendererProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  width: number;
  height: number;
  selectedNodeId?: string | null;
  highlightedPaths?: {
    upstream: Set<string>;
    downstream: Set<string>;
    edges: Set<string>;
  } | null;
  groupingMode?: 'none' | 'location' | 'environment' | 'datacenter' | 'type';
  groupColors?: Map<string, string>;
  onNodeClick?: (node: TopologyNode) => void;
  onNodeDoubleClick?: (node: TopologyNode) => void;
  onBackgroundClick?: () => void;
  onEdgeHover?: (edge: RenderEdge | null, position: { x: number; y: number }) => void;
  simulationConfig?: {
    linkDistance?: number;
    chargeStrength?: number;
    collisionRadius?: number;
  };
  performanceMode?: 'auto' | 'quality' | 'performance';
  layoutType?: LayoutType | 'force';
}

// Colors
const COLORS = {
  background: '#1e293b',
  nodeInternal: '#10b981',
  nodeExternal: '#f97316',
  nodeStroke: '#1e293b',
  nodeStrokeHover: '#3b82f6',
  nodeStrokeSelected: '#fbbf24',
  edgeDefault: '#475569',
  edgeInternal: '#22c55e',
  edgeExternal: '#f97316',
  edgeCritical: '#ef4444',
  edgeGateway: '#a855f7',
  edgeHighlightUpstream: '#22d3ee',
  edgeHighlightDownstream: '#fbbf24',
  textPrimary: '#e2e8f0',
  textSecondary: '#94a3b8',
  hullFill: 'rgba(59, 130, 246, 0.1)',
  hullStroke: 'rgba(59, 130, 246, 0.5)',
};

// LOD thresholds
const LOD = {
  showLabels: 0.4,      // Show labels above this zoom level
  showEdgeLabels: 0.6,  // Show edge labels above this level
  showIcons: 0.3,       // Show node icons above this level
  simplifyEdges: 0.2,   // Simplify edge rendering below this level
  showArrows: 0.35,     // Show edge arrows above this level
};

export default function CanvasTopologyRenderer({
  nodes,
  edges,
  width,
  height,
  selectedNodeId,
  highlightedPaths,
  groupingMode = 'none',
  groupColors = new Map(),
  onNodeClick,
  onNodeDoubleClick,
  onBackgroundClick,
  onEdgeHover,
  simulationConfig,
  performanceMode = 'auto',
  layoutType = 'force',
}: CanvasTopologyRendererProps) {

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transformRef = useRef<Transform>({ x: 0, y: 0, k: 1 });
  const nodesRef = useRef<RenderNode[]>([]);
  const edgesRef = useRef<RenderEdge[]>([]);
  const quadtreeRef = useRef<d3.Quadtree<QuadtreeNode> | null>(null);
  const simulationRef = useRef<d3.Simulation<RenderNode, RenderEdge> | null>(null);
  const rafRef = useRef<number | null>(null);
  const isDraggingRef = useRef(false);
  const dragNodeRef = useRef<RenderNode | null>(null);
  const hoveredNodeRef = useRef<RenderNode | null>(null);
  const hoveredEdgeRef = useRef<RenderEdge | null>(null);
  const mouseDownPosRef = useRef<{ x: number; y: number } | null>(null);
  const mouseDownTimeRef = useRef<number>(0);

  // Refs for callbacks to avoid stale closures in simulation tick handler
  const renderFnRef = useRef<() => void>(() => {});
  const updateQuadtreeFnRef = useRef<() => void>(() => {});

  // Determine if we should use performance optimizations
  const usePerformanceOptimizations = useMemo(() => {
    if (performanceMode === 'quality') return false;
    if (performanceMode === 'performance') return true;
    // Auto mode: enable optimizations for large graphs
    return nodes.length > 200 || edges.length > 500;
  }, [nodes.length, edges.length, performanceMode]);

  // Process nodes and edges for rendering
  useEffect(() => {
    // Aggregate edges between same source/target
    const edgeMap = new Map<string, {
      edge: TopologyEdge;
      ports: number[];
      count: number;
    }>();

    edges.forEach(e => {
      const key = `${e.source}->${e.target}`;
      if (edgeMap.has(key)) {
        const existing = edgeMap.get(key)!;
        if (!existing.ports.includes(e.target_port)) {
          existing.ports.push(e.target_port);
        }
        existing.count++;
      } else {
        edgeMap.set(key, {
          edge: e,
          ports: [e.target_port],
          count: 1,
        });
      }
    });

    // Create node map
    const nodeMap = new Map<string, RenderNode>();
    const renderNodes: RenderNode[] = nodes.map(n => {
      const renderNode: RenderNode = {
        ...n,
        x: n.x ?? width / 2 + (Math.random() - 0.5) * width * 0.5,
        y: n.y ?? height / 2 + (Math.random() - 0.5) * height * 0.5,
        vx: 0,
        vy: 0,
        fx: null,
        fy: null,
      };
      nodeMap.set(n.id, renderNode);
      return renderNode;
    });

    // Create render edges
    const renderEdges: RenderEdge[] = Array.from(edgeMap.values())
      .filter(({ edge }) => nodeMap.has(edge.source) && nodeMap.has(edge.target))
      .map(({ edge, ports, count }) => ({
        id: edge.id,
        source: nodeMap.get(edge.source)!,
        target: nodeMap.get(edge.target)!,
        targetPort: edge.target_port,
        targetPorts: ports.sort((a, b) => a - b),
        protocol: edge.protocol,
        bytesTotal: edge.bytes_total,
        isCritical: edge.is_critical,
        isAggregated: count > 1,
        aggregatedCount: count,
      }));

    nodesRef.current = renderNodes;
    edgesRef.current = renderEdges;

    // Stop any existing simulation
    if (simulationRef.current) {
      simulationRef.current.stop();
      simulationRef.current = null;
    }

    // Apply static layout or use force simulation
    if (layoutType !== 'force') {
      // Apply static layout
      const layoutNodes = renderNodes.map(n => ({
        id: n.id,
        groupKey: groupingMode !== 'none' ? (n as TopologyNode & { environment?: string; datacenter?: string; location?: string; asset_type?: string })[
          groupingMode === 'environment' ? 'environment' :
          groupingMode === 'datacenter' ? 'datacenter' :
          groupingMode === 'location' ? 'location' :
          'asset_type'
        ] ?? 'default' : undefined,
        is_internal: n.is_internal,
        connections_in: edges.filter(e => e.target === n.id).length,
        connections_out: edges.filter(e => e.source === n.id).length,
      }));

      const layoutEdges = edges.map(e => ({
        source: e.source,
        target: e.target,
      }));

      const layoutResult = applyLayout(
        layoutType as LayoutType,
        layoutNodes,
        layoutEdges,
        width,
        height
      );

      // Apply layout positions to render nodes
      renderNodes.forEach(node => {
        const pos = layoutResult.nodes.get(node.id);
        if (pos) {
          node.x = pos.x;
          node.y = pos.y;
        }
      });

      // Update quadtree and render
      updateQuadtreeFnRef.current();
      renderFnRef.current();

      return;
    }

    // Use force simulation for 'force' layout
    const nodeCount = renderNodes.length;
    const baseDistance = Math.max(100, Math.min(200, 800 / Math.sqrt(nodeCount)));
    const baseStrength = Math.max(-800, Math.min(-200, -300 - nodeCount * 0.5));

    const simulation = d3.forceSimulation<RenderNode>(renderNodes)
      .force('link', d3.forceLink<RenderNode, RenderEdge>(renderEdges)
        .id((d: RenderNode) => d.id)
        .distance(simulationConfig?.linkDistance ?? baseDistance)
        .strength(0.5))
      .force('charge', d3.forceManyBody<RenderNode>()
        .strength(simulationConfig?.chargeStrength ?? baseStrength)
        .distanceMax(500)
        .theta(usePerformanceOptimizations ? 0.9 : 0.5))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<RenderNode>()
        .radius(simulationConfig?.collisionRadius ?? 50)
        .strength(0.8))
      .force('x', d3.forceX(width / 2).strength(0.02))
      .force('y', d3.forceY(height / 2).strength(0.02));

    if (usePerformanceOptimizations) {
      simulation.alphaDecay(0.03);
      simulation.velocityDecay(0.3);
    } else {
      simulation.alphaDecay(0.02);
      simulation.velocityDecay(0.4);
    }

    simulation.on('tick', () => {
      updateQuadtreeFnRef.current();
      renderFnRef.current();
    });

    simulationRef.current = simulation;

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, width, height, simulationConfig, usePerformanceOptimizations, layoutType, groupingMode]);

  // Update quadtree for spatial queries
  const updateQuadtree = useCallback(() => {
    const quadtreeNodes: QuadtreeNode[] = nodesRef.current.map(n => ({
      id: n.id,
      x: n.x,
      y: n.y,
      radius: n.isGroupNode ? 35 : 20,
      data: n,
    }));

    quadtreeRef.current = d3.quadtree<QuadtreeNode>()
      .x((d: QuadtreeNode) => d.x)
      .y((d: QuadtreeNode) => d.y)
      .addAll(quadtreeNodes);
  }, []);

  // Check if a point is within the viewport
  const isInViewport = useCallback((x: number, y: number, margin = 50) => {
    const transform = transformRef.current;
    const screenX = x * transform.k + transform.x;
    const screenY = y * transform.k + transform.y;
    return screenX >= -margin && screenX <= width + margin &&
           screenY >= -margin && screenY <= height + margin;
  }, [width, height]);

  // Find node at screen coordinates
  const findNodeAt = useCallback((screenX: number, screenY: number): RenderNode | null => {
    const transform = transformRef.current;
    const x = (screenX - transform.x) / transform.k;
    const y = (screenY - transform.y) / transform.k;

    if (!quadtreeRef.current) return null;

    let closest: RenderNode | null = null;
    let closestDist = Infinity;

    quadtreeRef.current.visit((
      node: d3.QuadtreeInternalNode<QuadtreeNode> | d3.QuadtreeLeaf<QuadtreeNode>,
      x0: number,
      y0: number,
      x1: number,
      y1: number
    ) => {
      if (!node.length) {
        const leaf = node as d3.QuadtreeLeaf<QuadtreeNode>;
        const n = leaf.data;
        const dx = n.x - x;
        const dy = n.y - y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < n.radius / transform.k && dist < closestDist) {
          closest = n.data;
          closestDist = dist;
        }
      }
      // Check if quadrant could contain closer node
      const closestX = Math.max(x0, Math.min(x, x1));
      const closestY = Math.max(y0, Math.min(y, y1));
      const dx = closestX - x;
      const dy = closestY - y;
      return dx * dx + dy * dy > closestDist * closestDist;
    });

    return closest;
  }, []);

  // Find edge at screen coordinates
  const findEdgeAt = useCallback((screenX: number, screenY: number, threshold: number = 8): RenderEdge | null => {
    const transform = transformRef.current;
    const x = (screenX - transform.x) / transform.k;
    const y = (screenY - transform.y) / transform.k;
    const edges = edgesRef.current;

    // Adjust threshold for zoom level
    const adjustedThreshold = threshold / transform.k;

    let closestEdge: RenderEdge | null = null;
    let closestDist = adjustedThreshold;

    for (const edge of edges) {
      const sx = edge.source.x;
      const sy = edge.source.y;
      const tx = edge.target.x;
      const ty = edge.target.y;

      // Use curve distance for better accuracy
      const mx = (sx + tx) / 2;
      const my = (sy + ty) / 2;
      const dist = pointToCurveDistance(x, y, sx, sy, mx, my, tx, ty);

      if (dist < closestDist) {
        closestDist = dist;
        closestEdge = edge;
      }
    }

    return closestEdge;
  }, []);

  // Render function
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;

    const transform = transformRef.current;
    const nodes = nodesRef.current;
    const edges = edgesRef.current;

    // Clear canvas
    ctx.fillStyle = COLORS.background;
    ctx.fillRect(0, 0, width, height);

    // Apply transform
    ctx.save();
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // Determine LOD levels
    const showLabels = transform.k >= LOD.showLabels;
    const showEdgeLabels = transform.k >= LOD.showEdgeLabels;
    const showIcons = transform.k >= LOD.showIcons;
    const simplifyEdges = transform.k < LOD.simplifyEdges;
    const showArrows = transform.k >= LOD.showArrows;

    // Render edges
    ctx.lineWidth = 2 / transform.k;

    // Group edges by color for batched rendering
    const edgesByColor = new Map<string, RenderEdge[]>();

    edges.forEach(edge => {
      // Viewport culling
      if (usePerformanceOptimizations) {
        const mx = (edge.source.x + edge.target.x) / 2;
        const my = (edge.source.y + edge.target.y) / 2;
        if (!isInViewport(mx, my, 200)) return;
      }

      let color = COLORS.edgeInternal;

      if (highlightedPaths?.edges.has(edge.id)) {
        // Determine if upstream or downstream based on source/target
        if (highlightedPaths.upstream.has(edge.source.id)) {
          color = COLORS.edgeHighlightUpstream;
        } else {
          color = COLORS.edgeHighlightDownstream;
        }
      } else if (edge.isGatewayEdge) {
        color = COLORS.edgeGateway;
      } else if (edge.isCritical) {
        color = COLORS.edgeCritical;
      } else if (!edge.source.is_internal || !edge.target.is_internal) {
        color = COLORS.edgeExternal;
      }

      if (!edgesByColor.has(color)) {
        edgesByColor.set(color, []);
      }
      edgesByColor.get(color)!.push(edge);
    });

    // Render edges in batches by color
    edgesByColor.forEach((colorEdges, color) => {
      ctx.strokeStyle = color;
      ctx.globalAlpha = highlightedPaths ? 0.3 : 0.7;

      ctx.beginPath();
      colorEdges.forEach(edge => {
        if (simplifyEdges) {
          // Simple lines when zoomed out
          ctx.moveTo(edge.source.x, edge.source.y);
          ctx.lineTo(edge.target.x, edge.target.y);
        } else {
          // Curved paths
          const mx = (edge.source.x + edge.target.x) / 2;
          const my = (edge.source.y + edge.target.y) / 2;
          ctx.moveTo(edge.source.x, edge.source.y);
          ctx.quadraticCurveTo(mx, my, edge.target.x, edge.target.y);
        }
      });
      ctx.stroke();

      // Draw arrows if needed
      if (showArrows && !simplifyEdges) {
        ctx.fillStyle = color;
        colorEdges.forEach(edge => {
          const dx = edge.target.x - edge.source.x;
          const dy = edge.target.y - edge.source.y;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len < 50) return;

          const nodeRadius = edge.target.isGroupNode ? 35 : 20;
          const arrowX = edge.target.x - (dx / len) * (nodeRadius + 10);
          const arrowY = edge.target.y - (dy / len) * (nodeRadius + 10);
          const angle = Math.atan2(dy, dx);

          ctx.save();
          ctx.translate(arrowX, arrowY);
          ctx.rotate(angle);
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(-10, -5);
          ctx.lineTo(-10, 5);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        });
      }

      // Draw edge labels if zoomed in enough
      if (showEdgeLabels && !simplifyEdges) {
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        colorEdges.forEach(edge => {
          const label = getEdgeLabel(edge.targetPorts, edge.targetPort);
          if (!label) return;

          // Calculate midpoint of edge
          const mx = (edge.source.x + edge.target.x) / 2;
          const my = (edge.source.y + edge.target.y) / 2;

          // Calculate angle for text orientation
          const dx = edge.target.x - edge.source.x;
          const dy = edge.target.y - edge.source.y;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len < 80) return; // Skip labels for very short edges

          // Offset label perpendicular to edge direction
          const offsetDist = 12;
          const perpX = -dy / len * offsetDist;
          const perpY = dx / len * offsetDist;

          const labelX = mx + perpX;
          const labelY = my + perpY;

          // Draw background for readability
          const textWidth = ctx.measureText(label).width;
          ctx.fillStyle = 'rgba(30, 41, 59, 0.85)';
          ctx.fillRect(labelX - textWidth / 2 - 3, labelY - 7, textWidth + 6, 14);

          // Draw label text
          ctx.fillStyle = COLORS.textSecondary;
          ctx.fillText(label, labelX, labelY);
        });
      }
    });

    // Draw hovered edge highlight
    const hoveredEdge = hoveredEdgeRef.current;
    if (hoveredEdge) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#3b82f6'; // Blue highlight
      ctx.lineWidth = 4 / transform.k;

      ctx.beginPath();
      const mx = (hoveredEdge.source.x + hoveredEdge.target.x) / 2;
      const my = (hoveredEdge.source.y + hoveredEdge.target.y) / 2;
      ctx.moveTo(hoveredEdge.source.x, hoveredEdge.source.y);
      ctx.quadraticCurveTo(mx, my, hoveredEdge.target.x, hoveredEdge.target.y);
      ctx.stroke();
      ctx.lineWidth = 2 / transform.k;
    }

    // Reset alpha for highlighted edges
    if (highlightedPaths) {
      ctx.globalAlpha = 1;
      highlightedPaths.edges.forEach(edgeId => {
        const edge = edges.find((e: RenderEdge) => e.id === edgeId);
        if (!edge) return;

        const isUpstream = highlightedPaths.upstream.has(edge.source.id);
        ctx.strokeStyle = isUpstream ? COLORS.edgeHighlightUpstream : COLORS.edgeHighlightDownstream;
        ctx.lineWidth = 3 / transform.k;

        ctx.beginPath();
        const mx = (edge.source.x + edge.target.x) / 2;
        const my = (edge.source.y + edge.target.y) / 2;
        ctx.moveTo(edge.source.x, edge.source.y);
        ctx.quadraticCurveTo(mx, my, edge.target.x, edge.target.y);
        ctx.stroke();
      });
      ctx.lineWidth = 2 / transform.k;
    }

    ctx.globalAlpha = 1;

    // Render nodes
    nodes.forEach(node => {
      // Viewport culling
      if (usePerformanceOptimizations && !isInViewport(node.x, node.y)) return;

      const radius = node.isGroupNode ? 35 : 20;
      const isSelected = node.id === selectedNodeId;
      const isHovered = node === hoveredNodeRef.current;
      const isHighlighted = highlightedPaths && (
        highlightedPaths.upstream.has(node.id) ||
        highlightedPaths.downstream.has(node.id) ||
        node.id === selectedNodeId
      );

      // Dim non-highlighted nodes when highlighting is active
      if (highlightedPaths && !isHighlighted && !isSelected) {
        ctx.globalAlpha = 0.15;
      }

      // Node fill - use asset type color if available, otherwise internal/external
      let fillColor: string;
      if (node.isGroupNode && node.groupKey) {
        fillColor = groupColors.get(node.groupKey) || '#6b7280';
      } else if ((node as TopologyNode).asset_type && (node as TopologyNode).asset_type !== 'unknown') {
        fillColor = getAssetTypeColor((node as TopologyNode).asset_type as AssetType);
      } else {
        fillColor = node.is_internal ? COLORS.nodeInternal : COLORS.nodeExternal;
      }

      ctx.fillStyle = fillColor;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();

      // Node stroke
      let strokeColor = COLORS.nodeStroke;
      let strokeWidth = 2;
      if (isSelected) {
        strokeColor = COLORS.nodeStrokeSelected;
        strokeWidth = 4;
      } else if (isHovered) {
        strokeColor = COLORS.nodeStrokeHover;
        strokeWidth = 3;
      } else if (isHighlighted) {
        strokeColor = highlightedPaths!.upstream.has(node.id)
          ? COLORS.edgeHighlightUpstream
          : COLORS.edgeHighlightDownstream;
        strokeWidth = 3;
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = strokeWidth / transform.k;
      ctx.stroke();

      // Node icon
      if (showIcons) {
        ctx.fillStyle = 'white';
        ctx.font = `bold ${node.isGroupNode ? 16 : 14}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const icon = node.isGroupNode
          ? (node.groupNodeCount?.toString() || '')
          : (node.is_internal ? 'I' : 'E');
        ctx.fillText(icon, node.x, node.y);
      }

      // Node label
      if (showLabels) {
        ctx.fillStyle = COLORS.textPrimary;
        ctx.font = `${node.isGroupNode ? 'bold 12px' : '11px'} sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        const label = node.name.length > 20
          ? node.name.substring(0, 20) + '...'
          : node.name;
        ctx.fillText(label, node.x, node.y + radius + 5);
      }

      ctx.globalAlpha = 1;
    });

    ctx.restore();

    rafRef.current = null;
  }, [width, height, selectedNodeId, highlightedPaths, groupColors, usePerformanceOptimizations, isInViewport]);

  // Request animation frame for rendering
  const requestRender = useCallback(() => {
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(render);
    }
  }, [render]);

  // Keep refs updated with latest callbacks (for simulation tick handler)
  useEffect(() => {
    renderFnRef.current = requestRender;
    updateQuadtreeFnRef.current = updateQuadtree;
  }, [requestRender, updateQuadtree]);

  // Initial render and cleanup
  useEffect(() => {
    requestRender();
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [requestRender]);

  // Re-render when highlight/selection changes
  useEffect(() => {
    requestRender();
  }, [selectedNodeId, highlightedPaths, requestRender]);

  // Handle zoom
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const zoom = d3.zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.1, 4])
      .filter((event: Event) => {
        // Allow zoom on wheel events
        if (event.type === 'wheel') return true;
        // Allow zoom on double-click for zoom in
        if (event.type === 'dblclick') return true;
        // For mouse events, only allow if not clicking on a node
        if (event.type === 'mousedown') {
          const mouseEvent = event as MouseEvent;
          const rect = canvas.getBoundingClientRect();
          const x = mouseEvent.clientX - rect.left;
          const y = mouseEvent.clientY - rect.top;
          const node = findNodeAt(x, y);
          // Block zoom/pan if clicking on a node
          if (node) return false;
        }
        return true;
      })
      .on('zoom', (event: d3.D3ZoomEvent<HTMLCanvasElement, unknown>) => {
        transformRef.current = event.transform;
        requestRender();
      });

    d3.select(canvas).call(zoom);

    return () => {
      d3.select(canvas).on('.zoom', null);
    };
  }, [requestRender, findNodeAt]);

  // Handle mouse events
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const CLICK_THRESHOLD = 5; // Max pixels moved to count as click
    const DOUBLE_CLICK_TIME = 300; // ms
    let lastClickTime = 0;

    const handleMouseMove = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;

      // Check if we're dragging a node
      if (mouseDownPosRef.current && dragNodeRef.current) {
        const dx = x - mouseDownPosRef.current.x;
        const dy = y - mouseDownPosRef.current.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        // Start actual dragging if moved past threshold
        if (dist > CLICK_THRESHOLD) {
          isDraggingRef.current = true;
        }

        if (isDraggingRef.current) {
          const transform = transformRef.current;
          dragNodeRef.current.fx = (x - transform.x) / transform.k;
          dragNodeRef.current.fy = (y - transform.y) / transform.k;
          dragNodeRef.current.x = dragNodeRef.current.fx;
          dragNodeRef.current.y = dragNodeRef.current.fy;
          simulationRef.current?.alpha(0.3).restart();
          requestRender();
        }
        return;
      }

      // Hover detection - nodes take priority over edges
      const node = findNodeAt(x, y);
      let needsRender = false;

      if (node !== hoveredNodeRef.current) {
        hoveredNodeRef.current = node;
        needsRender = true;
      }

      // Edge hover detection (only if not hovering a node)
      if (!node) {
        const edge = findEdgeAt(x, y);
        if (edge !== hoveredEdgeRef.current) {
          hoveredEdgeRef.current = edge;
          needsRender = true;

          // Call edge hover callback with edge data
          if (onEdgeHover) {
            if (edge) {
              onEdgeHover(edge, { x: event.clientX, y: event.clientY });
            } else {
              onEdgeHover(null, { x: 0, y: 0 });
            }
          }
        } else if (edge && onEdgeHover) {
          // Update position while still hovering same edge
          onEdgeHover(edge, { x: event.clientX, y: event.clientY });
        }
      } else if (hoveredEdgeRef.current) {
        // Clear edge hover when hovering a node
        hoveredEdgeRef.current = null;
        if (onEdgeHover) {
          onEdgeHover(null, { x: 0, y: 0 });
        }
        needsRender = true;
      }

      // Update cursor
      canvas.style.cursor = node ? 'pointer' : (hoveredEdgeRef.current ? 'pointer' : 'default');

      if (needsRender) {
        requestRender();
      }
    };

    const handleMouseDown = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;

      // Store mouse down position and time
      mouseDownPosRef.current = { x, y };
      mouseDownTimeRef.current = Date.now();
      isDraggingRef.current = false;

      const node = findNodeAt(x, y);
      if (node) {
        dragNodeRef.current = node;
        const transform = transformRef.current;
        node.fx = (x - transform.x) / transform.k;
        node.fy = (y - transform.y) / transform.k;
      }
    };

    const handleMouseUp = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;

      const clickedNode = dragNodeRef.current;
      const wasActualDrag = isDraggingRef.current;

      // Release any fixed node
      if (dragNodeRef.current) {
        dragNodeRef.current.fx = null;
        dragNodeRef.current.fy = null;
        simulationRef.current?.alphaTarget(0);
      }

      // Reset state
      const mouseDownPos = mouseDownPosRef.current;
      mouseDownPosRef.current = null;
      isDraggingRef.current = false;
      dragNodeRef.current = null;

      // Determine if this was a click (not a drag)
      if (mouseDownPos && !wasActualDrag) {
        const dx = x - mouseDownPos.x;
        const dy = y - mouseDownPos.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist <= CLICK_THRESHOLD) {
          const now = Date.now();
          const isDoubleClick = now - lastClickTime < DOUBLE_CLICK_TIME;
          lastClickTime = now;

          // Use the node we originally clicked on
          if (clickedNode) {
            if (isDoubleClick && onNodeDoubleClick) {
              onNodeDoubleClick(clickedNode);
            } else if (onNodeClick) {
              onNodeClick(clickedNode);
            }
          } else {
            // Clicked on background
            const nodeAtRelease = findNodeAt(x, y);
            if (nodeAtRelease) {
              if (isDoubleClick && onNodeDoubleClick) {
                onNodeDoubleClick(nodeAtRelease);
              } else if (onNodeClick) {
                onNodeClick(nodeAtRelease);
              }
            } else if (onBackgroundClick) {
              onBackgroundClick();
            }
          }
        }
      }
    };

    const handleMouseLeave = () => {
      if (dragNodeRef.current) {
        dragNodeRef.current.fx = null;
        dragNodeRef.current.fy = null;
        simulationRef.current?.alphaTarget(0);
      }
      mouseDownPosRef.current = null;
      isDraggingRef.current = false;
      dragNodeRef.current = null;
      hoveredNodeRef.current = null;

      // Clear edge hover
      if (hoveredEdgeRef.current) {
        hoveredEdgeRef.current = null;
        if (onEdgeHover) {
          onEdgeHover(null, { x: 0, y: 0 });
        }
      }

      requestRender();
    };

    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      canvas.removeEventListener('mousemove', handleMouseMove);
      canvas.removeEventListener('mousedown', handleMouseDown);
      canvas.removeEventListener('mouseup', handleMouseUp);
      canvas.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [findNodeAt, findEdgeAt, onNodeClick, onNodeDoubleClick, onBackgroundClick, onEdgeHover, requestRender]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{
        display: 'block',
        width: '100%',
        height: '100%',
      }}
    />
  );
}
