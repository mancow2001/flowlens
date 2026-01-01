/**
 * Canvas-based Application Detail Topology Renderer
 * High-performance renderer for application topology using Canvas 2D
 *
 * Preserves hierarchical hop-based column layout while adding:
 * 1. Canvas 2D rendering instead of SVG
 * 2. Viewport culling - only render visible elements
 * 3. Level-of-detail (LOD) - simplify rendering when zoomed out
 * 4. Spatial indexing with quadtree for efficient hit testing
 * 5. Batched rendering with requestAnimationFrame
 */

import { useRef, useEffect, useCallback, useMemo } from 'react';
import * as d3 from 'd3';
import { formatProtocolPort } from '../../utils/network';
import type { AssetType } from '../../types';

// Entry point in topology data
interface TopologyEntryPointInfo {
  id: string;
  port: number;
  protocol: number;
  order: number;
  label: string | null;
}

// Node interface for simulation
interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  display_name: string | null;
  ip_address: string;
  asset_type: AssetType | 'client_summary';
  is_entry_point: boolean;
  entry_points: TopologyEntryPointInfo[];
  entry_point_order: number | null;
  role: string | null;
  is_critical: boolean;
  is_external?: boolean;
  is_internal_asset?: boolean;
  hop_distance?: number;
  is_client_summary?: boolean;
  client_count?: number;
  total_bytes_24h?: number;
  target_entry_point_id?: string;
  // Legacy fields for client summary nodes
  entry_point_port?: number | null;
  entry_point_protocol?: number | null;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  target_port: number;
  protocol: number;
  dependency_type: string | null;
  bytes_last_24h: number | null;
  last_seen: string | null;
  is_internal: boolean;
  is_from_client_summary?: boolean;
}

interface Transform {
  x: number;
  y: number;
  k: number;
}

interface QuadtreeNode {
  id: string;
  x: number;
  y: number;
  radius: number;
  data: SimNode;
}

interface ApplicationDetailCanvasProps {
  nodes: SimNode[];
  links: SimLink[];
  width: number;
  height: number;
  onNodeHover?: (node: SimNode | null) => void;
  onEdgeHover?: (edge: SimLink | null, position: { x: number; y: number }) => void;
}

// Colors matching the SVG version
const NODE_COLORS = {
  entry_point: '#eab308',
  internal: '#3b82f6',
  external: '#6b7280',
  critical: '#ef4444',
  client_summary: '#10b981',
};

const EDGE_COLORS = {
  default: '#64748b',
  client_summary: '#10b981',
};

// LOD thresholds - set low for high quality rendering
const LOD = {
  showLabels: 0.25,       // Always show labels unless very zoomed out
  showEdgeLabels: 0.35,   // Show edge labels at reasonable zoom
  showIcons: 0.2,         // Always show icons
  simplifyEdges: 0.1,     // Only simplify when extremely zoomed out
  showArrows: 0.2,        // Always show arrows
};

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
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }

  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;

  return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
}

// Calculate distance from point to quadratic bezier curve
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

    const bx1 = (1 - t1) ** 2 * x1 + 2 * (1 - t1) * t1 * cx + t1 ** 2 * x2;
    const by1 = (1 - t1) ** 2 * y1 + 2 * (1 - t1) * t1 * cy + t1 ** 2 * y2;
    const bx2 = (1 - t2) ** 2 * x1 + 2 * (1 - t2) * t2 * cx + t2 ** 2 * x2;
    const by2 = (1 - t2) ** 2 * y1 + 2 * (1 - t2) * t2 * cy + t2 ** 2 * y2;

    const dist = pointToLineDistance(px, py, bx1, by1, bx2, by2);
    minDist = Math.min(minDist, dist);
  }

  return minDist;
}

