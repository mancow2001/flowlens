import { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as d3 from 'd3';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import FilterPanel from '../components/topology/FilterPanel';
import EdgeTooltip from '../components/topology/EdgeTooltip';
import CanvasTopologyRenderer from '../components/topology/CanvasTopologyRenderer';
import TopologySettingsDialog, {
  type TopologySettings,
  type RenderMode,
  DEFAULT_SETTINGS,
} from '../components/topology/TopologySettings';
import { useTopologyFilters } from '../hooks/useTopologyFilters';
import { topologyApi, savedViewsApi, gatewayApi } from '../services/api';
import { getServiceName } from '../utils/network';
// Static layout algorithms - will be used when layout settings are implemented
// import { applyLayout, type LayoutType } from '../utils/graphLayouts';
import type { TopologyNode, TopologyEdge, SavedViewSummary, ViewConfig } from '../types';

// Get edge label text showing port/service info
function getEdgeLabel(ports: number[] | undefined, targetPort: number): string {
  const portsToShow = ports && ports.length > 0 ? ports : [targetPort];
  if (portsToShow.length === 0 || (portsToShow.length === 1 && portsToShow[0] === 0)) {
    return '';
  }

  // For single port, show service name if available
  if (portsToShow.length === 1) {
    const port = portsToShow[0];
    const service = getServiceName(port);
    return service ? `${service.toLowerCase()} (${port})` : `${port}`;
  }

  // For multiple ports, show count or abbreviated list
  if (portsToShow.length <= 3) {
    return portsToShow.map(p => {
      const service = getServiceName(p);
      return service ? `${service.toLowerCase()} (${p})` : `${p}`;
    }).join(', ');
  }

  return `${portsToShow.length} ports`;
}

// Determine edge color based on properties
function getEdgeColor(sourceNode: SimNode, targetNode: SimNode, isCritical: boolean): string {
  // Critical edges are red
  if (isCritical) {
    return '#ef4444'; // red
  }
  // Edges to/from external nodes are amber/orange
  if (!sourceNode.is_internal || !targetNode.is_internal) {
    return '#f97316'; // orange
  }
  // Default internal edges are green
  return '#22c55e'; // green
}

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
  // Multiple ports between same source/target
  target_ports?: number[];
  // Gateway edge properties
  isGatewayEdge?: boolean;
  gatewayRole?: string;
  confidence?: number;
}

type GroupingMode = 'none' | 'location' | 'environment' | 'datacenter' | 'type';

