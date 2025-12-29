import { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as d3 from 'd3';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import FilterPanel from '../components/topology/FilterPanel';
import EdgeTooltip from '../components/topology/EdgeTooltip';
import { useTopologyFilters } from '../hooks/useTopologyFilters';
import { topologyApi, savedViewsApi, gatewayApi } from '../services/api';
import type { TopologyNode, TopologyEdge, SavedViewSummary, ViewConfig } from '../types';

interface SimNode extends TopologyNode, d3.SimulationNodeDatum {
  isGroupNode?: boolean;
  groupKey?: string;
  groupNodeCount?: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  target_port: number;
  protocol: number;
  protocol_name: string | null;
  service_type: string | null;
  bytes_total: number;
  bytes_last_24h: number;
  is_critical: boolean;
  last_seen: string;
  // Aggregation properties for collapsed groups
  isAggregated?: boolean;
  aggregatedCount?: number;
  originalEdgeIds?: string[];
  // Gateway edge properties
  isGatewayEdge?: boolean;
  gatewayRole?: string;
  confidence?: number;
}

type GroupingMode = 'none' | 'location' | 'environment' | 'datacenter' | 'type';

// Colors for groups (used for hulls)
const GROUP_COLORS = [
  '#3b82f6', // blue
  '#10b981', // green
  '#f59e0b', // amber
  '#8b5cf6', // purple
  '#ef4444', // red
  '#06b6d4', // cyan
  '#f97316', // orange
  '#84cc16', // lime
  '#ec4899', // pink
  '#6366f1', // indigo
];

// Get group key for a node based on grouping mode
function getGroupKey(node: TopologyNode, mode: GroupingMode): string {
  switch (mode) {
    case 'location':
      return node.is_internal ? 'Internal' : 'External';
    case 'environment':
      return node.environment || 'Unknown';
    case 'datacenter':
      return node.datacenter || 'Unknown';
    case 'type':
      return node.asset_type?.replace('_', ' ') || 'Unknown';
    default:
      return 'all';
  }
}

// Compute convex hull for a set of points
function computeHull(points: [number, number][]): [number, number][] | null {
  if (points.length < 3) return null;
  return d3.polygonHull(points);
}

// Generate smooth hull path with padding
function hullPath(hull: [number, number][], padding: number = 40): string {
  if (!hull || hull.length < 3) return '';

  // Add padding by moving points outward from centroid
  const centroid = d3.polygonCentroid(hull);
  const paddedHull = hull.map(([x, y]) => {
    const dx = x - centroid[0];
    const dy = y - centroid[1];
    const dist = Math.sqrt(dx * dx + dy * dy);
    const scale = (dist + padding) / dist;
    return [centroid[0] + dx * scale, centroid[1] + dy * scale] as [number, number];
  });

  // Create smooth curve through points
  const lineGenerator = d3.line()
    .curve(d3.curveCardinalClosed.tension(0.7));

  return lineGenerator(paddedHull) || '';
}

// Find all connected nodes (upstream and downstream) from a starting node
function findConnectedNodes(
  startNodeId: string,
  edges: TopologyEdge[],
  maxDepth: number = 10
): { upstream: Set<string>; downstream: Set<string>; connectedEdges: Set<string> } {
  const upstream = new Set<string>();
  const downstream = new Set<string>();
  const connectedEdges = new Set<string>();

  // Build adjacency lists
  const outgoing = new Map<string, { nodeId: string; edgeId: string }[]>();
  const incoming = new Map<string, { nodeId: string; edgeId: string }[]>();

  edges.forEach(edge => {
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    outgoing.get(edge.source)!.push({ nodeId: edge.target, edgeId: edge.id });
    incoming.get(edge.target)!.push({ nodeId: edge.source, edgeId: edge.id });
  });

  // BFS for downstream (what this node connects to)
  const downstreamQueue: { nodeId: string; depth: number }[] = [{ nodeId: startNodeId, depth: 0 }];
  const visitedDown = new Set<string>([startNodeId]);

  while (downstreamQueue.length > 0) {
    const { nodeId, depth } = downstreamQueue.shift()!;
    if (depth >= maxDepth) continue;

    const neighbors = outgoing.get(nodeId) || [];
    for (const { nodeId: neighborId, edgeId } of neighbors) {
      connectedEdges.add(edgeId);
      if (!visitedDown.has(neighborId)) {
        visitedDown.add(neighborId);
        downstream.add(neighborId);
        downstreamQueue.push({ nodeId: neighborId, depth: depth + 1 });
      }
    }
  }

  // BFS for upstream (what connects to this node)
  const upstreamQueue: { nodeId: string; depth: number }[] = [{ nodeId: startNodeId, depth: 0 }];
  const visitedUp = new Set<string>([startNodeId]);

  while (upstreamQueue.length > 0) {
    const { nodeId, depth } = upstreamQueue.shift()!;
    if (depth >= maxDepth) continue;

    const neighbors = incoming.get(nodeId) || [];
    for (const { nodeId: neighborId, edgeId } of neighbors) {
      connectedEdges.add(edgeId);
      if (!visitedUp.has(neighborId)) {
        visitedUp.add(neighborId);
        upstream.add(neighborId);
        upstreamQueue.push({ nodeId: neighborId, depth: depth + 1 });
      }
    }
  }

  return { upstream, downstream, connectedEdges };
}

// Format date for display
function formatDate(date: Date): string {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Export SVG to file - captures full content by calculating bounding box
function exportSvgToFile(svgElement: SVGSVGElement, filename: string, format: 'svg' | 'png') {
  // Get the container group that has all the content
  const container = svgElement.querySelector('g');
  if (!container) return;

  // Get the bounding box of all content
  const bbox = (container as SVGGElement).getBBox();

  // Add padding around the content
  const padding = 50;
  const exportWidth = bbox.width + padding * 2;
  const exportHeight = bbox.height + padding * 2;

  // Create a new SVG element with the right size
  const svgClone = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svgClone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  svgClone.setAttribute('width', String(exportWidth));
  svgClone.setAttribute('height', String(exportHeight));
  svgClone.setAttribute('viewBox', `${bbox.x - padding} ${bbox.y - padding} ${exportWidth} ${exportHeight}`);

  // Add background
  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bg.setAttribute('x', String(bbox.x - padding));
  bg.setAttribute('y', String(bbox.y - padding));
  bg.setAttribute('width', String(exportWidth));
  bg.setAttribute('height', String(exportHeight));
  bg.setAttribute('fill', '#1e293b');
  svgClone.appendChild(bg);

  // Copy defs (markers, etc.)
  const defs = svgElement.querySelector('defs');
  if (defs) {
    svgClone.appendChild(defs.cloneNode(true));
  }

  // Copy the content container (without transform for clean export)
  const contentClone = container.cloneNode(true) as SVGGElement;
  contentClone.removeAttribute('transform'); // Remove zoom/pan transform
  svgClone.appendChild(contentClone);

  const svgData = new XMLSerializer().serializeToString(svgClone);
  const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });

  if (format === 'svg') {
    const url = URL.createObjectURL(svgBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.svg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } else {
    // Convert to PNG with higher resolution
    const scale = 2; // 2x for retina quality
    const canvas = document.createElement('canvas');
    canvas.width = exportWidth * scale;
    canvas.height = exportHeight * scale;
    const ctx = canvas.getContext('2d')!;
    ctx.scale(scale, scale);

    const img = new Image();

    img.onload = () => {
      ctx.drawImage(img, 0, 0, exportWidth, exportHeight);

      canvas.toBlob((blob) => {
        if (blob) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${filename}.png`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        }
      }, 'image/png');
    };

    img.onerror = () => {
      console.error('Failed to load SVG for PNG conversion');
    };

    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
  }
}

export default function Topology() {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  // Search highlight params from URL (e.g., from header search)
  const highlightSourceId = searchParams.get('source');
  const highlightTargetId = searchParams.get('target');
  const hasSearchHighlight = !!(highlightSourceId && highlightTargetId);

  // Track if we've applied the initial search highlight
  const [searchHighlightApplied, setSearchHighlightApplied] = useState(false);

  // Topology filters hook
  const { filters, setFilters, resetFilters, hasActiveFilters } = useTopologyFilters();

  // State
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [highlightedPaths, setHighlightedPaths] = useState<{
    upstream: Set<string>;
    downstream: Set<string>;
    edges: Set<string>;
  } | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [groupingMode, setGroupingMode] = useState<GroupingMode>('none');
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  // Time slider state - now synced with filters hook
  const historicalDate = filters.asOf ? new Date(filters.asOf) : null;
  const setHistoricalDate = useCallback((date: Date | null) => {
    setFilters({ asOf: date?.toISOString() || null });
  }, [setFilters]);
  const [showTimeSlider, setShowTimeSlider] = useState(false);

  // Saved views state
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [viewName, setViewName] = useState('');
  const [viewDescription, setViewDescription] = useState('');
  const [viewIsPublic, setViewIsPublic] = useState(false);
  const [selectedSavedView, setSelectedSavedView] = useState<string | null>(null);

  // Export dropdown
  const [showExportMenu, setShowExportMenu] = useState(false);

  // Legend visibility filters
  const [hiddenGroups, setHiddenGroups] = useState<Set<string>>(new Set());
  const [showInternal, setShowInternal] = useState(true);
  const [showExternal, setShowExternal] = useState(true);

  // Collapsed groups state
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Gateway visualization state
  const [showGateways, setShowGateways] = useState(false);

  // Edge hover state for tooltip
  const [hoveredEdge, setHoveredEdge] = useState<{
    edge: SimLink;
    position: { x: number; y: number };
  } | null>(null);

  // Group positions for dragging (persisted across renders)
  const groupPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());

  // Fetch topology data with filters
  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology', 'graph', filters],
    queryFn: () => topologyApi.getGraph({
      as_of: filters.asOf || undefined,
      environments: filters.environments.length > 0 ? filters.environments : undefined,
      datacenters: filters.datacenters.length > 0 ? filters.datacenters : undefined,
      asset_types: filters.assetTypes.length > 0 ? filters.assetTypes : undefined,
      include_external: filters.includeExternal,
      min_bytes_24h: filters.minBytes24h > 0 ? filters.minBytes24h : undefined,
    }),
  });

  // Fetch gateway topology data (only when showGateways is enabled)
  const { data: gatewayTopology } = useQuery({
    queryKey: ['gateway-topology', filters.asOf],
    queryFn: () => gatewayApi.getTopology({
      min_confidence: 0.6,
      as_of: filters.asOf || undefined,
    }),
    enabled: showGateways,
  });

  // Fetch saved views
  const { data: savedViews } = useQuery({
    queryKey: ['saved-views'],
    queryFn: () => savedViewsApi.list(),
  });

  // Save view mutation
  const saveViewMutation = useMutation({
    mutationFn: (data: { name: string; description?: string; is_public?: boolean; config: ViewConfig }) =>
      savedViewsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-views'] });
      setShowSaveModal(false);
      setViewName('');
      setViewDescription('');
      setViewIsPublic(false);
    },
  });

  // Delete view mutation
  const deleteViewMutation = useMutation({
    mutationFn: (id: string) => savedViewsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-views'] });
      setSelectedSavedView(null);
    },
  });

  // Compute groups from nodes
  const groups = useMemo(() => {
    if (!topology || groupingMode === 'none') return new Map<string, TopologyNode[]>();

    const groupMap = new Map<string, TopologyNode[]>();
    topology.nodes.forEach(node => {
      const key = getGroupKey(node, groupingMode);
      if (!groupMap.has(key)) {
        groupMap.set(key, []);
      }
      groupMap.get(key)!.push(node);
    });
    return groupMap;
  }, [topology, groupingMode]);

  // Assign colors to groups
  const groupColors = useMemo(() => {
    const colorMap = new Map<string, string>();
    let i = 0;
    groups.forEach((_, key) => {
      colorMap.set(key, GROUP_COLORS[i % GROUP_COLORS.length]);
      i++;
    });
    return colorMap;
  }, [groups]);

  // Build node-to-group mapping
  const nodeToGroupMap = useMemo(() => {
    const map = new Map<string, string>();
    if (topology && groupingMode !== 'none') {
      topology.nodes.forEach(node => {
        map.set(node.id, getGroupKey(node, groupingMode));
      });
    }
    return map;
  }, [topology, groupingMode]);

  // Filter nodes based on legend visibility settings and handle collapsed groups
  const filteredTopology = useMemo((): {
    nodes: (TopologyNode & { isGroupNode?: boolean; groupKey?: string; groupNodeCount?: number })[];
    edges: (TopologyEdge & { isAggregated?: boolean; aggregatedCount?: number; originalEdgeIds?: string[]; isGatewayEdge?: boolean; gatewayRole?: string; confidence?: number })[];
  } | null => {
    if (!topology) return null;

    // First, filter by visibility
    const visibleNodes = topology.nodes.filter(node => {
      if (!showInternal && node.is_internal) return false;
      if (!showExternal && !node.is_internal) return false;
      if (groupingMode !== 'none') {
        const groupKey = getGroupKey(node, groupingMode);
        if (hiddenGroups.has(groupKey)) return false;
      }
      return true;
    });

    // If no grouping or no collapsed groups, return filtered topology
    if (groupingMode === 'none' || collapsedGroups.size === 0) {
      const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
      const filteredEdges: (TopologyEdge & { isGatewayEdge?: boolean; gatewayRole?: string; confidence?: number })[] =
        topology.edges.filter(edge =>
          visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
        );

      // Add gateway edges if enabled
      if (showGateways && gatewayTopology) {
        gatewayTopology.edges.forEach(gwEdge => {
          // Only add if both source and target are visible
          if (visibleNodeIds.has(gwEdge.source) && visibleNodeIds.has(gwEdge.target)) {
            filteredEdges.push({
              id: `gw-${gwEdge.id}`,
              source: gwEdge.source,
              target: gwEdge.target,
              target_port: 0,
              protocol: 0,
              protocol_name: null,
              service_type: 'gateway',
              bytes_total: gwEdge.bytes_total,
              bytes_last_24h: 0,
              is_critical: false,
              last_seen: '',
              isGatewayEdge: true,
              gatewayRole: gwEdge.gateway_role,
              confidence: gwEdge.confidence,
            });
          }
        });
      }

      return { nodes: visibleNodes, edges: filteredEdges };
    }

    // Build nodes list with group nodes for collapsed groups
    const resultNodes: (TopologyNode & { isGroupNode?: boolean; groupKey?: string; groupNodeCount?: number })[] = [];
    const collapsedNodeIds = new Set<string>();

    // Add non-collapsed nodes
    visibleNodes.forEach(node => {
      const groupKey = getGroupKey(node, groupingMode);
      if (collapsedGroups.has(groupKey)) {
        collapsedNodeIds.add(node.id);
      } else {
        resultNodes.push(node);
      }
    });

    // Create virtual group nodes for collapsed groups
    collapsedGroups.forEach(groupKey => {
      const nodesInGroup = visibleNodes.filter(n => getGroupKey(n, groupingMode) === groupKey);
      if (nodesInGroup.length === 0) return;

      // Get stored position or compute centroid
      const storedPos = groupPositionsRef.current.get(groupKey);

      // Create a virtual group node
      const groupNode: TopologyNode & { isGroupNode: boolean; groupKey: string; groupNodeCount: number } = {
        id: `group-${groupKey}`,
        name: groupKey,
        label: `${groupKey} (${nodesInGroup.length})`,
        asset_type: 'unknown',
        ip_address: '',
        is_internal: nodesInGroup.some(n => n.is_internal),
        is_critical: nodesInGroup.some(n => n.is_critical),
        environment: nodesInGroup[0]?.environment,
        datacenter: nodesInGroup[0]?.datacenter,
        location: nodesInGroup[0]?.location,
        connections_in: nodesInGroup.reduce((sum, n) => sum + n.connections_in, 0),
        connections_out: nodesInGroup.reduce((sum, n) => sum + n.connections_out, 0),
        bytes_in_24h: nodesInGroup.reduce((sum, n) => sum + (n.bytes_in_24h || 0), 0),
        bytes_out_24h: nodesInGroup.reduce((sum, n) => sum + (n.bytes_out_24h || 0), 0),
        isGroupNode: true,
        groupKey: groupKey,
        groupNodeCount: nodesInGroup.length,
      };

      // Apply stored position if available
      if (storedPos) {
        (groupNode as SimNode).x = storedPos.x;
        (groupNode as SimNode).y = storedPos.y;
      }

      resultNodes.push(groupNode);
    });

    // Build edges with aggregation for collapsed groups
    const resultEdges: (TopologyEdge & { isAggregated?: boolean; aggregatedCount?: number; originalEdgeIds?: string[]; isGatewayEdge?: boolean; gatewayRole?: string; confidence?: number })[] = [];
    const edgeAggregationMap = new Map<string, TopologyEdge & { isAggregated: boolean; aggregatedCount: number; originalEdgeIds: string[] }>();

    topology.edges.forEach(edge => {
      const sourceGroupKey = nodeToGroupMap.get(edge.source);
      const targetGroupKey = nodeToGroupMap.get(edge.target);

      // Skip edges where both endpoints are hidden
      const sourceVisible = visibleNodes.some(n => n.id === edge.source);
      const targetVisible = visibleNodes.some(n => n.id === edge.target);
      if (!sourceVisible || !targetVisible) return;

      // Determine actual source and target (may be group node)
      const sourceIsCollapsed = sourceGroupKey && collapsedGroups.has(sourceGroupKey);
      const targetIsCollapsed = targetGroupKey && collapsedGroups.has(targetGroupKey);

      const actualSource = sourceIsCollapsed ? `group-${sourceGroupKey}` : edge.source;
      const actualTarget = targetIsCollapsed ? `group-${targetGroupKey}` : edge.target;

      // Skip self-loops (when both source and target are in the same collapsed group)
      if (actualSource === actualTarget) return;

      // Create aggregation key
      const aggKey = `${actualSource}->${actualTarget}`;

      if (edgeAggregationMap.has(aggKey)) {
        // Aggregate into existing edge
        const existing = edgeAggregationMap.get(aggKey)!;
        existing.aggregatedCount++;
        existing.bytes_total += edge.bytes_total;
        existing.bytes_last_24h += edge.bytes_last_24h;
        existing.is_critical = existing.is_critical || edge.is_critical;
        existing.originalEdgeIds.push(edge.id);
      } else {
        // Create new aggregated edge
        edgeAggregationMap.set(aggKey, {
          ...edge,
          id: aggKey,
          source: actualSource,
          target: actualTarget,
          isAggregated: !!(sourceIsCollapsed || targetIsCollapsed),
          aggregatedCount: 1,
          originalEdgeIds: [edge.id],
        });
      }
    });

    edgeAggregationMap.forEach(edge => resultEdges.push(edge));

    // Add gateway edges if enabled (for grouped view)
    if (showGateways && gatewayTopology) {
      const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
      gatewayTopology.edges.forEach(gwEdge => {
        // Only add if both source and target are visible
        if (visibleNodeIds.has(gwEdge.source) && visibleNodeIds.has(gwEdge.target)) {
          // Check if nodes are in collapsed groups
          const sourceGroupKey = nodeToGroupMap.get(gwEdge.source);
          const targetGroupKey = nodeToGroupMap.get(gwEdge.target);
          const sourceIsCollapsed = sourceGroupKey && collapsedGroups.has(sourceGroupKey);
          const targetIsCollapsed = targetGroupKey && collapsedGroups.has(targetGroupKey);
          const actualSource = sourceIsCollapsed ? `group-${sourceGroupKey}` : gwEdge.source;
          const actualTarget = targetIsCollapsed ? `group-${targetGroupKey}` : gwEdge.target;

          // Skip self-loops
          if (actualSource === actualTarget) return;

          resultEdges.push({
            id: `gw-${gwEdge.id}`,
            source: actualSource,
            target: actualTarget,
            target_port: 0,
            protocol: 0,
            protocol_name: null,
            service_type: 'gateway',
            bytes_total: gwEdge.bytes_total,
            bytes_last_24h: 0,
            is_critical: false,
            last_seen: '',
            isGatewayEdge: true,
            gatewayRole: gwEdge.gateway_role,
            confidence: gwEdge.confidence,
          });
        }
      });
    }

    return { nodes: resultNodes, edges: resultEdges };
  }, [topology, showInternal, showExternal, hiddenGroups, groupingMode, collapsedGroups, nodeToGroupMap, showGateways, gatewayTopology]);

  // Handle node selection and path highlighting
  const handleNodeClick = useCallback((node: TopologyNode) => {
    if (selectedNode?.id === node.id) {
      // Clicking same node clears selection
      setSelectedNode(null);
      setHighlightedPaths(null);
    } else {
      setSelectedNode(node);
      if (topology) {
        const { upstream, downstream, connectedEdges } = findConnectedNodes(
          node.id,
          topology.edges,
          5 // max depth
        );
        setHighlightedPaths({ upstream, downstream, edges: connectedEdges });
      }
    }
  }, [selectedNode, topology]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelectedNode(null);
    setHighlightedPaths(null);
  }, []);

  // Handle resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const { width, height } = containerRef.current.getBoundingClientRect();
        setDimensions({ width, height: Math.max(height, 500) });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Reset view function
  const resetView = () => {
    if (svgRef.current && zoomRef.current) {
      const svg = d3.select(svgRef.current);
      svg.transition()
        .duration(750)
        .call(zoomRef.current.transform, d3.zoomIdentity);
    }
    clearSelection();
  };

  // Get current view config for saving
  const getCurrentViewConfig = useCallback((): ViewConfig => {
    let zoomState = { scale: 1, x: 0, y: 0 };
    if (svgRef.current) {
      const transform = d3.zoomTransform(svgRef.current);
      zoomState = { scale: transform.k, x: transform.x, y: transform.y };
    }

    return {
      filters: {
        include_external: true,
        min_bytes_24h: 0,
        as_of: historicalDate?.toISOString(),
      },
      grouping: groupingMode,
      zoom: zoomState,
      selected_asset_ids: selectedNode ? [selectedNode.id] : [],
      layout_positions: {},
    };
  }, [groupingMode, historicalDate, selectedNode]);

  // Load a saved view
  const loadSavedView = useCallback(async (viewId: string) => {
    try {
      const view = await savedViewsApi.get(viewId);

      // Apply grouping
      if (view.config.grouping) {
        setGroupingMode(view.config.grouping);
      }

      // Apply historical date
      if (view.config.filters?.as_of) {
        setHistoricalDate(new Date(view.config.filters.as_of));
        setShowTimeSlider(true);
      } else {
        setHistoricalDate(null);
      }

      // Apply zoom
      if (svgRef.current && zoomRef.current && view.config.zoom) {
        const svg = d3.select(svgRef.current);
        svg.transition()
          .duration(750)
          .call(
            zoomRef.current.transform,
            d3.zoomIdentity
              .translate(view.config.zoom.x, view.config.zoom.y)
              .scale(view.config.zoom.scale)
          );
      }

      setSelectedSavedView(viewId);
    } catch (error) {
      console.error('Failed to load saved view:', error);
    }
  }, []);

  // Handle save view
  const handleSaveView = () => {
    if (!viewName.trim()) return;

    saveViewMutation.mutate({
      name: viewName,
      description: viewDescription || undefined,
      is_public: viewIsPublic,
      config: getCurrentViewConfig(),
    });
  };

  // Handle export
  const handleExport = (format: 'svg' | 'png') => {
    if (svgRef.current) {
      const filename = `topology-${new Date().toISOString().split('T')[0]}`;
      exportSvgToFile(svgRef.current, filename, format);
    }
    setShowExportMenu(false);
  };

  // D3 Force simulation
  useEffect(() => {
    if (!svgRef.current || !filteredTopology || filteredTopology.nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const { width, height } = dimensions;

    // Create simulation nodes and links
    const nodes: SimNode[] = filteredTopology.nodes.map((n) => ({ ...n }));
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    const links: SimLink[] = filteredTopology.edges
      .filter((e: TopologyEdge) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e: TopologyEdge) => ({
        ...e,
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
      }));

    // Create zoom behavior
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });

    zoomRef.current = zoom;
    svg.call(zoom);

    // Click on background to clear selection
    svg.on('click', (event) => {
      if (event.target === svgRef.current) {
        clearSelection();
      }
    });

    // Create container for zoom/pan
    const container = svg.append('g');

    // Create group hulls layer (behind nodes)
    const hullGroup = container.append('g').attr('class', 'hulls');

    // Create simulation with group-aware forces
    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(150)
      )
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40));

    // Add grouping force if grouping is enabled
    if (groupingMode !== 'none') {
      // Compute group centers
      const groupCenters = new Map<string, { x: number; y: number }>();
      const groupCount = groups.size;
      let idx = 0;
      groups.forEach((_, key) => {
        const angle = (2 * Math.PI * idx) / groupCount;
        const radius = Math.min(width, height) * 0.25;
        groupCenters.set(key, {
          x: width / 2 + radius * Math.cos(angle),
          y: height / 2 + radius * Math.sin(angle),
        });
        idx++;
      });

      // Add force to pull nodes toward their group center
      simulation.force('group', d3.forceX<SimNode>((d) => {
        const key = getGroupKey(d, groupingMode);
        return groupCenters.get(key)?.x || width / 2;
      }).strength(0.1));

      simulation.force('groupY', d3.forceY<SimNode>((d) => {
        const key = getGroupKey(d, groupingMode);
        return groupCenters.get(key)?.y || height / 2;
      }).strength(0.1));
    }

    // Create arrow markers for different states
    const defs = svg.append('defs');

    // Default arrow
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#475569');

    // Highlighted arrow (upstream - cyan)
    defs.append('marker')
      .attr('id', 'arrowhead-upstream')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#06b6d4');

    // Highlighted arrow (downstream - yellow)
    defs.append('marker')
      .attr('id', 'arrowhead-downstream')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#eab308');

    // Gateway arrow (purple)
    defs.append('marker')
      .attr('id', 'arrowhead-gateway')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#a855f7');

    // Create links - with support for aggregated edges and gateway edges
    const linksGroup = container
      .append('g')
      .attr('class', 'links');

    const link = linksGroup
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('class', (d) => d.isGatewayEdge ? 'edge gateway-edge' : 'edge')
      .attr('stroke', (d) => d.isGatewayEdge ? '#a855f7' : '#475569')
      .attr('stroke-width', (d) => {
        if (d.isGatewayEdge) return 2;
        if (d.isAggregated && d.aggregatedCount && d.aggregatedCount > 1) {
          return Math.min(2 + d.aggregatedCount, 8);
        }
        return 2;
      })
      .attr('stroke-opacity', (d) => d.isGatewayEdge ? 0.8 : 0.6)
      .attr('stroke-dasharray', (d) => d.isGatewayEdge ? '6,3' : 'none')
      .attr('marker-end', (d) => d.isGatewayEdge ? 'url(#arrowhead-gateway)' : 'url(#arrowhead)')
      .style('cursor', 'pointer')
      .on('mouseenter', function (event, d) {
        // Highlight the edge
        d3.select(this)
          .attr('stroke-width', (d as SimLink).isGatewayEdge ? 4 : 4)
          .attr('stroke-opacity', 1);

        // Show tooltip
        setHoveredEdge({
          edge: d,
          position: { x: event.clientX, y: event.clientY },
        });
      })
      .on('mousemove', function (event) {
        // Update tooltip position on mouse move
        setHoveredEdge(prev => prev ? {
          ...prev,
          position: { x: event.clientX, y: event.clientY },
        } : null);
      })
      .on('mouseleave', function (_event, d) {
        // Reset edge style
        d3.select(this)
          .attr('stroke-width', () => {
            if ((d as SimLink).isGatewayEdge) return 2;
            if ((d as SimLink).isAggregated && (d as SimLink).aggregatedCount && (d as SimLink).aggregatedCount! > 1) {
              return Math.min(2 + (d as SimLink).aggregatedCount!, 8);
            }
            return 2;
          })
          .attr('stroke-opacity', (d as SimLink).isGatewayEdge ? 0.8 : 0.6);

        // Hide tooltip
        setHoveredEdge(null);
      });

    // Create port labels on edges
    const edgeLabels = linksGroup
      .selectAll('text.edge-label')
      .data(links.filter(l => !l.isGatewayEdge))
      .join('text')
      .attr('class', 'edge-label')
      .attr('text-anchor', 'middle')
      .attr('fill', '#94a3b8')
      .attr('font-size', 9)
      .attr('pointer-events', 'none')
      .text((d) => {
        if (d.isAggregated && d.aggregatedCount && d.aggregatedCount > 1) {
          return `${d.aggregatedCount} conn`;
        }
        return d.target_port.toString();
      });

    // Create drag behavior for individual nodes
    const dragBehavior = d3
      .drag<SVGGElement, SimNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
        // Store position for group nodes
        if (d.isGroupNode && d.groupKey) {
          groupPositionsRef.current.set(d.groupKey, { x: event.x, y: event.y });
        }
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        // Keep group nodes pinned where they were dragged
        if (d.isGroupNode && d.groupKey) {
          groupPositionsRef.current.set(d.groupKey, { x: d.x!, y: d.y! });
        } else {
          d.fx = null;
          d.fy = null;
        }
      });

    // Create group drag behavior - drags all nodes in the group together
    const groupDragBehavior = d3
      .drag<SVGPathElement, string>()
      .on('start', function (event, groupKey) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        // Fix all nodes in this group at their current positions
        nodes.forEach(n => {
          if (getGroupKey(n, groupingMode) === groupKey) {
            n.fx = n.x;
            n.fy = n.y;
          }
        });
      })
      .on('drag', function (event, groupKey) {
        const dx = event.dx;
        const dy = event.dy;
        // Move all nodes in this group by the drag delta
        nodes.forEach(n => {
          if (getGroupKey(n, groupingMode) === groupKey) {
            const newX = (n.fx ?? n.x ?? 0) + dx;
            const newY = (n.fy ?? n.y ?? 0) + dy;
            n.fx = newX;
            n.fy = newY;
            n.x = newX;
            n.y = newY;
          }
        });
      })
      .on('end', function (event, groupKey) {
        if (!event.active) simulation.alphaTarget(0);
        // Release all nodes in this group
        nodes.forEach(n => {
          if (getGroupKey(n, groupingMode) === groupKey) {
            n.fx = null;
            n.fy = null;
          }
        });
      });

    // Create node groups
    const node = container
      .append('g')
      .attr('class', 'nodes')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('class', (d) => d.isGroupNode ? 'node group-node' : 'node')
      .style('cursor', 'pointer')
      .call(dragBehavior);

    // Add circles to nodes - different styling for group nodes
    node
      .append('circle')
      .attr('r', (d) => d.isGroupNode ? 35 : 20)
      .attr('fill', (d) => {
        if (d.isGroupNode && d.groupKey) {
          return groupColors.get(d.groupKey) || '#6b7280';
        }
        return d.is_internal ? '#10b981' : '#f97316';
      })
      .attr('stroke', (d) => d.isGroupNode ? '#ffffff' : '#1e293b')
      .attr('stroke-width', (d) => d.isGroupNode ? 3 : 2)
      .attr('stroke-dasharray', (d) => d.isGroupNode ? '5,3' : 'none');

    // Add labels to nodes
    node
      .append('text')
      .text((d) => d.isGroupNode ? d.name : (d.name.length > 20 ? d.name.substring(0, 20) + '...' : d.name))
      .attr('dy', (d) => d.isGroupNode ? 55 : 35)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', (d) => d.isGroupNode ? 12 : 11)
      .attr('font-weight', (d) => d.isGroupNode ? 'bold' : 'normal');

    // Add icon/initial to nodes
    node
      .append('text')
      .text((d) => {
        if (d.isGroupNode) {
          return d.groupNodeCount?.toString() || '';
        }
        return d.is_internal ? 'I' : 'E';
      })
      .attr('dy', 5)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', (d) => d.isGroupNode ? 16 : 14)
      .attr('font-weight', 'bold');

    // Handle click - for group nodes, toggle collapse
    node.on('click', (event, d) => {
      event.stopPropagation();
      if (d.isGroupNode && d.groupKey) {
        // Expand the group
        setCollapsedGroups(prev => {
          const next = new Set(prev);
          next.delete(d.groupKey!);
          return next;
        });
      } else {
        handleNodeClick(d);
      }
    });

    // Handle double-click on regular nodes to collapse their group
    node.on('dblclick', (event, d) => {
      event.stopPropagation();
      if (!d.isGroupNode && groupingMode !== 'none') {
        const groupKey = getGroupKey(d, groupingMode);
        setCollapsedGroups(prev => {
          const next = new Set(prev);
          next.add(groupKey);
          return next;
        });
      }
    });

    // Handle hover
    node
      .on('mouseenter', function (_, d) {
        const strokeColor = d.isGroupNode ? '#ffffff' : '#3b82f6';
        d3.select(this).select('circle').attr('stroke', strokeColor).attr('stroke-width', d.isGroupNode ? 4 : 3);
      })
      .on('mouseleave', function (_, d) {
        const isSelected = selectedNode?.id === d.id;
        const isHighlighted = highlightedPaths?.upstream.has(d.id) || highlightedPaths?.downstream.has(d.id);
        if (!isSelected && !isHighlighted) {
          d3.select(this).select('circle')
            .attr('stroke', d.isGroupNode ? '#ffffff' : '#1e293b')
            .attr('stroke-width', d.isGroupNode ? 3 : 2);
        }
      });

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!);

      // Update edge label positions (midpoint of the edge)
      edgeLabels
        .attr('x', (d) => {
          const source = d.source as SimNode;
          const target = d.target as SimNode;
          return (source.x! + target.x!) / 2;
        })
        .attr('y', (d) => {
          const source = d.source as SimNode;
          const target = d.target as SimNode;
          // Offset slightly above the line
          return ((source.y! + target.y!) / 2) - 5;
        });

      node.attr('transform', (d) => `translate(${d.x},${d.y})`);

      // Update group hulls (skip collapsed groups - they show as single nodes)
      if (groupingMode !== 'none') {
        hullGroup.selectAll('*').remove();

        groups.forEach((groupNodes, key) => {
          // Skip collapsed groups - they're represented by group nodes
          if (collapsedGroups.has(key)) return;

          const points: [number, number][] = groupNodes
            .map(gn => {
              const simNode = nodes.find(n => n.id === gn.id);
              if (simNode && simNode.x !== undefined && simNode.y !== undefined) {
                return [simNode.x, simNode.y] as [number, number];
              }
              return null;
            })
            .filter((p): p is [number, number] => p !== null);

          if (points.length >= 3) {
            const hull = computeHull(points);
            if (hull) {
              const color = groupColors.get(key) || '#6b7280';
              const hullPath_ = hullGroup
                .append('path')
                .attr('d', hullPath(hull, 40))
                .attr('fill', color)
                .attr('fill-opacity', 0.1)
                .attr('stroke', color)
                .attr('stroke-width', 2)
                .attr('stroke-opacity', 0.5)
                .style('cursor', 'move')
                .datum(key);

              // Make hull draggable
              hullPath_.call(groupDragBehavior as any);

              // Double-click on hull to collapse the group
              hullPath_.on('dblclick', (event) => {
                event.stopPropagation();
                setCollapsedGroups(prev => {
                  const next = new Set(prev);
                  next.add(key);
                  return next;
                });
              });

              // Add group label
              const centroid = d3.polygonCentroid(hull);
              hullGroup
                .append('text')
                .attr('x', centroid[0])
                .attr('y', centroid[1] - (Math.max(...points.map(p => p[1])) - centroid[1]) - 50)
                .attr('text-anchor', 'middle')
                .attr('fill', color)
                .attr('font-size', 14)
                .attr('font-weight', 'bold')
                .style('pointer-events', 'none')
                .text(key);
            }
          } else if (points.length > 0) {
            // Single or two nodes - draw a circle around them
            const color = groupColors.get(key) || '#6b7280';
            const cx = points.reduce((sum, p) => sum + p[0], 0) / points.length;
            const cy = points.reduce((sum, p) => sum + p[1], 0) / points.length;

            hullGroup
              .append('circle')
              .attr('cx', cx)
              .attr('cy', cy)
              .attr('r', 60)
              .attr('fill', color)
              .attr('fill-opacity', 0.1)
              .attr('stroke', color)
              .attr('stroke-width', 2)
              .attr('stroke-opacity', 0.5)
              .style('cursor', 'move')
              .datum(key)
              .call(groupDragBehavior as any)
              .on('dblclick', (event) => {
                event.stopPropagation();
                setCollapsedGroups(prev => {
                  const next = new Set(prev);
                  next.add(key);
                  return next;
                });
              });

            hullGroup
              .append('text')
              .attr('x', cx)
              .attr('y', cy - 70)
              .attr('text-anchor', 'middle')
              .attr('fill', color)
              .attr('font-size', 14)
              .attr('font-weight', 'bold')
              .style('pointer-events', 'none')
              .text(key);
          }
        });
      }
    });

    // Cleanup
    return () => {
      simulation.stop();
    };
  }, [filteredTopology, dimensions, groupingMode, groups, groupColors, handleNodeClick, clearSelection, collapsedGroups, setCollapsedGroups]);

  // Center and zoom to a specific node
  const centerOnNode = useCallback((nodeId: string) => {
    if (!svgRef.current || !zoomRef.current || !filteredTopology) return;

    const svg = d3.select(svgRef.current);

    // Find the node element
    let targetX: number | undefined;
    let targetY: number | undefined;
    svg.selectAll<SVGGElement, SimNode>('.node').each(function (d) {
      if (d.id === nodeId && d.x !== undefined && d.y !== undefined) {
        targetX = d.x;
        targetY = d.y;
      }
    });

    if (targetX === undefined || targetY === undefined) return;

    const { width, height } = dimensions;
    const scale = 1.5; // Zoom level

    // Calculate transform to center the node
    const x = width / 2 - targetX * scale;
    const y = height / 2 - targetY * scale;

    svg.transition()
      .duration(750)
      .call(
        zoomRef.current.transform,
        d3.zoomIdentity.translate(x, y).scale(scale)
      );
  }, [filteredTopology, dimensions]);

  // Apply search highlight from URL params
  useEffect(() => {
    if (!hasSearchHighlight || searchHighlightApplied || !topology || !filteredTopology) return;

    // Wait for simulation to settle (nodes need positions)
    const timer = setTimeout(() => {
      // Find the source node
      const sourceNode = topology.nodes.find(n => n.id === highlightSourceId);
      if (sourceNode) {
        // Select the source node to highlight the path
        handleNodeClick(sourceNode);

        // Center on the source node
        centerOnNode(highlightSourceId!);

        // Mark as applied
        setSearchHighlightApplied(true);

        // Clear the URL params after applying (optional - keeps URL clean)
        // setSearchParams({});
      }
    }, 1000); // Wait for D3 simulation to stabilize

    return () => clearTimeout(timer);
  }, [hasSearchHighlight, searchHighlightApplied, topology, filteredTopology, highlightSourceId, handleNodeClick, centerOnNode]);

  // Reset search highlight state when URL params change
  useEffect(() => {
    if (!hasSearchHighlight) {
      setSearchHighlightApplied(false);
    }
  }, [hasSearchHighlight]);

  // Update highlighting when selection changes
  useEffect(() => {
    if (!svgRef.current || !topology) return;

    const svg = d3.select(svgRef.current);

    // Update node highlighting
    svg.selectAll<SVGGElement, SimNode>('.node').each(function (d) {
      const nodeGroup = d3.select(this);
      const circle = nodeGroup.select('circle');

      if (selectedNode?.id === d.id) {
        // Selected node - bright white border
        circle
          .attr('stroke', '#ffffff')
          .attr('stroke-width', 4);
      } else if (highlightedPaths?.upstream.has(d.id)) {
        // Upstream node - cyan border
        circle
          .attr('stroke', '#06b6d4')
          .attr('stroke-width', 3);
      } else if (highlightedPaths?.downstream.has(d.id)) {
        // Downstream node - yellow border
        circle
          .attr('stroke', '#eab308')
          .attr('stroke-width', 3);
      } else if (highlightedPaths) {
        // Non-connected node when something is selected - dim
        circle
          .attr('stroke', '#1e293b')
          .attr('stroke-width', 2)
          .attr('opacity', 0.3);
      } else {
        // Default state
        circle
          .attr('stroke', '#1e293b')
          .attr('stroke-width', 2)
          .attr('opacity', 1);
      }
    });

    // Update edge highlighting
    svg.selectAll<SVGLineElement, SimLink>('.edge').each(function (d) {
      const edge = d3.select(this);
      const sourceId = typeof d.source === 'object' ? (d.source as SimNode).id : d.source;
      const targetId = typeof d.target === 'object' ? (d.target as SimNode).id : d.target;

      if (highlightedPaths?.edges.has(d.id)) {
        // Check if this is an upstream or downstream edge
        const isUpstream = highlightedPaths.upstream.has(sourceId as string) ||
                          (selectedNode?.id === targetId);
        const isDownstream = highlightedPaths.downstream.has(targetId as string) ||
                            (selectedNode?.id === sourceId);

        if (isUpstream && !isDownstream) {
          edge
            .attr('stroke', '#06b6d4')
            .attr('stroke-width', 3)
            .attr('stroke-opacity', 1)
            .attr('marker-end', 'url(#arrowhead-upstream)');
        } else if (isDownstream) {
          edge
            .attr('stroke', '#eab308')
            .attr('stroke-width', 3)
            .attr('stroke-opacity', 1)
            .attr('marker-end', 'url(#arrowhead-downstream)');
        } else {
          edge
            .attr('stroke', '#3b82f6')
            .attr('stroke-width', 3)
            .attr('stroke-opacity', 1)
            .attr('marker-end', 'url(#arrowhead)');
        }
      } else if (highlightedPaths) {
        // Non-connected edge when something is selected - dim
        edge
          .attr('stroke', '#475569')
          .attr('stroke-width', 1)
          .attr('stroke-opacity', 0.2)
          .attr('marker-end', 'url(#arrowhead)');
      } else {
        // Default state
        edge
          .attr('stroke', '#475569')
          .attr('stroke-width', 2)
          .attr('stroke-opacity', 0.6)
          .attr('marker-end', 'url(#arrowhead)');
      }
    });

    // Update node labels opacity
    svg.selectAll<SVGGElement, SimNode>('.node').each(function (d) {
      const nodeGroup = d3.select(this);
      const isConnected = selectedNode?.id === d.id ||
                         highlightedPaths?.upstream.has(d.id) ||
                         highlightedPaths?.downstream.has(d.id);

      if (highlightedPaths && !isConnected) {
        nodeGroup.selectAll('text').attr('opacity', 0.3);
      } else {
        nodeGroup.selectAll('text').attr('opacity', 1);
      }
    });
  }, [selectedNode, highlightedPaths, topology]);

  if (isLoading) {
    return <LoadingPage />;
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Topology Map
            {hasActiveFilters() && (
              <span className="ml-2 text-sm font-normal text-primary-400">(Filtered)</span>
            )}
          </h1>
          <p className="text-slate-400 mt-1">
            {hasSearchHighlight && selectedNode
              ? `Search result: ${selectedNode.name}`
              : historicalDate
              ? `Viewing topology as of ${formatDate(historicalDate)}`
              : selectedNode
              ? `Showing dependencies for ${selectedNode.name}`
              : 'Click a node to highlight its dependencies'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Show Gateways toggle */}
          <Button
            variant={showGateways ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setShowGateways(!showGateways)}
          >
            {showGateways ? 'Hide Gateways' : 'Show Gateways'}
          </Button>

          {/* Time slider toggle */}
          <Button
            variant={showTimeSlider ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setShowTimeSlider(!showTimeSlider)}
          >
            Time Travel
          </Button>

          {/* Saved views dropdown */}
          <div className="relative">
            <select
              value={selectedSavedView || ''}
              onChange={(e) => {
                if (e.target.value) {
                  loadSavedView(e.target.value);
                } else {
                  setSelectedSavedView(null);
                }
              }}
              className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">Saved Views</option>
              {savedViews?.map((view: SavedViewSummary) => (
                <option key={view.id} value={view.id}>
                  {view.name}
                </option>
              ))}
            </select>
          </div>

          {/* Save view button */}
          <Button variant="secondary" size="sm" onClick={() => setShowSaveModal(true)}>
            Save View
          </Button>

          {/* Export dropdown */}
          <div className="relative">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowExportMenu(!showExportMenu)}
            >
              Export
            </Button>
            {showExportMenu && (
              <div className="absolute right-0 mt-1 w-32 bg-slate-700 border border-slate-600 rounded-lg shadow-lg z-10">
                <button
                  className="w-full px-4 py-2 text-left text-sm text-slate-100 hover:bg-slate-600 rounded-t-lg"
                  onClick={() => handleExport('svg')}
                >
                  Export SVG
                </button>
                <button
                  className="w-full px-4 py-2 text-left text-sm text-slate-100 hover:bg-slate-600 rounded-b-lg"
                  onClick={() => handleExport('png')}
                >
                  Export PNG
                </button>
              </div>
            )}
          </div>

          {/* Grouping dropdown */}
          <select
            value={groupingMode}
            onChange={(e) => setGroupingMode(e.target.value as GroupingMode)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="none">No Grouping</option>
            <option value="location">Group by Location</option>
            <option value="environment">Group by Environment</option>
            <option value="datacenter">Group by Datacenter</option>
            <option value="type">Group by Type</option>
          </select>
          {selectedNode && (
            <Button variant="ghost" size="sm" onClick={clearSelection}>
              Clear Selection
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={resetView}>
            Reset View
          </Button>
        </div>
      </div>

      {/* Time Slider */}
      {showTimeSlider && (
        <Card className="mb-4">
          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-400">Historical View:</span>
            <input
              type="datetime-local"
              value={historicalDate ? historicalDate.toISOString().slice(0, 16) : ''}
              onChange={(e) => {
                if (e.target.value) {
                  setHistoricalDate(new Date(e.target.value));
                } else {
                  setHistoricalDate(null);
                }
              }}
              className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            {historicalDate && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setHistoricalDate(null)}
              >
                Clear
              </Button>
            )}
            <div className="flex-1" />
            <span className="text-xs text-slate-500">
              View the topology as it existed at a specific point in time
            </span>
          </div>
        </Card>
      )}

      {/* Save View Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-96">
            <h2 className="text-lg font-semibold text-white mb-4">Save View</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Name</label>
                <input
                  type="text"
                  value={viewName}
                  onChange={(e) => setViewName(e.target.value)}
                  placeholder="My View"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Description (optional)</label>
                <textarea
                  value={viewDescription}
                  onChange={(e) => setViewDescription(e.target.value)}
                  placeholder="Describe this view..."
                  rows={2}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is-public"
                  checked={viewIsPublic}
                  onChange={(e) => setViewIsPublic(e.target.checked)}
                  className="rounded border-slate-600 bg-slate-700 text-primary-500 focus:ring-primary-500"
                />
                <label htmlFor="is-public" className="text-sm text-slate-300">
                  Share with team
                </label>
              </div>
              <div className="flex justify-end gap-2 pt-4">
                <Button variant="ghost" onClick={() => setShowSaveModal(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={handleSaveView}
                  disabled={!viewName.trim() || saveViewMutation.isPending}
                >
                  {saveViewMutation.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      <div className="flex-1 flex gap-4">
        {/* Filter Panel */}
        <FilterPanel
          filters={filters}
          onFiltersChange={setFilters}
          onReset={resetFilters}
          hasActiveFilters={hasActiveFilters()}
        />

        {/* Graph Area */}
        <div
          ref={containerRef}
          className="flex-1 bg-slate-800 border border-slate-700 rounded-lg overflow-hidden"
        >
          {!filteredTopology || filteredTopology.nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-400">
              {topology && topology.nodes.length > 0
                ? 'All nodes are hidden. Adjust legend filters to show nodes.'
                : 'No topology data available'}
            </div>
          ) : (
            <svg
              ref={svgRef}
              width="100%"
              height="100%"
              viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
              preserveAspectRatio="xMidYMid meet"
            />
          )}
        </div>

        {/* Legend and Details Panel */}
        <div className="w-72 space-y-4">
          {/* Legend */}
          <Card title="Legend">
            <div className="space-y-3">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Node Types (click to toggle)</div>
              <div className="space-y-2">
                <label className="flex items-center gap-2 cursor-pointer hover:bg-slate-700/50 px-2 py-1 rounded -mx-2">
                  <input
                    type="checkbox"
                    checked={showInternal}
                    onChange={(e) => setShowInternal(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-700 text-green-500 focus:ring-green-500"
                  />
                  <div className="w-4 h-4 rounded-full bg-green-500" />
                  <span className="text-sm text-slate-300 flex-1">Internal (I)</span>
                  <span className="text-xs text-slate-500">
                    ({topology?.nodes.filter(n => n.is_internal).length || 0})
                  </span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer hover:bg-slate-700/50 px-2 py-1 rounded -mx-2">
                  <input
                    type="checkbox"
                    checked={showExternal}
                    onChange={(e) => setShowExternal(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-700 text-orange-500 focus:ring-orange-500"
                  />
                  <div className="w-4 h-4 rounded-full bg-orange-500" />
                  <span className="text-sm text-slate-300 flex-1">External (E)</span>
                  <span className="text-xs text-slate-500">
                    ({topology?.nodes.filter(n => !n.is_internal).length || 0})
                  </span>
                </label>
              </div>

              {showGateways && (
                <>
                  <div className="text-xs text-slate-400 uppercase tracking-wider mt-4 mb-2">Gateway Edges</div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <div className="w-8 border-t-2 border-dashed border-purple-500" />
                      <span className="text-sm text-slate-300">Gateway Route</span>
                      <span className="text-xs text-slate-500">
                        ({gatewayTopology?.edges.length || 0})
                      </span>
                    </div>
                  </div>
                </>
              )}

              {selectedNode && (
                <>
                  <div className="text-xs text-slate-400 uppercase tracking-wider mt-4 mb-2">Path Highlighting</div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded-full border-2 border-white bg-transparent" />
                      <span className="text-sm text-slate-300">Selected</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded-full border-2 border-cyan-400 bg-transparent" />
                      <span className="text-sm text-slate-300">Upstream ({highlightedPaths?.upstream.size || 0})</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded-full border-2 border-yellow-400 bg-transparent" />
                      <span className="text-sm text-slate-300">Downstream ({highlightedPaths?.downstream.size || 0})</span>
                    </div>
                  </div>
                </>
              )}

              {groupingMode !== 'none' && groups.size > 0 && (
                <>
                  <div className="text-xs text-slate-400 uppercase tracking-wider mt-4 mb-2">
                    Groups
                    <span className="text-slate-500 font-normal ml-1">(dbl-click to collapse)</span>
                  </div>
                  <div className="space-y-2">
                    {Array.from(groupColors.entries()).map(([name, color]) => (
                      <div key={name} className="flex items-center gap-2 hover:bg-slate-700/50 px-2 py-1 rounded -mx-2">
                        <input
                          type="checkbox"
                          checked={!hiddenGroups.has(name)}
                          onChange={(e) => {
                            const newHidden = new Set(hiddenGroups);
                            if (e.target.checked) {
                              newHidden.delete(name);
                            } else {
                              newHidden.add(name);
                            }
                            setHiddenGroups(newHidden);
                          }}
                          className="rounded border-slate-600 bg-slate-700 focus:ring-primary-500"
                          style={{ accentColor: color }}
                        />
                        <div
                          className="w-4 h-4 rounded"
                          style={{ backgroundColor: color, opacity: 0.5 }}
                        />
                        <span className="text-sm text-slate-300 flex-1">{name}</span>
                        <span className="text-xs text-slate-500">
                          ({groups.get(name)?.length || 0})
                        </span>
                        <button
                          onClick={() => {
                            setCollapsedGroups(prev => {
                              const next = new Set(prev);
                              if (next.has(name)) {
                                next.delete(name);
                              } else {
                                next.add(name);
                              }
                              return next;
                            });
                          }}
                          className="p-1 rounded hover:bg-slate-600 text-slate-400 hover:text-white transition-colors"
                          title={collapsedGroups.has(name) ? 'Expand group' : 'Collapse group'}
                        >
                          {collapsedGroups.has(name) ? (
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                  {collapsedGroups.size > 0 && (
                    <button
                      onClick={() => setCollapsedGroups(new Set())}
                      className="mt-2 text-xs text-primary-400 hover:text-primary-300"
                    >
                      Expand all groups
                    </button>
                  )}
                </>
              )}
            </div>
          </Card>

          {/* Selected Node Details */}
          {selectedNode && (
            <Card title="Selected Asset">
              <div className="space-y-3">
                <div>
                  <span className="text-sm text-slate-400">Name</span>
                  <p className="text-white font-medium">{selectedNode.name}</p>
                </div>
                <div>
                  <span className="text-sm text-slate-400">Type</span>
                  <p className="text-white capitalize">
                    {selectedNode.asset_type?.replace('_', ' ') ?? 'Unknown'}
                  </p>
                </div>
                {selectedNode.ip_address && (
                  <div>
                    <span className="text-sm text-slate-400">IP Address</span>
                    <p className="text-white">{selectedNode.ip_address}</p>
                  </div>
                )}
                <div>
                  <span className="text-sm text-slate-400">Location</span>
                  <p className="text-white">
                    {selectedNode.is_internal ? 'Internal' : 'External'}
                  </p>
                </div>
                <div>
                  <span className="text-sm text-slate-400">Connections</span>
                  <p className="text-white">
                    {highlightedPaths?.upstream.size || 0} upstream, {highlightedPaths?.downstream.size || 0} downstream
                  </p>
                </div>
                {selectedNode.environment && (
                  <div>
                    <span className="text-sm text-slate-400">Environment</span>
                    <p className="text-white">{selectedNode.environment}</p>
                  </div>
                )}
                {selectedNode.datacenter && (
                  <div>
                    <span className="text-sm text-slate-400">Datacenter</span>
                    <p className="text-white">{selectedNode.datacenter}</p>
                  </div>
                )}
                <Button
                  variant="primary"
                  size="sm"
                  className="w-full"
                  onClick={() =>
                    (window.location.href = `/assets/${selectedNode.id}`)
                  }
                >
                  View Details
                </Button>
              </div>
            </Card>
          )}

          {/* Saved View Actions */}
          {selectedSavedView && (
            <Card title="Current View">
              <div className="space-y-3">
                <p className="text-sm text-slate-300">
                  {savedViews?.find((v: SavedViewSummary) => v.id === selectedSavedView)?.name}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full text-red-400 hover:text-red-300"
                  onClick={() => {
                    if (confirm('Delete this saved view?')) {
                      deleteViewMutation.mutate(selectedSavedView);
                    }
                  }}
                >
                  Delete View
                </Button>
              </div>
            </Card>
          )}

          {/* Stats */}
          <Card title="Statistics">
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-400">Visible Nodes</span>
                <span className="text-white">
                  {filteredTopology?.nodes.length ?? 0}
                  {filteredTopology && topology && filteredTopology.nodes.length !== topology.nodes.length && (
                    <span className="text-slate-500"> / {topology.nodes.length}</span>
                  )}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Visible Edges</span>
                <span className="text-white">
                  {filteredTopology?.edges.length ?? 0}
                  {filteredTopology && topology && filteredTopology.edges.length !== topology.edges.length && (
                    <span className="text-slate-500"> / {topology.edges.length}</span>
                  )}
                </span>
              </div>
              {groupingMode !== 'none' && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Groups</span>
                  <span className="text-white">
                    {groups.size - hiddenGroups.size}
                    {hiddenGroups.size > 0 && (
                      <span className="text-slate-500"> / {groups.size}</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* Edge Tooltip */}
      {hoveredEdge && (
        <EdgeTooltip
          edge={{
            source: {
              name: (hoveredEdge.edge.source as SimNode).name,
              ip_address: (hoveredEdge.edge.source as SimNode).ip_address || '',
            },
            target: {
              name: (hoveredEdge.edge.target as SimNode).name,
              ip_address: (hoveredEdge.edge.target as SimNode).ip_address || '',
            },
            target_port: hoveredEdge.edge.target_port,
            protocol: hoveredEdge.edge.protocol,
            bytes_last_24h: hoveredEdge.edge.bytes_last_24h,
            last_seen: hoveredEdge.edge.last_seen,
            service_type: hoveredEdge.edge.service_type,
          }}
          position={hoveredEdge.position}
          containerBounds={containerRef.current?.getBoundingClientRect()}
        />
      )}
    </div>
  );
}