export default function ApplicationDetailCanvas({
  nodes,
  links,
  width,
  height,
  onNodeHover,
  onEdgeHover,
}: ApplicationDetailCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transformRef = useRef<Transform>({ x: 30, y: 30, k: 0.85 });
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const quadtreeRef = useRef<d3.Quadtree<QuadtreeNode> | null>(null);
  const simulationRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const rafRef = useRef<number | null>(null);
  const isDraggingRef = useRef(false);
  const dragNodeRef = useRef<SimNode | null>(null);
  const hoveredNodeRef = useRef<SimNode | null>(null);
  const hoveredEdgeRef = useRef<SimLink | null>(null);
  const mouseDownPosRef = useRef<{ x: number; y: number } | null>(null);

  // Refs for callbacks
  const renderFnRef = useRef<() => void>(() => {});
  const updateQuadtreeFnRef = useRef<() => void>(() => {});

  // Get device pixel ratio for crisp rendering
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

  // Determine if we should use performance optimizations
  const usePerformanceOptimizations = useMemo(() => {
    return nodes.length > 100 || links.length > 200;
  }, [nodes.length, links.length]);

  // Check if a point is within the viewport
  const isInViewport = useCallback((x: number, y: number, margin = 50) => {
    const transform = transformRef.current;
    const screenX = x * transform.k + transform.x;
    const screenY = y * transform.k + transform.y;
    return screenX >= -margin && screenX <= width + margin &&
           screenY >= -margin && screenY <= height + margin;
  }, [width, height]);

  // Update quadtree for spatial queries
  const updateQuadtree = useCallback(() => {
    const quadtreeNodes: QuadtreeNode[] = nodesRef.current.map(n => ({
      id: n.id,
      x: n.x ?? 0,
      y: n.y ?? 0,
      radius: n.is_client_summary ? 30 : (n.is_entry_point ? 18 : 14),
      data: n,
    }));

    quadtreeRef.current = d3.quadtree<QuadtreeNode>()
      .x((d: QuadtreeNode) => d.x)
      .y((d: QuadtreeNode) => d.y)
      .addAll(quadtreeNodes);
  }, []);

  // Find node at screen coordinates
  const findNodeAt = useCallback((screenX: number, screenY: number): SimNode | null => {
    const transform = transformRef.current;
    const x = (screenX - transform.x) / transform.k;
    const y = (screenY - transform.y) / transform.k;

    if (!quadtreeRef.current) return null;

    let closest: SimNode | null = null;
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
      const closestX = Math.max(x0, Math.min(x, x1));
      const closestY = Math.max(y0, Math.min(y, y1));
      const dx = closestX - x;
      const dy = closestY - y;
      return dx * dx + dy * dy > closestDist * closestDist;
    });

    return closest;
  }, []);

  // Find edge at screen coordinates
  const findEdgeAt = useCallback((screenX: number, screenY: number, threshold: number = 8): SimLink | null => {
    const transform = transformRef.current;
    const x = (screenX - transform.x) / transform.k;
    const y = (screenY - transform.y) / transform.k;
    const edges = linksRef.current;

    const adjustedThreshold = threshold / transform.k;

    let closestEdge: SimLink | null = null;
    let closestDist = adjustedThreshold;

    for (const edge of edges) {
      const source = edge.source as SimNode;
      const target = edge.target as SimNode;
      const sx = source.x ?? 0;
      const sy = source.y ?? 0;
      const tx = target.x ?? 0;
      const ty = target.y ?? 0;

      // Use curve distance for curved edges, line distance for straight
      let dist: number;
      if (edge.is_from_client_summary) {
        dist = pointToLineDistance(x, y, sx, sy, tx, ty);
      } else {
        const mx = (sx + tx) / 2;
        const my = (sy + ty) / 2;
        dist = pointToCurveDistance(x, y, sx, sy, mx, my, tx, ty);
      }

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
    const renderNodes = nodesRef.current;
    const renderLinks = linksRef.current;

    // Clear canvas with high-DPI scaling
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, width, height);

    // Apply transform with high quality rendering
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
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

    // Group edges by type for batched rendering
    const clientEdges: SimLink[] = [];
    const regularEdges: SimLink[] = [];

    renderLinks.forEach(link => {
      const source = link.source as SimNode;
      const target = link.target as SimNode;

      // Viewport culling
      if (usePerformanceOptimizations) {
        const mx = ((source.x ?? 0) + (target.x ?? 0)) / 2;
        const my = ((source.y ?? 0) + (target.y ?? 0)) / 2;
        if (!isInViewport(mx, my, 200)) return;
      }

      if (link.is_from_client_summary) {
        clientEdges.push(link);
      } else {
        regularEdges.push(link);
      }
    });

    // Render regular edges
    if (regularEdges.length > 0) {
      ctx.strokeStyle = EDGE_COLORS.default;
      ctx.globalAlpha = 0.6;
      ctx.setLineDash([]);

      ctx.beginPath();
      regularEdges.forEach(edge => {
        const source = edge.source as SimNode;
        const target = edge.target as SimNode;
        const sx = source.x ?? 0;
        const sy = source.y ?? 0;
        const tx = target.x ?? 0;
        const ty = target.y ?? 0;

        if (simplifyEdges) {
          ctx.moveTo(sx, sy);
          ctx.lineTo(tx, ty);
        } else {
          // Use quadratic curve for curved edges
          ctx.moveTo(sx, sy);
          const mx = (sx + tx) / 2;
          const my = (sy + ty) / 2 - 20;
          ctx.quadraticCurveTo(mx, my, tx, ty);
        }
      });
      ctx.stroke();

      // Draw arrows for regular edges
      if (showArrows && !simplifyEdges) {
        ctx.fillStyle = EDGE_COLORS.default;
        regularEdges.forEach(edge => {
          const source = edge.source as SimNode;
          const target = edge.target as SimNode;
          const sx = source.x ?? 0;
          const sy = source.y ?? 0;
          const tx = target.x ?? 0;
          const ty = target.y ?? 0;

          const dx = tx - sx;
          const dy = ty - sy;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len < 50) return;

          const nodeRadius = (target.is_entry_point ? 18 : 14) + 5;
          const arrowX = tx - (dx / len) * nodeRadius;
          const arrowY = ty - (dy / len) * nodeRadius;
          const angle = Math.atan2(dy, dx);

          ctx.save();
          ctx.translate(arrowX, arrowY);
          ctx.rotate(angle);
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(-8, -4);
          ctx.lineTo(-8, 4);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        });
      }
    }

    // Render client summary edges (dashed, green)
    if (clientEdges.length > 0) {
      ctx.strokeStyle = EDGE_COLORS.client_summary;
      ctx.globalAlpha = 0.6;
      ctx.lineWidth = 3 / transform.k;
      ctx.setLineDash([5 / transform.k, 5 / transform.k]);

      ctx.beginPath();
      clientEdges.forEach(edge => {
        const source = edge.source as SimNode;
        const target = edge.target as SimNode;
        const sx = source.x ?? 0;
        const sy = source.y ?? 0;
        const tx = target.x ?? 0;
        const ty = target.y ?? 0;

        ctx.moveTo(sx, sy);
        ctx.lineTo(tx, ty);
      });
      ctx.stroke();

      // Draw arrows for client edges
      if (showArrows) {
        ctx.fillStyle = EDGE_COLORS.client_summary;
        ctx.setLineDash([]);
        clientEdges.forEach(edge => {
          const source = edge.source as SimNode;
          const target = edge.target as SimNode;
          const sx = source.x ?? 0;
          const sy = source.y ?? 0;
          const tx = target.x ?? 0;
          const ty = target.y ?? 0;

          const dx = tx - sx;
          const dy = ty - sy;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len < 50) return;

          const nodeRadius = 23;
          const arrowX = tx - (dx / len) * nodeRadius;
          const arrowY = ty - (dy / len) * nodeRadius;
          const angle = Math.atan2(dy, dx);

          ctx.save();
          ctx.translate(arrowX, arrowY);
          ctx.rotate(angle);
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(-8, -4);
          ctx.lineTo(-8, 4);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        });
      }
    }

    ctx.setLineDash([]);

    // Draw edge labels if zoomed in enough
    if (showEdgeLabels && !simplifyEdges) {
      ctx.font = `${10 / transform.k}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.globalAlpha = 1;

      renderLinks.forEach(edge => {
        const source = edge.source as SimNode;
        const target = edge.target as SimNode;
        const sx = source.x ?? 0;
        const sy = source.y ?? 0;
        const tx = target.x ?? 0;
        const ty = target.y ?? 0;

        const label = edge.target_port?.toString() || '';
        if (!label) return;

        const mx = (sx + tx) / 2;
        const my = (sy + ty) / 2 - 8;

        // Background for readability
        const textWidth = ctx.measureText(label).width;
        ctx.fillStyle = 'rgba(30, 41, 59, 0.85)';
        ctx.fillRect(mx - textWidth / 2 - 3, my - 7, textWidth + 6, 14);

        ctx.fillStyle = '#94a3b8';
        ctx.fillText(label, mx, my);
      });
    }

    // Draw hovered edge highlight
    const hoveredEdge = hoveredEdgeRef.current;
    if (hoveredEdge) {
      const source = hoveredEdge.source as SimNode;
      const target = hoveredEdge.target as SimNode;
      const sx = source.x ?? 0;
      const sy = source.y ?? 0;
      const tx = target.x ?? 0;
      const ty = target.y ?? 0;

      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 4 / transform.k;
      ctx.setLineDash(hoveredEdge.is_from_client_summary ? [5 / transform.k, 5 / transform.k] : []);

      ctx.beginPath();
      if (hoveredEdge.is_from_client_summary) {
        ctx.moveTo(sx, sy);
        ctx.lineTo(tx, ty);
      } else {
        const mx = (sx + tx) / 2;
        const my = (sy + ty) / 2 - 20;
        ctx.moveTo(sx, sy);
        ctx.quadraticCurveTo(mx, my, tx, ty);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.globalAlpha = 1;
    ctx.lineWidth = 2 / transform.k;

    // Render nodes
    renderNodes.forEach(node => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;

      // Viewport culling
      if (usePerformanceOptimizations && !isInViewport(x, y)) return;

      const isHovered = node === hoveredNodeRef.current;

      if (node.is_client_summary) {
        // Client summary nodes as rounded rectangles
        const rectWidth = 60;
        const rectHeight = 40;
        const cornerRadius = 8;

        ctx.fillStyle = NODE_COLORS.client_summary;
        ctx.beginPath();
        ctx.roundRect(x - rectWidth / 2, y - rectHeight / 2, rectWidth, rectHeight, cornerRadius);
        ctx.fill();

        ctx.strokeStyle = isHovered ? '#3b82f6' : '#1e293b';
        ctx.lineWidth = (isHovered ? 3 : 1.5) / transform.k;
        ctx.stroke();

        // Client count text
        if (showIcons) {
          ctx.fillStyle = '#1e293b';
          ctx.font = `bold ${14 / transform.k}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(node.client_count?.toString() || '0', x, y);
        }

        // Label below
        if (showLabels) {
          ctx.fillStyle = '#e2e8f0';
          ctx.font = `${11 / transform.k}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(`${node.client_count} clients`, x, y + rectHeight / 2 + 5);

          // Port label
          if (node.entry_point_port !== null) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = `${9 / transform.k}px sans-serif`;
            ctx.fillText(
              formatProtocolPort(node.entry_point_protocol ?? 6, node.entry_point_port),
              x,
              y + rectHeight / 2 + 20
            );
          }
        }
      } else {
        // Regular nodes as circles
        const radius = node.is_entry_point ? 18 : 14;

        // Node fill
        let fillColor = NODE_COLORS.internal;
        if (node.is_entry_point) fillColor = NODE_COLORS.entry_point;
        else if (node.is_external) fillColor = NODE_COLORS.external;
        else if (node.is_critical) fillColor = NODE_COLORS.critical;

        ctx.fillStyle = fillColor;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();

        // Node stroke
        ctx.strokeStyle = isHovered ? '#3b82f6' : '#1e293b';
        ctx.lineWidth = (isHovered ? 3 : 1.5) / transform.k;
        ctx.stroke();

        // Entry point star icon
        if (showIcons && node.is_entry_point) {
          ctx.fillStyle = '#1e293b';
          ctx.font = `${14 / transform.k}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('★', x, y);
        }

        // Node label
        if (showLabels) {
          ctx.fillStyle = '#e2e8f0';
          ctx.font = `${11 / transform.k}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          const label = node.display_name || node.name;
          const truncatedLabel = label.length > 20 ? label.substring(0, 20) + '...' : label;
          ctx.fillText(truncatedLabel, x, y + radius + 5);
        }
      }
    });

    ctx.restore();
    rafRef.current = null;
  }, [width, height, dpr, usePerformanceOptimizations, isInViewport]);

  // Request animation frame for rendering
  const requestRender = useCallback(() => {
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(render);
    }
  }, [render]);

  // Keep refs updated with latest callbacks
  useEffect(() => {
    renderFnRef.current = requestRender;
    updateQuadtreeFnRef.current = updateQuadtree;
  }, [requestRender, updateQuadtree]);

  // Process nodes and links, set up simulation
  useEffect(() => {
    nodesRef.current = nodes;
    linksRef.current = links;

    // Stop any existing simulation
    if (simulationRef.current) {
      simulationRef.current.stop();
      simulationRef.current = null;
    }

    // Create simulation with weak forces (nodes are mostly fixed by hop column position)
    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(120)
          .strength(0.3)
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('collision', d3.forceCollide().radius(45))
      .force('y', d3.forceY<SimNode>()
        .y(height / 2)
        .strength(0.05)
      );

    simulation.alphaDecay(0.03);

    simulation.on('tick', () => {
      updateQuadtreeFnRef.current();
      renderFnRef.current();
    });

    simulationRef.current = simulation;

    // Initial quadtree update and render
    updateQuadtree();
    requestRender();

    return () => {
      simulation.stop();
    };
  }, [nodes, links, height, updateQuadtree, requestRender]);

  // Initial render and cleanup
  useEffect(() => {
    requestRender();
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [requestRender]);

  // Handle zoom
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const zoom = d3.zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.1, 4])
      .filter((event: Event) => {
        if (event.type === 'wheel') return true;
        if (event.type === 'dblclick') return true;
        if (event.type === 'mousedown') {
          const mouseEvent = event as MouseEvent;
          const rect = canvas.getBoundingClientRect();
          const x = mouseEvent.clientX - rect.left;
          const y = mouseEvent.clientY - rect.top;
          const node = findNodeAt(x, y);
          if (node) return false;
        }
        return true;
      })
      .on('zoom', (event: d3.D3ZoomEvent<HTMLCanvasElement, unknown>) => {
        transformRef.current = event.transform;
        requestRender();
      });

    // Set initial transform
    const initialTransform = d3.zoomIdentity.translate(30, 30).scale(0.85);
    d3.select(canvas).call(zoom.transform, initialTransform);
    d3.select(canvas).call(zoom);

    return () => {
      d3.select(canvas).on('.zoom', null);
    };
  }, [requestRender, findNodeAt]);

  // Handle mouse events
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const CLICK_THRESHOLD = 5;

    const handleMouseMove = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;

      // Check if we're dragging a node
      if (mouseDownPosRef.current && dragNodeRef.current) {
        const dx = x - mouseDownPosRef.current.x;
        const dy = y - mouseDownPosRef.current.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

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

      // Hover detection
      const node = findNodeAt(x, y);
      let needsRender = false;

      if (node !== hoveredNodeRef.current) {
        hoveredNodeRef.current = node;
        needsRender = true;
        if (onNodeHover) {
          onNodeHover(node);
        }
      }

      // Edge hover detection
      if (!node) {
        const edge = findEdgeAt(x, y);
        if (edge !== hoveredEdgeRef.current) {
          hoveredEdgeRef.current = edge;
          needsRender = true;

          if (onEdgeHover) {
            if (edge) {
              onEdgeHover(edge, { x: event.clientX, y: event.clientY });
            } else {
              onEdgeHover(null, { x: 0, y: 0 });
            }
          }
        } else if (edge && onEdgeHover) {
          onEdgeHover(edge, { x: event.clientX, y: event.clientY });
        }
      } else if (hoveredEdgeRef.current) {
        hoveredEdgeRef.current = null;
        if (onEdgeHover) {
          onEdgeHover(null, { x: 0, y: 0 });
        }
        needsRender = true;
      }

      canvas.style.cursor = node || hoveredEdgeRef.current ? 'pointer' : 'default';

      if (needsRender) {
        requestRender();
      }
    };

    const handleMouseDown = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;

      mouseDownPosRef.current = { x, y };
      isDraggingRef.current = false;

      const node = findNodeAt(x, y);
      if (node) {
        dragNodeRef.current = node;
        const transform = transformRef.current;
        node.fx = (x - transform.x) / transform.k;
        node.fy = (y - transform.y) / transform.k;
      }
    };

    const handleMouseUp = () => {
      // Release any fixed node (unless it should stay fixed)
      if (dragNodeRef.current) {
        const node = dragNodeRef.current;
        // Keep entry points and client summary nodes fixed in X
        if (!node.is_entry_point && !node.is_client_summary) {
          node.fx = null;
        }
        node.fy = null;
        simulationRef.current?.alphaTarget(0);
      }

      mouseDownPosRef.current = null;
      isDraggingRef.current = false;
      dragNodeRef.current = null;
    };

    const handleMouseLeave = () => {
      if (dragNodeRef.current) {
        const node = dragNodeRef.current;
        if (!node.is_entry_point && !node.is_client_summary) {
          node.fx = null;
        }
        node.fy = null;
        simulationRef.current?.alphaTarget(0);
      }
      mouseDownPosRef.current = null;
      isDraggingRef.current = false;
      dragNodeRef.current = null;
      hoveredNodeRef.current = null;

      if (onNodeHover) {
        onNodeHover(null);
      }

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
  }, [findNodeAt, findEdgeAt, onNodeHover, onEdgeHover, requestRender]);

  return (
    <canvas
      ref={canvasRef}
      width={width * dpr}
      height={height * dpr}
      style={{
        display: 'block',
        width: '100%',
        height: '100%',
        background: '#0f172a',
      }}
    />
  );
}