// Infrastructure service types (these are typically "noise" in topology views)
const INFRASTRUCTURE_SERVICES = new Set([
  'infrastructure',
  'dns',
  'dhcp',
  'dhcp-server',
  'dhcp-client',
  'dhcpv6-client',
  'dhcpv6-server',
  'ntp',
  'snmp',
  'snmptrap',
  'syslog',
  'rpcbind',
  'msrpc',
  'netbios-ns',
  'netbios-dgm',
  'netbios-ssn',
  'rip',
  'upnp',
]);

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
  const simulationRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const [isLocatingNode, setIsLocatingNode] = useState(false);

  // Refs for callbacks and state used in D3 to avoid re-running the effect when they change
  const handleNodeClickRef = useRef<(node: TopologyNode) => void>(() => {});
  const clearSelectionRef = useRef<() => void>(() => {});
  const selectedNodeRef = useRef<TopologyNode | null>(null);
  const highlightedPathsRef = useRef<{
    upstream: Set<string>;
    downstream: Set<string>;
    edges: Set<string>;
  } | null>(null);

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

  // Topology performance settings
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [topologySettings, setTopologySettings] = useState<TopologySettings>(DEFAULT_SETTINGS);

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
  // Use getSubgraph when a focused endpoint is set, otherwise use getGraph for full topology
  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology', 'graph', filters],
    queryFn: () => {
      // When a focused endpoint is set, use the subgraph endpoint for proper depth-based traversal
      if (filters.focusedEndpoint) {
        return topologyApi.getSubgraph(
          filters.focusedEndpoint,
          filters.hopLevel
        );
      }
      // Otherwise, use the full topology graph endpoint
      return topologyApi.getGraph({
        as_of: filters.asOf || undefined,
        environments: filters.environments.length > 0 ? filters.environments : undefined,
        datacenters: filters.datacenters.length > 0 ? filters.datacenters : undefined,
        asset_types: filters.assetTypes.length > 0 ? filters.assetTypes : undefined,
        include_external: filters.includeExternal,
        min_bytes_24h: filters.minBytes24h > 0 ? filters.minBytes24h : undefined,
      });
    },
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
    let visibleNodes = topology.nodes.filter(node => {
      if (!showInternal && node.is_internal) return false;
      if (!showExternal && !node.is_internal) return false;
      if (groupingMode !== 'none') {
        const groupKey = getGroupKey(node, groupingMode);
        if (hiddenGroups.has(groupKey)) return false;
      }
      return true;
    });

    // Filter out nodes that only have infrastructure service edges
    if (filters.hideInfrastructureOnly) {
      // Build a map of node -> has non-infrastructure edges
      const nodeHasNonInfraEdge = new Map<string, boolean>();

      // Initialize all nodes as having no non-infra edges
      visibleNodes.forEach(node => nodeHasNonInfraEdge.set(node.id, false));

      // Check each edge
      topology.edges.forEach(edge => {
        const serviceType = edge.service_type?.toLowerCase() || '';
        const isInfraEdge = INFRASTRUCTURE_SERVICES.has(serviceType);

        if (!isInfraEdge) {
          // This edge is NOT infrastructure, so mark both nodes as having non-infra edges
          nodeHasNonInfraEdge.set(edge.source, true);
          nodeHasNonInfraEdge.set(edge.target, true);
        }
      });

      // Filter out nodes that only have infrastructure edges (but keep nodes with no edges)
      visibleNodes = visibleNodes.filter(node => {
        const hasNonInfra = nodeHasNonInfraEdge.get(node.id);
        // Keep if: has non-infra edges, OR has no edges at all
        const nodeEdgeCount = topology.edges.filter(
          e => e.source === node.id || e.target === node.id
        ).length;
        return hasNonInfra || nodeEdgeCount === 0;
      });
    }

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
  }, [topology, showInternal, showExternal, hiddenGroups, groupingMode, collapsedGroups, nodeToGroupMap, showGateways, gatewayTopology, filters.hideInfrastructureOnly]);

  // Determine render mode based on settings and graph size
  const effectiveRenderMode = useMemo((): RenderMode => {
    if (topologySettings.renderMode !== 'auto') {
      return topologySettings.renderMode;
    }
    // Auto mode: use Canvas for large graphs
    const nodeCount = filteredTopology?.nodes.length ?? 0;
    const edgeCount = filteredTopology?.edges.length ?? 0;
    return nodeCount > 200 || edgeCount > 500 ? 'canvas' : 'svg';
  }, [topologySettings.renderMode, filteredTopology?.nodes.length, filteredTopology?.edges.length]);

  // Check if we have a large graph
  const isLargeGraph = useMemo(() => {
    const nodeCount = filteredTopology?.nodes.length ?? 0;
    const edgeCount = filteredTopology?.edges.length ?? 0;
    return nodeCount > 200 || edgeCount > 500;
  }, [filteredTopology?.nodes.length, filteredTopology?.edges.length]);

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

  // Handle Canvas edge hover - convert RenderEdge format to SimLink format for EdgeTooltip
  const handleCanvasEdgeHover = useCallback((edge: {
    id: string;
    source: TopologyNode;
    target: TopologyNode;
    targetPort: number;
    targetPorts?: number[];
    protocol: number;
    bytesTotal: number;
    isCritical: boolean;
  } | null, position: { x: number; y: number }) => {
    if (edge) {
      // Convert to SimLink-compatible format for the tooltip
      setHoveredEdge({
        edge: {
          id: edge.id,
          source: edge.source as SimNode,
          target: edge.target as SimNode,
          target_port: edge.targetPort,
          target_ports: edge.targetPorts,
          protocol: edge.protocol,
          protocol_name: null,
          service_type: null,
          bytes_total: edge.bytesTotal,
          bytes_last_24h: edge.bytesTotal, // Use total as fallback
          is_critical: edge.isCritical,
          last_seen: new Date().toISOString(),
        },
        position,
      });
    } else {
      setHoveredEdge(null);
    }
  }, []);

  // Keep refs updated with latest callbacks and state (for D3 to use without causing re-renders)
  useEffect(() => {
    handleNodeClickRef.current = handleNodeClick;
    clearSelectionRef.current = clearSelection;
  }, [handleNodeClick, clearSelection]);

  useEffect(() => {
    selectedNodeRef.current = selectedNode;
    highlightedPathsRef.current = highlightedPaths;
  }, [selectedNode, highlightedPaths]);

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

    // First, filter valid edges
    const validEdges = filteredTopology.edges.filter(
      (e: TopologyEdge) => nodeMap.has(e.source) && nodeMap.has(e.target)
    );

    // Aggregate edges between the same source/target pair to collect multiple ports
    const edgeAggregation = new Map<string, {
      edge: TopologyEdge;
      ports: number[];
    }>();

    validEdges.forEach((e: TopologyEdge) => {
      const key = `${e.source}->${e.target}`;
      if (edgeAggregation.has(key)) {
        const existing = edgeAggregation.get(key)!;
        // Add port if not already present
        if (!existing.ports.includes(e.target_port)) {
          existing.ports.push(e.target_port);
        }
        // Aggregate traffic stats
        existing.edge.bytes_total += e.bytes_total;
        existing.edge.bytes_last_24h += e.bytes_last_24h;
        existing.edge.is_critical = existing.edge.is_critical || e.is_critical;
      } else {
        edgeAggregation.set(key, {
          edge: { ...e },
          ports: [e.target_port],
        });
      }
    });

    // Create links from aggregated edges
    const links: SimLink[] = Array.from(edgeAggregation.values()).map(({ edge, ports }) => ({
      ...edge,
      source: nodeMap.get(edge.source)!,
      target: nodeMap.get(edge.target)!,
      target_ports: ports.sort((a, b) => a - b), // Sort ports for consistent display
    }));

    // Calculate edge indices for curved paths (to avoid overlapping edges between same nodes)
    const edgePairCount = new Map<string, number>();
    const edgeIndices = new Map<string, { index: number; total: number }>();

    // First pass: count edges between each pair of nodes (both directions)
    links.forEach(link => {
      const sourceId = (link.source as SimNode).id;
      const targetId = (link.target as SimNode).id;
      // Use sorted IDs to group edges in both directions
      const pairKey = [sourceId, targetId].sort().join('|');
      edgePairCount.set(pairKey, (edgePairCount.get(pairKey) || 0) + 1);
    });

    // Second pass: assign index to each edge
    const edgePairIndex = new Map<string, number>();
    links.forEach(link => {
      const sourceId = (link.source as SimNode).id;
      const targetId = (link.target as SimNode).id;
      const pairKey = [sourceId, targetId].sort().join('|');
      const total = edgePairCount.get(pairKey) || 1;
      const currentIndex = edgePairIndex.get(pairKey) || 0;
      edgeIndices.set(link.id, { index: currentIndex, total });
      edgePairIndex.set(pairKey, currentIndex + 1);
    });

    // Function to calculate curved path between two points
    const getCurvedPath = (
      sx: number, sy: number, tx: number, ty: number,
      edgeIndex: number, totalEdges: number, isReversed: boolean
    ): string => {
      // If only one edge, use a straight line
      if (totalEdges === 1) {
        return `M ${sx} ${sy} L ${tx} ${ty}`;
      }

      // Calculate midpoint
      const mx = (sx + tx) / 2;
      const my = (sy + ty) / 2;

      // Calculate perpendicular offset direction
      const dx = tx - sx;
      const dy = ty - sy;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len === 0) return `M ${sx} ${sy} L ${tx} ${ty}`;

      // Perpendicular unit vector
      const px = -dy / len;
      const py = dx / len;

      // Calculate offset amount - spread edges evenly
      const spacing = 25; // pixels between parallel edges
      const offsetIndex = edgeIndex - (totalEdges - 1) / 2;
      let offset = offsetIndex * spacing;

      // Reverse offset direction for edges going the opposite way
      if (isReversed) {
        offset = -offset;
      }

      // Control point for quadratic bezier
      const cx = mx + px * offset;
      const cy = my + py * offset;

      return `M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`;
    };

    // Function to get curve midpoint for label positioning
    const getCurveMidpoint = (
      sx: number, sy: number, tx: number, ty: number,
      edgeIndex: number, totalEdges: number, isReversed: boolean
    ): { x: number; y: number } => {
      if (totalEdges === 1) {
        return { x: (sx + tx) / 2, y: (sy + ty) / 2 };
      }

      const mx = (sx + tx) / 2;
      const my = (sy + ty) / 2;
      const dx = tx - sx;
      const dy = ty - sy;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len === 0) return { x: mx, y: my };

      const px = -dy / len;
      const py = dx / len;
      const spacing = 25;
      const offsetIndex = edgeIndex - (totalEdges - 1) / 2;
      let offset = offsetIndex * spacing;
      if (isReversed) offset = -offset;

      // For quadratic bezier, the midpoint of the curve is at t=0.5
      // B(0.5) = 0.25*P0 + 0.5*C + 0.25*P1
      const cx = mx + px * offset;
      const cy = my + py * offset;
      return {
        x: 0.25 * sx + 0.5 * cx + 0.25 * tx,
        y: 0.25 * sy + 0.5 * cy + 0.25 * ty,
      };
    };

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
        clearSelectionRef.current();
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

    // Store simulation ref for external access (e.g., stopping before centering)
    simulationRef.current = simulation;

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

    // Highlighted arrow (upstream - bright cyan)
    defs.append('marker')
      .attr('id', 'arrowhead-upstream')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#22d3ee');

    // Highlighted arrow (downstream - bright amber)
    defs.append('marker')
      .attr('id', 'arrowhead-downstream')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#fbbf24');

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

    // Green arrow (internal edges)
    defs.append('marker')
      .attr('id', 'arrowhead-green')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#22c55e');

    // Orange arrow (external edges)
    defs.append('marker')
      .attr('id', 'arrowhead-orange')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#f97316');

    // Red arrow (critical edges)
    defs.append('marker')
      .attr('id', 'arrowhead-red')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#ef4444');

    // Create links - with support for aggregated edges and gateway edges
    const linksGroup = container
      .append('g')
      .attr('class', 'links');

    // Helper to get marker URL based on edge color
    const getMarkerUrl = (d: SimLink): string => {
      if (d.isGatewayEdge) return 'url(#arrowhead-gateway)';
      const sourceNode = d.source as SimNode;
      const targetNode = d.target as SimNode;
      if (d.is_critical) return 'url(#arrowhead-red)';
      if (!sourceNode.is_internal || !targetNode.is_internal) return 'url(#arrowhead-orange)';
      return 'url(#arrowhead-green)';
    };

    const link = linksGroup
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('class', (d) => d.isGatewayEdge ? 'edge gateway-edge' : 'edge')
      .attr('fill', 'none')
      .attr('stroke', (d) => {
        if (d.isGatewayEdge) return '#a855f7';
        return getEdgeColor(d.source as SimNode, d.target as SimNode, d.is_critical);
      })
      .attr('stroke-width', (d) => {
        if (d.isGatewayEdge) return 2;
        if (d.isAggregated && d.aggregatedCount && d.aggregatedCount > 1) {
          return Math.min(2 + d.aggregatedCount, 8);
        }
        return 2;
      })
      .attr('stroke-opacity', (d) => d.isGatewayEdge ? 0.8 : 0.7)
      .attr('stroke-dasharray', (d) => d.isGatewayEdge ? '6,3' : 'none')
      .attr('marker-end', getMarkerUrl)
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
          .attr('stroke-opacity', (d as SimLink).isGatewayEdge ? 0.8 : 0.7);

        // Hide tooltip
        setHoveredEdge(null);
      });

    // Create edge labels group
    const edgeLabelsGroup = container
      .append('g')
      .attr('class', 'edge-labels');

    // Create edge labels showing port/service info
    const edgeLabel = edgeLabelsGroup
      .selectAll('text')
      .data(links.filter(d => !d.isGatewayEdge))
      .join('text')
      .attr('class', 'edge-label')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', 10)
      .attr('font-weight', 500)
      .attr('paint-order', 'stroke')
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 3)
      .attr('stroke-linecap', 'round')
      .attr('stroke-linejoin', 'round')
      .style('pointer-events', 'none')
      .text((d) => getEdgeLabel(d.target_ports, d.target_port));

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
        handleNodeClickRef.current(d);
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

    // Handle hover - but don't override highlighted/selected states
    node
      .on('mouseenter', function (_, d) {
        // Skip hover effect if node is selected or highlighted (use refs for current state)
        const isSelected = selectedNodeRef.current?.id === d.id;
        const isUpstream = highlightedPathsRef.current?.upstream.has(d.id);
        const isDownstream = highlightedPathsRef.current?.downstream.has(d.id);
        if (isSelected || isUpstream || isDownstream) return;

        // Only apply hover effect to non-highlighted nodes
        const strokeColor = d.isGroupNode ? '#ffffff' : '#3b82f6';
        d3.select(this).select('circle').attr('stroke', strokeColor).attr('stroke-width', d.isGroupNode ? 4 : 3);
      })
      .on('mouseleave', function (_, d) {
        const isSelected = selectedNodeRef.current?.id === d.id;
        const isUpstream = highlightedPathsRef.current?.upstream.has(d.id);
        const isDownstream = highlightedPathsRef.current?.downstream.has(d.id);

        // Don't change anything for highlighted/selected nodes
        if (isSelected || isUpstream || isDownstream) return;

        // Restore default state for non-highlighted nodes
        d3.select(this).select('circle')
          .attr('stroke', d.isGroupNode ? '#ffffff' : '#1e293b')
          .attr('stroke-width', d.isGroupNode ? 3 : 2);
      });

    // Update positions on tick
    simulation.on('tick', () => {
      // Update curved paths for edges
      link.attr('d', (d) => {
        const sourceNode = d.source as SimNode;
        const targetNode = d.target as SimNode;
        const sx = sourceNode.x!;
        const sy = sourceNode.y!;
        const tx = targetNode.x!;
        const ty = targetNode.y!;

        const edgeInfo = edgeIndices.get(d.id) || { index: 0, total: 1 };
        // Check if this edge goes from lower to higher sorted ID (for consistent curve direction)
        const isReversed = sourceNode.id > targetNode.id;

        return getCurvedPath(sx, sy, tx, ty, edgeInfo.index, edgeInfo.total, isReversed);
      });

      // Position edge labels at curve midpoint
      edgeLabel
        .attr('x', (d) => {
          const sourceNode = d.source as SimNode;
          const targetNode = d.target as SimNode;
          const edgeInfo = edgeIndices.get(d.id) || { index: 0, total: 1 };
          const isReversed = sourceNode.id > targetNode.id;
          const midpoint = getCurveMidpoint(
            sourceNode.x!, sourceNode.y!,
            targetNode.x!, targetNode.y!,
            edgeInfo.index, edgeInfo.total, isReversed
          );
          return midpoint.x;
        })
        .attr('y', (d) => {
          const sourceNode = d.source as SimNode;
          const targetNode = d.target as SimNode;
          const edgeInfo = edgeIndices.get(d.id) || { index: 0, total: 1 };
          const isReversed = sourceNode.id > targetNode.id;
          const midpoint = getCurveMidpoint(
            sourceNode.x!, sourceNode.y!,
            targetNode.x!, targetNode.y!,
            edgeInfo.index, edgeInfo.total, isReversed
          );
          return midpoint.y;
        })
        .attr('transform', (d) => {
          // Rotate label to follow edge angle at the midpoint
          const sourceNode = d.source as SimNode;
          const targetNode = d.target as SimNode;
          const edgeInfo = edgeIndices.get(d.id) || { index: 0, total: 1 };
          const isReversed = sourceNode.id > targetNode.id;
          const midpoint = getCurveMidpoint(
            sourceNode.x!, sourceNode.y!,
            targetNode.x!, targetNode.y!,
            edgeInfo.index, edgeInfo.total, isReversed
          );

          // Calculate tangent angle at midpoint (for quadratic bezier, use line from source to target as approximation)
          let angle = Math.atan2(targetNode.y! - sourceNode.y!, targetNode.x! - sourceNode.x!) * (180 / Math.PI);
          // Keep text readable (not upside down)
          if (angle > 90 || angle < -90) {
            angle += 180;
          }
          return `rotate(${angle}, ${midpoint.x}, ${midpoint.y})`;
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
  }, [filteredTopology, dimensions, groupingMode, groups, groupColors, collapsedGroups, setCollapsedGroups]);

  // Center and zoom to a specific node
  const centerOnNode = useCallback((nodeId: string) => {
    if (!svgRef.current || !zoomRef.current || !filteredTopology) {
      return;
    }

    // Stop the simulation to prevent it from moving nodes after we center
    if (simulationRef.current) {
      simulationRef.current.stop();
    }

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

    if (targetX === undefined || targetY === undefined) {
      return;
    }

    // Use the dimensions state which matches the SVG viewBox
    const { width, height } = dimensions;
    const scale = 1.5; // Zoom level

    // Calculate transform to center the node in the viewBox
    const x = width / 2 - targetX * scale;
    const y = height / 2 - targetY * scale;

    const newTransform = d3.zoomIdentity.translate(x, y).scale(scale);

    // Apply transform with transition
    svg.transition()
      .duration(750)
      .call(zoomRef.current.transform, newTransform);
  }, [filteredTopology, dimensions]);

  // Apply search highlight from URL params
  useEffect(() => {
    if (!hasSearchHighlight || searchHighlightApplied || !filteredTopology || !svgRef.current) {
      return;
    }

    // Find the source node in filtered topology
    const sourceNode = filteredTopology.nodes.find(n => n.id === highlightSourceId);

    if (!sourceNode) {
      // Node not in filtered view - try finding in full topology
      const nodeInFull = topology?.nodes.find(n => n.id === highlightSourceId);

      if (nodeInFull) {
        // Node exists but is filtered out - clear filters and retry
        resetFilters();
        return;
      }

      // Node doesn't exist in topology at all
      setSearchHighlightApplied(true);
      return;
    }

    // Show locating indicator and wait 3 seconds for simulation to settle
    setIsLocatingNode(true);

    const timer = setTimeout(() => {
      handleNodeClick(sourceNode);
      centerOnNode(highlightSourceId!);
      setSearchHighlightApplied(true);
      setIsLocatingNode(false);
    }, 3000);

    return () => {
      clearTimeout(timer);
      setIsLocatingNode(false);
    };
  }, [hasSearchHighlight, searchHighlightApplied, topology, filteredTopology, highlightSourceId, handleNodeClick, centerOnNode, resetFilters]);

  // Reset search highlight state when URL params change to new values
  useEffect(() => {
    // Reset when params change so the highlight effect can re-run
    setSearchHighlightApplied(false);
  }, [highlightSourceId, highlightTargetId]);

  // Update highlighting when selection changes
  useEffect(() => {
    if (!svgRef.current || !topology) return;

    const svg = d3.select(svgRef.current);

    // Update node highlighting
    svg.selectAll<SVGGElement, SimNode>('.node').each(function (d) {
      const nodeGroup = d3.select(this);
      const circle = nodeGroup.select('circle');

      if (selectedNode?.id === d.id) {
        // Selected node - bright white border, thick stroke
        circle
          .attr('stroke', '#ffffff')
          .attr('stroke-width', 6)
          .attr('opacity', 1);
      } else if (highlightedPaths?.upstream.has(d.id)) {
        // Upstream node - bright cyan border
        circle
          .attr('stroke', '#22d3ee') // brighter cyan
          .attr('stroke-width', 5)
          .attr('opacity', 1);
      } else if (highlightedPaths?.downstream.has(d.id)) {
        // Downstream node - bright yellow/amber border
        circle
          .attr('stroke', '#fbbf24') // brighter amber
          .attr('stroke-width', 5)
          .attr('opacity', 1);
      } else if (highlightedPaths) {
        // Non-connected node when something is selected - heavily dim
        circle
          .attr('stroke', '#1e293b')
          .attr('stroke-width', 1)
          .attr('opacity', 0.12);
      } else {
        // Default state
        circle
          .attr('stroke', '#1e293b')
          .attr('stroke-width', 2)
          .attr('opacity', 1);
      }
    });

    // Update edge highlighting
    svg.selectAll<SVGPathElement, SimLink>('.edge').each(function (d) {
      const edge = d3.select(this);
      const sourceId = typeof d.source === 'object' ? (d.source as SimNode).id : d.source;
      const targetId = typeof d.target === 'object' ? (d.target as SimNode).id : d.target;
      const sourceNode = d.source as SimNode;
      const targetNode = d.target as SimNode;

      if (highlightedPaths?.edges.has(d.id)) {
        // Check if this is an upstream or downstream edge
        const isUpstream = highlightedPaths.upstream.has(sourceId as string) ||
                          (selectedNode?.id === targetId);
        const isDownstream = highlightedPaths.downstream.has(targetId as string) ||
                            (selectedNode?.id === sourceId);

        if (isUpstream && !isDownstream) {
          edge
            .attr('stroke', '#22d3ee') // brighter cyan
            .attr('stroke-width', 4)
            .attr('stroke-opacity', 1)
            .attr('marker-end', 'url(#arrowhead-upstream)');
        } else if (isDownstream) {
          edge
            .attr('stroke', '#fbbf24') // brighter amber
            .attr('stroke-width', 4)
            .attr('stroke-opacity', 1)
            .attr('marker-end', 'url(#arrowhead-downstream)');
        } else {
          edge
            .attr('stroke', '#3b82f6')
            .attr('stroke-width', 4)
            .attr('stroke-opacity', 1)
            .attr('marker-end', 'url(#arrowhead)');
        }
      } else if (highlightedPaths) {
        // Non-connected edge when something is selected - heavily dim
        edge
          .attr('stroke', '#475569')
          .attr('stroke-width', 1)
          .attr('stroke-opacity', 0.06)
          .attr('marker-end', null);
      } else {
        // Default state - use dynamic colors based on edge type
        if (d.isGatewayEdge) {
          edge
            .attr('stroke', '#a855f7')
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.8)
            .attr('marker-end', 'url(#arrowhead-gateway)');
        } else {
          const color = getEdgeColor(sourceNode, targetNode, d.is_critical);
          const markerUrl = d.is_critical ? 'url(#arrowhead-red)' :
            (!sourceNode.is_internal || !targetNode.is_internal) ? 'url(#arrowhead-orange)' :
            'url(#arrowhead-green)';
          edge
            .attr('stroke', color)
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.7)
            .attr('marker-end', markerUrl);
        }
      }
    });

    // Update edge labels opacity
    svg.selectAll<SVGTextElement, SimLink>('.edge-label').each(function (d) {
      const label = d3.select(this);
      const sourceId = typeof d.source === 'object' ? (d.source as SimNode).id : d.source;
      const targetId = typeof d.target === 'object' ? (d.target as SimNode).id : d.target;
      const isConnected = highlightedPaths?.edges.has(d.id) ||
                         highlightedPaths?.upstream.has(sourceId as string) ||
                         highlightedPaths?.downstream.has(targetId as string);

      if (highlightedPaths && !isConnected) {
        label.attr('opacity', 0.1);
      } else {
        label.attr('opacity', 1);
      }
    });

    // Update node labels opacity
    svg.selectAll<SVGGElement, SimNode>('.node').each(function (d) {
      const nodeGroup = d3.select(this);
      const isConnected = selectedNode?.id === d.id ||
                         highlightedPaths?.upstream.has(d.id) ||
                         highlightedPaths?.downstream.has(d.id);

      if (highlightedPaths && !isConnected) {
        nodeGroup.selectAll('text').attr('opacity', 0.15);
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
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowSettingsDialog(true)}
            title="Performance & Layout Settings"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </Button>
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
          className="flex-1 bg-slate-800 border border-slate-700 rounded-lg overflow-hidden relative"
        >
          {!filteredTopology || filteredTopology.nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-400">
              {topology && topology.nodes.length > 0
                ? 'All nodes are hidden. Adjust legend filters to show nodes.'
                : 'No topology data available'}
            </div>
          ) : effectiveRenderMode === 'canvas' ? (
            <CanvasTopologyRenderer
              nodes={filteredTopology.nodes}
              edges={filteredTopology.edges}
              width={dimensions.width}
              height={dimensions.height}
              selectedNodeId={selectedNode?.id ?? null}
              highlightedPaths={highlightedPaths}
              groupingMode={groupingMode}
              groupColors={groupColors}
              onNodeClick={handleNodeClick}
              onBackgroundClick={clearSelection}
              onEdgeHover={handleCanvasEdgeHover}
              performanceMode={topologySettings.performanceMode}
              layoutType={topologySettings.layoutType}
            />
          ) : (
            <svg
              ref={svgRef}
              width="100%"
              height="100%"
              viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
              preserveAspectRatio="xMidYMid meet"
            />
          )}

          {/* Render mode indicator */}
          {isLargeGraph && filteredTopology && (
            <div className="absolute bottom-4 left-4 bg-slate-900/80 rounded-lg px-3 py-1.5 text-xs text-slate-300 flex items-center gap-2 pointer-events-none">
              <span className={effectiveRenderMode === 'canvas' ? 'text-green-400' : 'text-amber-400'}>
                {effectiveRenderMode === 'canvas' ? 'Canvas' : 'SVG'}
              </span>
              <span className="text-slate-500">|</span>
              <span>{filteredTopology.nodes.length} nodes</span>
              <span className="text-slate-500">|</span>
              <span>{filteredTopology.edges.length} edges</span>
            </div>
          )}

          {/* Locating node indicator */}
          {isLocatingNode && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-slate-900/90 border border-primary-500 rounded-lg px-4 py-2 flex items-center gap-3 shadow-lg z-50">
              <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-primary-400 font-medium">Locating node...</span>
            </div>
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

              <div className="text-xs text-slate-400 uppercase tracking-wider mt-4 mb-2">Edge Colors</div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-8 border-t-2 border-green-500" />
                  <span className="text-sm text-slate-300">Internal</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 border-t-2 border-orange-500" />
                  <span className="text-sm text-slate-300">External</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-8 border-t-2 border-red-500" />
                  <span className="text-sm text-slate-300">Critical</span>
                </div>
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
            target_ports: hoveredEdge.edge.target_ports,
            protocol: hoveredEdge.edge.protocol,
            bytes_last_24h: hoveredEdge.edge.bytes_last_24h,
            last_seen: hoveredEdge.edge.last_seen,
            service_type: hoveredEdge.edge.service_type,
          }}
          position={hoveredEdge.position}
          containerBounds={containerRef.current?.getBoundingClientRect()}
        />
      )}

      {/* Topology Settings Dialog */}
      <TopologySettingsDialog
        isOpen={showSettingsDialog}
        onClose={() => setShowSettingsDialog(false)}
        settings={topologySettings}
        onSettingsChange={setTopologySettings}
        nodeCount={filteredTopology?.nodes.length ?? 0}
        edgeCount={filteredTopology?.edges.length ?? 0}
      />
    </div>
  );
}
