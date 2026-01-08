import { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as d3 from 'd3';
import {
  ArrowLeftIcon,
  InformationCircleIcon,
  UsersIcon,
  CpuChipIcon,
  PencilIcon,
  ArrowPathIcon,
  Squares2X2Icon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import { LoadingPage } from '../components/common/Loading';
import EdgeTooltip from '../components/topology/EdgeTooltip';
import ApplicationDetailCanvas from '../components/topology/ApplicationDetailCanvas';
import GroupEditModal from '../components/layout/GroupEditModal';
import BaselinePanel from '../components/baseline/BaselinePanel';
import { applicationsApi, layoutApi } from '../services/api';
import { getProtocolName, formatProtocolPort, formatBytes, getEdgeLabelForPort } from '../utils/network';
import type { AssetType, InboundSummary, NodePosition } from '../types';

type RenderMode = 'auto' | 'svg' | 'canvas';

// Entry point in topology data
interface TopologyEntryPointInfo {
  id: string;
  port: number;
  protocol: number;
  order: number;
  label: string | null;
}

// D3 simulation node extending the API response
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
  // For client summary nodes
  is_client_summary?: boolean;
  client_count?: number;
  total_bytes_24h?: number;
  target_entry_point_id?: string;
  // Legacy fields for client summary nodes (port/protocol for the specific entry point)
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

// Infrastructure service types (typically "noise" in topology views)
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

// Color scheme for nodes
const NODE_COLORS = {
  entry_point: '#eab308', // yellow for entry points
  internal: '#3b82f6', // blue for internal members
  external: '#6b7280', // gray for external
  critical: '#ef4444', // red for critical
  client_summary: '#10b981', // green for client summary
};

// Layout positions - dynamically calculated based on hop distance
const getLayoutX = (hopDistance: number) => {
  const clientX = 80;        // Client summary nodes (leftmost)
  const entryPointX = 200;   // Entry points (hop 0)
  const hopSpacing = 180;    // Spacing between each hop level

  if (hopDistance < 0) return clientX;  // Client summary
  if (hopDistance === 0) return entryPointX;  // Entry points
  return entryPointX + (hopDistance * hopSpacing);  // Downstream by hop
};

// Legacy layout for backwards compatibility
const LAYOUT = {
  clientX: 80,      // X position for client summary nodes (left)
  entryPointX: 200, // X position for entry points (center-left)
  memberX: 380,     // Starting X for hop 1 members
};

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<{
    edge: SimLink;
    position: { x: number; y: number };
  } | null>(null);
  const [showExternal, setShowExternal] = useState(false);
  const [maxDepth, setMaxDepth] = useState(1);
  const [renderMode, setRenderMode] = useState<RenderMode>('auto');
  const [hideInfrastructureOnly, setHideInfrastructureOnly] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<Set<string>>(new Set());
  const [showGroupModal, setShowGroupModal] = useState(false);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const transformRef = useRef<d3.ZoomTransform | null>(null);
  const queryClient = useQueryClient();

  // Fetch saved layout for this application and hop depth
  const { data: savedLayout } = useQuery({
    queryKey: ['application-layout', id, maxDepth],
    queryFn: () => layoutApi.getLayout(id!, maxDepth),
    enabled: !!id,
    staleTime: 30000, // Cache for 30 seconds
  });

  // Mutation to save positions on drag end
  // Note: We don't invalidate the query on success to avoid re-rendering the view
  // The local node positions are already updated via D3 drag
  const savePositionsMutation = useMutation({
    mutationFn: (positions: Record<string, NodePosition>) =>
      layoutApi.updatePositions(id!, maxDepth, { positions }),
  });

  // Reset layout to auto-calculated positions
  const resetLayoutMutation = useMutation({
    mutationFn: () => layoutApi.resetLayout(id!, maxDepth),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application-layout', id, maxDepth] });
    },
  });

  // Create asset group
  const createGroupMutation = useMutation({
    mutationFn: (data: { name: string; color: string; asset_ids: string[] }) =>
      layoutApi.createGroup(id!, maxDepth, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application-layout', id, maxDepth] });
      setSelectedNodes(new Set());
      setShowGroupModal(false);
    },
  });

  // Delete asset group
  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => layoutApi.deleteGroup(id!, maxDepth, groupId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application-layout', id, maxDepth] });
    },
  });

  // Handle creating a group from selected nodes
  const handleCreateGroup = useCallback(
    (name: string, color: string) => {
      if (selectedNodes.size < 2) return;
      createGroupMutation.mutate({
        name,
        color,
        asset_ids: Array.from(selectedNodes),
      });
    },
    [selectedNodes, createGroupMutation]
  );

  // Callback to save positions on drag end
  const handleNodeDragEnd = useCallback(
    (nodeId: string, x: number, y: number, allNodePositions?: Record<string, { x: number; y: number }>) => {
      if (!editMode) return;

      // If multiple nodes are selected and we have all positions, save all of them
      if (selectedNodes.size > 1 && selectedNodes.has(nodeId) && allNodePositions) {
        const positionsToSave: Record<string, NodePosition> = {};
        selectedNodes.forEach(id => {
          if (allNodePositions[id]) {
            positionsToSave[id] = { x: allNodePositions[id].x, y: allNodePositions[id].y };
          }
        });
        savePositionsMutation.mutate(positionsToSave);
      } else {
        // Single node drag
        savePositionsMutation.mutate({ [nodeId]: { x, y } });
      }
    },
    [editMode, selectedNodes, savePositionsMutation]
  );

  // Handle node click for selection
  const handleNodeClick = useCallback(
    (nodeId: string, event: MouseEvent) => {
      if (!editMode) return;

      if (event.shiftKey) {
        // Shift+click: toggle selection
        setSelectedNodes(prev => {
          const next = new Set(prev);
          if (next.has(nodeId)) {
            next.delete(nodeId);
          } else {
            next.add(nodeId);
          }
          return next;
        });
      } else {
        // Regular click: select only this node (or deselect if already solo-selected)
        setSelectedNodes(prev => {
          if (prev.size === 1 && prev.has(nodeId)) {
            return new Set();
          }
          return new Set([nodeId]);
        });
      }
    },
    [editMode]
  );

  // Clear selection when exiting edit mode
  useEffect(() => {
    if (!editMode) {
      setSelectedNodes(new Set());
    }
  }, [editMode]);

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && editMode) {
        if (selectedNodes.size > 0) {
          setSelectedNodes(new Set());
        } else {
          setEditMode(false);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [editMode, selectedNodes.size]);

  // Fetch application topology
  const { data: topology, isLoading, error } = useQuery({
    queryKey: ['application-topology', id, showExternal, maxDepth],
    queryFn: () => applicationsApi.getTopology(id!, showExternal, maxDepth),
    enabled: !!id,
  });

  // Reset transform when topology query changes (new data warrants a view reset)
  useEffect(() => {
    transformRef.current = null;
  }, [id, maxDepth, showExternal]);

  // Transform data for D3 with hierarchical layout based on hop distance
  const { nodes, links } = useMemo(() => {
    if (!topology) return { nodes: [], links: [] };

    const { height } = dimensions;
    const simNodes: SimNode[] = [];
    const simLinks: SimLink[] = [];

    // Get saved positions from layout
    const savedPositions = savedLayout?.positions || {};

    // Group nodes by hop distance
    const nodesByHop: Map<number, typeof topology.nodes> = new Map();
    topology.nodes.forEach(node => {
      const hop = node.hop_distance ?? 0;
      if (!nodesByHop.has(hop)) nodesByHop.set(hop, []);
      nodesByHop.get(hop)!.push(node);
    });

    // Create nodes positioned by hop distance (columns)
    // If saved position exists, use it; otherwise use auto-calculated position
    nodesByHop.forEach((nodesAtHop, hopDistance) => {
      const defaultXPos = getLayoutX(hopDistance);
      const ySpacing = height / (nodesAtHop.length + 1);

      nodesAtHop.forEach((node, i) => {
        const defaultYPos = ySpacing * (i + 1);
        const saved = savedPositions[node.id];

        // Use saved position if available, otherwise use auto-calculated
        const xPos = saved?.x ?? defaultXPos;
        const yPos = saved?.y ?? defaultYPos;

        simNodes.push({
          ...node,
          hop_distance: hopDistance,
          x: xPos,
          y: yPos,
          // If we have a saved position, fix both X and Y; otherwise just fix X for column layout
          fx: saved ? xPos : defaultXPos,
          fy: saved ? yPos : undefined,
        });
      });
    });

    // Create client summary nodes from inbound_summary (leftmost column)
    if (topology.inbound_summary) {
      // Filter to only summaries with clients
      const clientSummaries = topology.inbound_summary.filter(s => s.client_count > 0);
      const clientYSpacing = height / (clientSummaries.length + 1);

      clientSummaries.forEach((summary: InboundSummary, summaryIndex: number) => {
        // Include port and protocol in ID to ensure uniqueness when same asset has multiple entry points
        const clientNodeId = `client-summary-${summary.entry_point_asset_id}-${summary.port}-${summary.protocol}`;
        const defaultXPos = getLayoutX(-1); // -1 for client summary column
        const defaultYPos = clientYSpacing * (summaryIndex + 1);

        // Check for saved position
        const saved = savedPositions[clientNodeId];
        const xPos = saved?.x ?? defaultXPos;
        const yPos = saved?.y ?? defaultYPos;

        simNodes.push({
          id: clientNodeId,
          name: `${summary.client_count} clients`,
          display_name: null,
          ip_address: '',
          asset_type: 'client_summary',
          is_entry_point: false,
          entry_points: [],
          entry_point_port: summary.port,
          entry_point_protocol: summary.protocol,
          entry_point_order: null,
          role: null,
          is_critical: false,
          is_external: true,
          is_client_summary: true,
          client_count: summary.client_count,
          total_bytes_24h: summary.total_bytes_24h,
          target_entry_point_id: summary.entry_point_asset_id,
          hop_distance: -1,
          x: xPos,
          y: yPos,
          fx: xPos,
          fy: yPos,
        });

        simLinks.push({
          id: `${clientNodeId}-${summary.entry_point_asset_id}`,
          source: clientNodeId,
          target: summary.entry_point_asset_id,
          target_port: summary.port,
          protocol: summary.protocol ?? 6,
          dependency_type: null,
          bytes_last_24h: summary.total_bytes_24h,
          last_seen: null,
          is_internal: false,
          is_from_client_summary: true,
        });
      });
    }

    // Create edges from topology.edges
    // Only show edges that progress from one hop level to the next
    // (hop 0 -> hop 1 -> hop 2 -> ... -> hop N)
    const nodeMap = new Map(simNodes.map(n => [n.id, n]));
    topology.edges.forEach((edge, i) => {
      if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) return;

      const sourceNode = nodeMap.get(edge.source)!;
      const targetNode = nodeMap.get(edge.target)!;
      const sourceHop = sourceNode.hop_distance ?? 0;
      const targetHop = targetNode.hop_distance ?? 0;

      // Only show edges where target is exactly one hop further than source
      // This creates the progression: entry point (0) -> hop 1 -> hop 2 -> etc.
      if (targetHop !== sourceHop + 1) return;

      simLinks.push({
        id: `${edge.source}-${edge.target}-${i}`,
        source: edge.source,
        target: edge.target,
        target_port: edge.target_port,
        protocol: edge.protocol,
        dependency_type: edge.dependency_type,
        bytes_last_24h: edge.bytes_last_24h,
        last_seen: edge.last_seen,
        is_internal: edge.is_internal,
        is_from_client_summary: false,
      });
    });

    // Filter out infrastructure-only nodes if enabled
    if (hideInfrastructureOnly) {
      // Build a map of node -> has non-infrastructure edges
      const nodeHasNonInfraEdge = new Map<string, boolean>();
      simNodes.forEach(node => nodeHasNonInfraEdge.set(node.id, false));

      // Check each edge to see if it's infrastructure
      simLinks.forEach(edge => {
        const serviceType = edge.dependency_type?.toLowerCase() || '';
        const isInfraEdge = INFRASTRUCTURE_SERVICES.has(serviceType);

        if (!isInfraEdge) {
          const sourceId = typeof edge.source === 'string' ? edge.source : (edge.source as SimNode).id;
          const targetId = typeof edge.target === 'string' ? edge.target : (edge.target as SimNode).id;
          nodeHasNonInfraEdge.set(sourceId, true);
          nodeHasNonInfraEdge.set(targetId, true);
        }
      });

      // Keep entry points and nodes with non-infrastructure edges
      const filteredNodes = simNodes.filter(node => {
        if (node.is_entry_point || node.is_client_summary) return true;
        return nodeHasNonInfraEdge.get(node.id) === true;
      });

      const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
      const filteredLinks = simLinks.filter(edge => {
        const sourceId = typeof edge.source === 'string' ? edge.source : (edge.source as SimNode).id;
        const targetId = typeof edge.target === 'string' ? edge.target : (edge.target as SimNode).id;
        return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
      });

      return { nodes: filteredNodes, links: filteredLinks };
    }

    return { nodes: simNodes, links: simLinks };
  }, [topology, dimensions, maxDepth, hideInfrastructureOnly, savedLayout]);

  // Determine effective render mode based on graph size
  const effectiveRenderMode = useMemo((): 'svg' | 'canvas' => {
    if (renderMode !== 'auto') {
      return renderMode;
    }
    // Auto mode: use Canvas for larger graphs
    const nodeCount = nodes.length;
    const edgeCount = links.length;
    return nodeCount > 50 || edgeCount > 100 ? 'canvas' : 'svg';
  }, [renderMode, nodes.length, links.length]);

  // Check if graph is large enough to recommend Canvas
  const isLargeGraph = nodes.length > 50 || links.length > 100;

  // Handle container resize
  useEffect(() => {
    if (!containerRef.current) return;

    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        const newWidth = Math.floor(rect.width);
        const newHeight = Math.floor(rect.height);
        // Only update if dimensions actually changed and are valid
        if (newWidth > 0 && newHeight > 0) {
          setDimensions(prev => {
            if (prev.width !== newWidth || prev.height !== newHeight) {
              return { width: newWidth, height: newHeight };
            }
            return prev;
          });
        }
      }
    };

    // Initial update with a slight delay to ensure layout is complete
    updateDimensions();
    const initialTimeout = setTimeout(updateDimensions, 100);

    // ResizeObserver for container size changes
    const resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(updateDimensions);
    });
    resizeObserver.observe(containerRef.current);

    // Window resize listener as fallback
    window.addEventListener('resize', updateDimensions);

    return () => {
      clearTimeout(initialTimeout);
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateDimensions);
    };
  }, []);

  // D3 force simulation with hierarchical layout (only for SVG mode)
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0 || effectiveRenderMode === 'canvas') return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const { height } = dimensions;

    // Main group for zoom/pan
    const g = svg.append('g');

    // Create zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
        // Save transform for restoration after re-renders
        transformRef.current = event.transform;
      });

    svg.call(zoom);
    zoomRef.current = zoom;

    // Restore previous transform if available
    if (transformRef.current) {
      svg.call(zoom.transform, transformRef.current);
      g.attr('transform', transformRef.current.toString());
    }

    // Click on background clears edge tooltip
    svg.on('click', () => {
      setHoveredEdge(null);
    });

    // Define arrow markers
    const defs = svg.append('defs');
    defs
      .append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#64748b');

    // Client summary marker (green)
    defs
      .append('marker')
      .attr('id', 'client-arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#10b981');

    // Entry point marker (yellow)
    defs
      .append('marker')
      .attr('id', 'entry-point-marker')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#eab308');

    // Create simulation with horizontal force to push members right
    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(120)
          .strength(0.3) // Weaker links to allow position forces to work
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('collision', d3.forceCollide().radius(45))
      // Push non-fixed nodes towards the right side
      .force('x', d3.forceX<SimNode>()
        .x((d) => {
          if (d.fx !== undefined && d.fx !== null) return d.fx; // Fixed nodes stay
          return LAYOUT.memberX + 100; // Members pulled right
        })
        .strength(0.3)
      )
      .force('y', d3.forceY<SimNode>()
        .y(height / 2)
        .strength(0.05) // Weak vertical centering
      );

    // Draw links
    const linksGroup = g.append('g').attr('class', 'links');
    const linkElements = linksGroup
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('fill', 'none')
      .attr('stroke', (d) => d.is_from_client_summary ? '#10b981' : '#64748b')
      .attr('stroke-width', (d) => d.is_from_client_summary ? 3 : 2)
      .attr('stroke-opacity', 0.6)
      .attr('stroke-dasharray', (d) => d.is_from_client_summary ? '5,5' : 'none')
      .attr('marker-end', (d) =>
        d.is_from_client_summary ? 'url(#client-arrowhead)' : 'url(#arrowhead)'
      )
      .style('cursor', 'pointer')
      .on('mouseenter', function (event, d) {
        d3.select(this).attr('stroke-width', 6).attr('stroke-opacity', 1);
        setHoveredEdge({
          edge: d,
          position: { x: event.clientX, y: event.clientY },
        });
      })
      .on('mousemove', function (event) {
        setHoveredEdge((prev) =>
          prev ? { ...prev, position: { x: event.clientX, y: event.clientY } } : null
        );
      })
      .on('mouseleave', function (_, d) {
        d3.select(this)
          .attr('stroke-width', d.is_from_client_summary ? 3 : 2)
          .attr('stroke-opacity', 0.6);
        setHoveredEdge(null);
      })
      .on('click', function (event) {
        // Prevent click from bubbling to SVG background
        event.stopPropagation();
      });

    // Port labels on edges
    const edgeLabels = linksGroup
      .selectAll('text.edge-label')
      .data(links)
      .join('text')
      .attr('class', 'edge-label')
      .attr('text-anchor', 'middle')
      .attr('fill', '#94a3b8')
      .attr('font-size', 10)
      .attr('pointer-events', 'none')
      .text((d) => getEdgeLabelForPort(d.target_port));

    // Draw asset groups (render before nodes so they appear behind)
    const assetGroups = savedLayout?.groups || [];
    const groupsGroup = g.append('g').attr('class', 'groups');

    // Create a map of node positions for group bounds calculation
    const nodePositionMap = new Map<string, SimNode>();
    nodes.forEach(n => nodePositionMap.set(n.id, n));

    // Function to calculate group bounds based on member nodes
    const calculateGroupBounds = (group: { asset_ids: string[] }) => {
      const memberNodes = group.asset_ids
        .map(id => nodePositionMap.get(id))
        .filter((n): n is SimNode => n !== undefined && n.x !== undefined && n.y !== undefined);

      if (memberNodes.length === 0) return null;

      const padding = 30;
      const xs = memberNodes.map(n => n.x!);
      const ys = memberNodes.map(n => n.y!);

      return {
        x: Math.min(...xs) - padding,
        y: Math.min(...ys) - padding,
        width: Math.max(...xs) - Math.min(...xs) + padding * 2,
        height: Math.max(...ys) - Math.min(...ys) + padding * 2,
      };
    };

    const groupElements = groupsGroup
      .selectAll<SVGGElement, typeof assetGroups[number]>('g.asset-group')
      .data(assetGroups)
      .join('g')
      .attr('class', 'asset-group');

    // Group background rectangles
    groupElements
      .append('rect')
      .attr('class', 'group-bounds')
      .attr('rx', 12)
      .attr('ry', 12)
      .attr('fill', d => d.color + '15')
      .attr('stroke', d => d.color)
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '4,2');

    // Group labels
    groupElements
      .append('text')
      .attr('class', 'group-label')
      .attr('fill', d => d.color)
      .attr('font-size', 12)
      .attr('font-weight', 'bold')
      .text(d => d.name);

    // Delete buttons for groups (only in edit mode)
    if (editMode) {
      groupElements
        .append('text')
        .attr('class', 'group-delete')
        .attr('fill', '#ef4444')
        .attr('font-size', 14)
        .attr('cursor', 'pointer')
        .text('×')
        .on('click', (event, d) => {
          event.stopPropagation();
          if (confirm(`Delete group "${d.name}"?`)) {
            deleteGroupMutation.mutate(d.id);
          }
        });
    }

    // Draw nodes
    const nodesGroup = g.append('g').attr('class', 'nodes');

    // Track drag start positions for multi-select dragging
    let dragStartPositions: Map<string, { x: number; y: number }> = new Map();

    const nodeElements = nodesGroup
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;

            // If in edit mode and dragging a selected node, track all selected nodes
            if (editMode && selectedNodes.has(d.id)) {
              dragStartPositions.clear();
              nodes.forEach(n => {
                if (selectedNodes.has(n.id)) {
                  dragStartPositions.set(n.id, { x: n.x ?? 0, y: n.y ?? 0 });
                }
              });
            }
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;

            // In edit mode, move all selected nodes together
            if (editMode && selectedNodes.has(d.id) && selectedNodes.size > 1) {
              const startPos = dragStartPositions.get(d.id);
              if (startPos) {
                const dx = event.x - startPos.x;
                const dy = event.y - startPos.y;

                nodes.forEach(n => {
                  if (selectedNodes.has(n.id) && n.id !== d.id) {
                    const nStartPos = dragStartPositions.get(n.id);
                    if (nStartPos) {
                      n.fx = nStartPos.x + dx;
                      n.fy = nStartPos.y + dy;
                    }
                  }
                });
              }
            }
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            // In edit mode, save the position and keep it fixed
            if (editMode) {
              // Collect all node positions for multi-select save
              const allPositions: Record<string, { x: number; y: number }> = {};
              nodes.forEach(n => {
                if (n.fx != null && n.fy != null) {
                  allPositions[n.id] = { x: n.fx, y: n.fy };
                }
              });

              handleNodeDragEnd(d.id, event.x, event.y, allPositions);
              d.fx = event.x;
              d.fy = event.y;
            } else {
              // Only release non-fixed nodes (non-edit mode behavior)
              if (!d.is_entry_point && !d.is_client_summary) {
                d.fx = null;
                d.fy = null;
              }
            }
            dragStartPositions.clear();
          })
      )
      .on('click', function (event, d) {
        // Prevent click from bubbling to SVG background
        event.stopPropagation();
        // Handle node selection in edit mode
        handleNodeClick(d.id, event);
      })
      .on('mouseenter', function (_, d) {
        setHoveredNode(d);
        d3.select(this).select('circle,rect').attr('stroke-width', 3);
      })
      .on('mouseleave', function () {
        setHoveredNode(null);
        d3.select(this).select('circle,rect').attr('stroke-width', 1.5);
      });

    // Selection rings for selected nodes (in edit mode)
    nodeElements
      .filter((d) => editMode && selectedNodes.has(d.id) && d.is_client_summary === true)
      .append('rect')
      .attr('class', 'selection-ring')
      .attr('x', -36)
      .attr('y', -26)
      .attr('width', 72)
      .attr('height', 52)
      .attr('rx', 12)
      .attr('ry', 12)
      .attr('fill', 'none')
      .attr('stroke', '#60a5fa')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '4,2');

    nodeElements
      .filter((d) => editMode && selectedNodes.has(d.id) && !d.is_client_summary)
      .append('circle')
      .attr('class', 'selection-ring')
      .attr('r', (d) => (d.is_entry_point ? 24 : 20))
      .attr('fill', 'none')
      .attr('stroke', '#60a5fa')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '4,2');

    // Client summary nodes as rounded rectangles
    nodeElements
      .filter((d) => d.is_client_summary === true)
      .append('rect')
      .attr('x', -30)
      .attr('y', -20)
      .attr('width', 60)
      .attr('height', 40)
      .attr('rx', 8)
      .attr('ry', 8)
      .attr('fill', NODE_COLORS.client_summary)
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 1.5);

    // Client summary icon and count
    nodeElements
      .filter((d) => d.is_client_summary === true)
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('fill', '#1e293b')
      .attr('font-size', 14)
      .attr('font-weight', 'bold')
      .text((d) => d.client_count?.toString() || '0');

    // Regular node circles (non-client-summary)
    nodeElements
      .filter((d) => !d.is_client_summary)
      .append('circle')
      .attr('r', (d) => (d.is_entry_point ? 18 : 14))
      .attr('fill', (d) => {
        if (d.is_entry_point) return NODE_COLORS.entry_point;
        if (d.is_external) return NODE_COLORS.external;
        if (d.is_critical) return NODE_COLORS.critical;
        return NODE_COLORS.internal;
      })
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 1.5);

    // Entry point star icon
    nodeElements
      .filter((d) => d.is_entry_point)
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('fill', '#1e293b')
      .attr('font-size', 14)
      .text('★');

    // Node labels
    nodeElements
      .append('text')
      .attr('dy', (d) => d.is_client_summary ? 35 : 32)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', 11)
      .text((d) => {
        if (d.is_client_summary) {
          return `${d.client_count} clients`;
        }
        return d.display_name || d.name;
      });

    // Port labels under client summary nodes
    nodeElements
      .filter((d) => d.is_client_summary === true && d.entry_point_port !== null)
      .append('text')
      .attr('dy', 48)
      .attr('text-anchor', 'middle')
      .attr('fill', '#94a3b8')
      .attr('font-size', 9)
      .text((d) => formatProtocolPort(d.entry_point_protocol ?? 6, d.entry_point_port!));

    // Build edge grouping map for spreading labels of edges with same source-target
    const edgeGroupMap = new Map<string, { count: number; indexMap: Map<string, number> }>();
    links.forEach((link) => {
      const sourceId = typeof link.source === 'string' ? link.source : (link.source as SimNode).id;
      const targetId = typeof link.target === 'string' ? link.target : (link.target as SimNode).id;
      const key = `${sourceId}-${targetId}`;
      if (!edgeGroupMap.has(key)) {
        edgeGroupMap.set(key, { count: 0, indexMap: new Map() });
      }
      const group = edgeGroupMap.get(key)!;
      group.indexMap.set(link.id, group.count);
      group.count++;
    });

    // Update positions on tick
    simulation.on('tick', () => {
      linkElements.attr('d', (d) => {
        const source = d.source as SimNode;
        const target = d.target as SimNode;

        // Straight lines for client summary connections
        if (d.is_from_client_summary) {
          return `M${source.x},${source.y}L${target.x},${target.y}`;
        }

        // Curved lines for other connections
        const dx = (target.x ?? 0) - (source.x ?? 0);
        const dy = (target.y ?? 0) - (source.y ?? 0);
        const dr = Math.sqrt(dx * dx + dy * dy) * 1.5;
        return `M${source.x},${source.y}A${dr},${dr} 0 0,1 ${target.x},${target.y}`;
      });

      edgeLabels
        .attr('x', (d) => {
          const source = d.source as SimNode;
          const target = d.target as SimNode;
          const sx = source.x ?? 0;
          const sy = source.y ?? 0;
          const tx = target.x ?? 0;
          const ty = target.y ?? 0;
          const midX = (sx + tx) / 2;

          // For straight client edges, use simple midpoint
          if (d.is_from_client_summary) {
            return midX;
          }

          // For curved edges, offset perpendicular to edge direction
          const dx = tx - sx;
          const dy = ty - sy;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len === 0) return midX;

          // Perpendicular direction (matches arc sweep direction)
          const perpX = -dy / len;
          const offset = 15;
          let labelX = midX + perpX * offset;

          // Spread labels for edges with same source-target (different ports)
          const key = `${source.id}-${target.id}`;
          const group = edgeGroupMap.get(key);
          if (group && group.count > 1) {
            const idx = group.indexMap.get(d.id) ?? 0;
            const spreadOffset = (idx - (group.count - 1) / 2) * 18;
            // Spread along edge direction
            labelX += (dx / len) * spreadOffset;
          }

          return labelX;
        })
        .attr('y', (d) => {
          const source = d.source as SimNode;
          const target = d.target as SimNode;
          const sx = source.x ?? 0;
          const sy = source.y ?? 0;
          const tx = target.x ?? 0;
          const ty = target.y ?? 0;
          const midY = (sy + ty) / 2;

          // For straight client edges, use simple midpoint with small offset
          if (d.is_from_client_summary) {
            return midY - 8;
          }

          // For curved edges, offset perpendicular to edge direction
          const dx = tx - sx;
          const dy = ty - sy;
          const len = Math.sqrt(dx * dx + dy * dy);
          if (len === 0) return midY - 8;

          // Perpendicular direction (matches arc sweep direction)
          const perpY = dx / len;
          const offset = 15;
          let labelY = midY + perpY * offset;

          // Spread labels for edges with same source-target (different ports)
          const key = `${source.id}-${target.id}`;
          const group = edgeGroupMap.get(key);
          if (group && group.count > 1) {
            const idx = group.indexMap.get(d.id) ?? 0;
            const spreadOffset = (idx - (group.count - 1) / 2) * 18;
            // Spread along edge direction
            labelY += (dy / len) * spreadOffset;
          }

          return labelY;
        });

      // Update group bounds based on member node positions
      groupElements.each(function (d) {
        const bounds = calculateGroupBounds(d);
        if (bounds) {
          d3.select(this)
            .select('rect.group-bounds')
            .attr('x', bounds.x)
            .attr('y', bounds.y)
            .attr('width', bounds.width)
            .attr('height', bounds.height);

          d3.select(this)
            .select('text.group-label')
            .attr('x', bounds.x + 8)
            .attr('y', bounds.y + 16);

          d3.select(this)
            .select('text.group-delete')
            .attr('x', bounds.x + bounds.width - 12)
            .attr('y', bounds.y + 16);
        }
      });

      nodeElements.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    // Initial zoom to fit content (only on first render)
    if (!transformRef.current) {
      const padding = 30;
      const initialTransform = d3.zoomIdentity.translate(padding, padding).scale(0.85);
      svg.call(zoom.transform, initialTransform);
      transformRef.current = initialTransform;
    }

    return () => {
      simulation.stop();
    };
  }, [nodes, links, dimensions, effectiveRenderMode, editMode, selectedNodes, savedLayout, handleNodeDragEnd, handleNodeClick, deleteGroupMutation]);

  if (isLoading) {
    return <LoadingPage />;
  }

  if (error || !topology) {
    return (
      <div className="flex items-center justify-center h-96">
        <p className="text-red-500">Failed to load application topology</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/applications"
            className="text-slate-400 hover:text-white"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold text-white">
              {topology.application.display_name || topology.application.name}
            </h1>
            <p className="text-slate-400 mt-1">Application Topology</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <label className="text-sm text-slate-400">Hop Depth:</label>
            <input
              type="range"
              min={1}
              max={5}
              value={maxDepth}
              onChange={(e) => setMaxDepth(parseInt(e.target.value))}
              className="w-24 h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
            <span className="text-sm text-white font-medium w-4">{maxDepth}</span>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={showExternal}
              onChange={(e) => setShowExternal(e.target.checked)}
              className="rounded bg-slate-700 border-slate-600 text-blue-500 focus:ring-blue-500"
            />
            Show external connections
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={hideInfrastructureOnly}
              onChange={(e) => setHideInfrastructureOnly(e.target.checked)}
              className="rounded bg-slate-700 border-slate-600 text-blue-500 focus:ring-blue-500"
            />
            Hide infrastructure-only
          </label>
          <div className="flex items-center gap-2 border-l border-slate-700 pl-4">
            <CpuChipIcon className="h-4 w-4 text-slate-400" />
            <select
              value={renderMode}
              onChange={(e) => setRenderMode(e.target.value as RenderMode)}
              className="bg-slate-700 text-slate-300 text-sm rounded px-2 py-1 border-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="auto">Auto</option>
              <option value="svg">SVG</option>
              <option value="canvas">Canvas</option>
            </select>
          </div>
          <div className="flex items-center gap-2 border-l border-slate-700 pl-4">
            <button
              onClick={() => setEditMode(!editMode)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
                editMode
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
              title={editMode ? 'Exit edit mode' : 'Edit layout positions'}
            >
              <PencilIcon className="h-4 w-4" />
              {editMode ? 'Editing' : 'Edit Layout'}
            </button>
            {editMode && selectedNodes.size > 0 && (
              <span className="text-sm text-blue-400">
                {selectedNodes.size} selected
              </span>
            )}
            {editMode && selectedNodes.size > 0 && (
              <button
                onClick={() => setSelectedNodes(new Set())}
                className="text-sm text-slate-400 hover:text-white transition-colors"
                title="Clear selection"
              >
                Clear
              </button>
            )}
            {editMode && selectedNodes.size >= 2 && (
              <button
                onClick={() => setShowGroupModal(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded bg-purple-600 text-white hover:bg-purple-500 transition-colors"
                title="Group selected nodes"
              >
                <Squares2X2Icon className="h-4 w-4" />
                Group
              </button>
            )}
            {editMode && savedLayout && (
              <button
                onClick={() => resetLayoutMutation.mutate()}
                disabled={resetLayoutMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50 transition-colors"
                title="Reset to auto-calculated positions"
              >
                <ArrowPathIcon className={`h-4 w-4 ${resetLayoutMutation.isPending ? 'animate-spin' : ''}`} />
                Reset
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-0 h-full">
        {/* Topology Visualization */}
        <div className="lg:col-span-3 bg-slate-900 rounded-lg overflow-hidden relative min-h-[500px] h-full">
          <div ref={containerRef} className="absolute inset-0 w-full h-full">
            {effectiveRenderMode === 'canvas' ? (
              <ApplicationDetailCanvas
                nodes={nodes}
                links={links}
                width={dimensions.width}
                height={dimensions.height}
                onNodeHover={setHoveredNode}
                onEdgeHover={(edge, position) => {
                  if (edge) {
                    setHoveredEdge({ edge, position });
                  } else {
                    setHoveredEdge(null);
                  }
                }}
              />
            ) : (
              <svg
                ref={svgRef}
                className="w-full h-full bg-slate-900"
              />
            )}
          </div>

          {/* Render mode indicator */}
          {isLargeGraph && (
            <div className="absolute bottom-4 left-4 bg-slate-900/80 rounded-lg px-3 py-1.5 text-xs text-slate-300 flex items-center gap-2 pointer-events-none">
              <span className={effectiveRenderMode === 'canvas' ? 'text-green-400' : 'text-amber-400'}>
                {effectiveRenderMode === 'canvas' ? 'Canvas' : 'SVG'}
              </span>
              <span className="text-slate-500">|</span>
              <span>{nodes.length} nodes, {links.length} edges</span>
            </div>
          )}

          {/* Node hover tooltip */}
          {hoveredNode && (
            <div className="absolute top-4 right-4 bg-slate-800 rounded-lg p-4 shadow-lg max-w-xs">
              <div className="flex items-center gap-2 mb-2">
                {hoveredNode.is_client_summary ? (
                  <UsersIcon className="h-5 w-5 text-emerald-400" />
                ) : null}
                <span className="font-medium text-white">
                  {hoveredNode.is_client_summary
                    ? `${hoveredNode.client_count} External Clients`
                    : hoveredNode.display_name || hoveredNode.name}
                </span>
                {hoveredNode.is_entry_point && (
                  <StarIconSolid className="h-4 w-4 text-yellow-400" />
                )}
              </div>
              <div className="space-y-1 text-sm">
                {!hoveredNode.is_client_summary && (
                  <>
                    <div className="text-slate-400">
                      IP: <span className="text-slate-300">{hoveredNode.ip_address}</span>
                    </div>
                    <div className="text-slate-400">
                      Type: <span className="text-slate-300">{hoveredNode.asset_type}</span>
                    </div>
                    {hoveredNode.role && (
                      <div className="text-slate-400">
                        Role: <span className="text-slate-300">{hoveredNode.role}</span>
                      </div>
                    )}
                    {hoveredNode.is_entry_point && hoveredNode.entry_points.length > 0 && (
                      <div className="text-slate-400">
                        Entry Ports:{' '}
                        <span className="text-yellow-400">
                          {hoveredNode.entry_points.map((ep, i) => (
                            <span key={ep.id}>
                              {i > 0 && ', '}
                              {ep.label ? `${ep.label}: ` : ''}{ep.port}/{getProtocolName(ep.protocol)}
                            </span>
                          ))}
                        </span>
                      </div>
                    )}
                  </>
                )}
                {hoveredNode.is_client_summary && (
                  <>
                    <div className="text-slate-400">
                      Connecting to port:{' '}
                      <span className="text-emerald-400">
                        {formatProtocolPort(
                          hoveredNode.entry_point_protocol ?? 6,
                          hoveredNode.entry_point_port!
                        )}
                      </span>
                    </div>
                    {hoveredNode.total_bytes_24h !== undefined && (
                      <div className="text-slate-400">
                        Traffic (24h):{' '}
                        <span className="text-slate-300">
                          {formatBytes(hoveredNode.total_bytes_24h)}
                        </span>
                      </div>
                    )}
                  </>
                )}
                {hoveredNode.is_external && !hoveredNode.is_client_summary && (
                  <Badge variant="default" size="sm">
                    External
                  </Badge>
                )}
                {hoveredNode.is_critical && (
                  <Badge variant="error" size="sm">
                    Critical
                  </Badge>
                )}
              </div>
            </div>
          )}

          {/* Edge tooltip */}
          {hoveredEdge && (
            <EdgeTooltip
              edge={{
                source: {
                  name: (hoveredEdge.edge.source as SimNode).is_client_summary
                    ? `${(hoveredEdge.edge.source as SimNode).client_count} clients`
                    : (hoveredEdge.edge.source as SimNode).name,
                  ip_address: (hoveredEdge.edge.source as SimNode).ip_address || '',
                },
                target: {
                  name: (hoveredEdge.edge.target as SimNode).name,
                  ip_address: (hoveredEdge.edge.target as SimNode).ip_address || '',
                },
                target_port: hoveredEdge.edge.target_port,
                protocol: hoveredEdge.edge.protocol,
                bytes_last_24h: hoveredEdge.edge.bytes_last_24h ?? undefined,
                last_seen: hoveredEdge.edge.last_seen ?? undefined,
                service_type: hoveredEdge.edge.dependency_type,
              }}
              position={hoveredEdge.position}
              containerBounds={containerRef.current?.getBoundingClientRect()}
            />
          )}
        </div>

        {/* Sidebar Panels */}
        <div className="space-y-4">
          {/* Baseline Panel */}
          <BaselinePanel
            applicationId={id!}
            hopDepth={maxDepth}
          />

          {/* Inbound Traffic Summary */}
          {topology.inbound_summary && topology.inbound_summary.length > 0 && (
            <Card title="Inbound Traffic">
              <div className="space-y-3">
                {topology.inbound_summary.map((summary) => (
                  <div
                    key={`${summary.entry_point_asset_id}-${summary.port}`}
                    className="p-2 rounded bg-slate-700/50"
                  >
                    <div className="flex items-center gap-2">
                      <div className="flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500/20">
                        <UsersIcon className="h-4 w-4 text-emerald-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-white">
                          {summary.client_count} clients
                        </div>
                        <div className="text-xs text-slate-400">
                          → {summary.entry_point_name}:{summary.port}
                        </div>
                      </div>
                    </div>
                    {summary.total_bytes_24h > 0 && (
                      <div className="mt-1 text-xs text-slate-500 pl-8">
                        {formatBytes(summary.total_bytes_24h)} / 24h
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Dependencies by Hop Level */}
          {nodes.filter(n => !n.is_client_summary && (n.hop_distance ?? 0) > 0).length > 0 && (
            <Card title="Dependencies by Hop">
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {Array.from(
                  nodes
                    .filter(n => !n.is_client_summary && (n.hop_distance ?? 0) > 0)
                    .reduce((acc, node) => {
                      const hop = node.hop_distance ?? 1;
                      if (!acc.has(hop)) acc.set(hop, []);
                      acc.get(hop)!.push(node);
                      return acc;
                    }, new Map<number, SimNode[]>())
                )
                  .sort(([a], [b]) => a - b)
                  .map(([hopLevel, nodesAtHop]) => (
                    <div key={hopLevel}>
                      <div className="text-xs font-medium text-slate-400 mb-1">
                        Hop {hopLevel} ({nodesAtHop.length})
                      </div>
                      <div className="space-y-1">
                        {nodesAtHop.map((node) => (
                          <div
                            key={node.id}
                            className="flex items-center gap-2 p-1.5 rounded bg-slate-700/50 text-sm"
                          >
                            <div
                              className="w-3 h-3 rounded-full flex-shrink-0"
                              style={{
                                backgroundColor: node.is_external
                                  ? NODE_COLORS.external
                                  : node.is_critical
                                  ? NODE_COLORS.critical
                                  : NODE_COLORS.internal,
                              }}
                            />
                            <span className="text-white truncate">
                              {node.display_name || node.name}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </Card>
          )}

          <Card title="Entry Points">
            {topology.entry_points.length === 0 ? (
              <p className="text-slate-500 text-sm">No entry points defined</p>
            ) : (
              <div className="space-y-3">
                {topology.entry_points.map((ep, idx) => (
                  <div
                    key={ep.asset_id}
                    className="flex items-center gap-3 p-2 rounded bg-slate-700/50"
                  >
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-yellow-500/20">
                      <StarIconSolid className="h-4 w-4 text-yellow-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-white truncate">
                        {ep.asset_name}
                      </div>
                      {ep.port && (
                        <div className="text-xs text-slate-400">
                          {formatProtocolPort(ep.port, ep.protocol ?? 6)}
                        </div>
                      )}
                    </div>
                    <span className="text-xs text-slate-500">#{idx + 1}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Legend">
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded"
                  style={{ backgroundColor: NODE_COLORS.client_summary }}
                />
                <span className="text-slate-300">External Clients</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: NODE_COLORS.entry_point }}
                />
                <span className="text-slate-300">Entry Point</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: NODE_COLORS.internal }}
                />
                <span className="text-slate-300">Application Member</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: NODE_COLORS.external }}
                />
                <span className="text-slate-300">External Asset</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: NODE_COLORS.critical }}
                />
                <span className="text-slate-300">Critical Asset</span>
              </div>
            </div>
          </Card>

          <Card title="Info">
            <div className="text-sm text-slate-400 space-y-2">
              <p>
                <InformationCircleIcon className="inline h-4 w-4 mr-1" />
                {editMode ? 'Edit mode enabled. Positions will be saved.' : 'Click "Edit Layout" to save positions.'}
              </p>
              {editMode && (
                <>
                  <p>• Click node to select, Shift+click for multi-select</p>
                  <p>• Drag selected nodes to move them together</p>
                  <p>• Select 2+ nodes and click "Group" to group them</p>
                  <p>• Press Escape to clear selection or exit</p>
                </>
              )}
              <p>Scroll to zoom, drag background to pan.</p>
              <p>Hover over edges to see connection details.</p>
            </div>
          </Card>
        </div>
      </div>

      {/* Group Edit Modal */}
      <GroupEditModal
        isOpen={showGroupModal}
        onClose={() => setShowGroupModal(false)}
        onSave={handleCreateGroup}
        title="Create Asset Group"
      />
    </div>
  );
}
