import { useRef, useEffect, useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import { topologyApi } from '../../services/api';
import Loading from '../common/Loading';
import EdgeTooltip from '../topology/EdgeTooltip';
import type { TopologyNode, TopologyEdge } from '../../types';

interface SimNode extends TopologyNode, d3.SimulationNodeDatum {
  isCenter?: boolean;
  hopDistance?: number;
  // Fixed positions for hierarchical layout
  targetX?: number;
  targetY?: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  target_port: number;
  protocol: number;
  protocol_name: string | null;
  service_type: string | null;
  bytes_last_24h: number;
  last_seen: string;
  is_critical: boolean;
}

interface BlastRadiusTopologyProps {
  centerId: string;
  maxHops: number;
  onHopsChange: (hops: number) => void;
}

// Color scale based on hop distance
const HOP_COLORS = [
  '#ef4444', // 0 hops (center) - red
  '#f97316', // 1 hop - orange
  '#eab308', // 2 hops - yellow
  '#22c55e', // 3 hops - green
  '#06b6d4', // 4 hops - cyan
  '#8b5cf6', // 5 hops - purple
];

export default function BlastRadiusTopology({
  centerId,
  maxHops,
  onHopsChange,
}: BlastRadiusTopologyProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<{
    edge: SimLink;
    position: { x: number; y: number };
  } | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  // Fetch subgraph data
  const { data: subgraph, isLoading, error } = useQuery({
    queryKey: ['topology', 'subgraph', centerId, maxHops],
    queryFn: () => topologyApi.getSubgraph(centerId, maxHops),
    enabled: !!centerId,
  });

  // Calculate hop distances for each node
  const nodesWithHops = useMemo(() => {
    if (!subgraph) return [];

    // Build adjacency list
    const adjacency = new Map<string, string[]>();
    subgraph.edges.forEach(edge => {
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
      adjacency.get(edge.source)!.push(edge.target);
      adjacency.get(edge.target)!.push(edge.source);
    });

    // BFS to calculate hop distances
    const distances = new Map<string, number>();
    distances.set(centerId, 0);
    const queue = [centerId];

    while (queue.length > 0) {
      const current = queue.shift()!;
      const currentDist = distances.get(current)!;
      const neighbors = adjacency.get(current) || [];

      for (const neighbor of neighbors) {
        if (!distances.has(neighbor)) {
          distances.set(neighbor, currentDist + 1);
          queue.push(neighbor);
        }
      }
    }

    return subgraph.nodes.map(node => ({
      ...node,
      isCenter: node.id === centerId,
      hopDistance: distances.get(node.id) ?? maxHops,
    }));
  }, [subgraph, centerId, maxHops]);

  // Handle resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const { width, height } = containerRef.current.getBoundingClientRect();
        setDimensions({ width: Math.max(width, 400), height: Math.max(height, 400) });
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
  };

  // D3 hierarchical visualization
  useEffect(() => {
    if (!svgRef.current || !subgraph || nodesWithHops.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const { width } = dimensions;

    // Group nodes by hop distance
    const nodesByHop = new Map<number, SimNode[]>();
    nodesWithHops.forEach(n => {
      const hop = n.hopDistance ?? 0;
      if (!nodesByHop.has(hop)) nodesByHop.set(hop, []);
      nodesByHop.get(hop)!.push({ ...n });
    });

    // Calculate hierarchical positions
    const rowHeight = 120; // Vertical spacing between hop levels
    const nodeSpacing = 80; // Minimum horizontal spacing between nodes
    const topPadding = 60; // Padding from top for center node

    // Create nodes with target positions
    const nodes: SimNode[] = [];
    const nodeMap = new Map<string, SimNode>();

    // Sort hops and position each level
    const sortedHops = Array.from(nodesByHop.keys()).sort((a, b) => a - b);

    sortedHops.forEach(hop => {
      const hopNodes = nodesByHop.get(hop)!;
      const rowY = topPadding + hop * rowHeight;

      // Calculate row width needed
      const rowWidth = (hopNodes.length - 1) * nodeSpacing;
      const startX = (width - rowWidth) / 2;

      hopNodes.forEach((n, idx) => {
        const node: SimNode = {
          ...n,
          targetX: startX + idx * nodeSpacing,
          targetY: rowY,
          x: startX + idx * nodeSpacing,
          y: rowY,
        };
        nodes.push(node);
        nodeMap.set(node.id, node);
      });
    });

    const links: SimLink[] = subgraph.edges
      .filter((e: TopologyEdge) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e: TopologyEdge) => ({
        ...e,
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
      }));

    // Create zoom behavior
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 3])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });

    zoomRef.current = zoom;
    svg.call(zoom);

    // Container for zoom/pan
    const container = svg.append('g');

    // Light simulation for small adjustments (collision avoidance)
    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force('collision', d3.forceCollide().radius(40).strength(0.8))
      .force('x', d3.forceX<SimNode>(d => d.targetX!).strength(0.8))
      .force('y', d3.forceY<SimNode>(d => d.targetY!).strength(0.8))
      .alphaDecay(0.05);

    // Arrow marker
    const defs = svg.append('defs');
    defs.append('marker')
      .attr('id', 'blast-arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', '#475569');

    // Create curved links (paths instead of lines for better hierarchy visualization)
    const linkGroup = container.append('g').attr('class', 'links');

    const link = linkGroup
      .selectAll('path.edge')
      .data(links)
      .join('path')
      .attr('class', 'edge')
      .attr('stroke', '#475569')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.6)
      .attr('fill', 'none')
      .attr('marker-end', 'url(#blast-arrowhead)')
      .style('cursor', 'pointer')
      .on('mouseenter', function (event, d) {
        d3.select(this)
          .attr('stroke-width', 3)
          .attr('stroke-opacity', 1)
          .attr('stroke', '#60a5fa');
        setHoveredEdge({
          edge: d,
          position: { x: event.clientX, y: event.clientY },
        });
      })
      .on('mousemove', function (event) {
        setHoveredEdge(prev => prev ? {
          ...prev,
          position: { x: event.clientX, y: event.clientY },
        } : null);
      })
      .on('mouseleave', function () {
        d3.select(this)
          .attr('stroke-width', 1.5)
          .attr('stroke-opacity', 0.6)
          .attr('stroke', '#475569');
        setHoveredEdge(null);
      });

    // Edge port labels
    const edgeLabels = linkGroup
      .selectAll('text.edge-label')
      .data(links)
      .join('text')
      .attr('class', 'edge-label')
      .attr('text-anchor', 'middle')
      .attr('fill', '#94a3b8')
      .attr('font-size', 9)
      .attr('pointer-events', 'none')
      .text(d => d.target_port.toString());

    // Function to create curved path between nodes
    const createCurvedPath = (d: SimLink) => {
      const source = d.source as SimNode;
      const target = d.target as SimNode;
      const sourceX = source.x!;
      const sourceY = source.y!;
      const targetX = target.x!;
      const targetY = target.y!;

      // If nodes are on the same level, create an arc
      if (Math.abs(sourceY - targetY) < 10) {
        const midY = sourceY - 40; // Arc above
        return `M ${sourceX} ${sourceY} Q ${(sourceX + targetX) / 2} ${midY} ${targetX} ${targetY}`;
      }

      // For hierarchical connections, use a gentle curve
      const midY = (sourceY + targetY) / 2;
      return `M ${sourceX} ${sourceY} C ${sourceX} ${midY} ${targetX} ${midY} ${targetX} ${targetY}`;
    };

    // Create drag behavior
    const drag = d3
      .drag<SVGGElement, SimNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    // Create hop level labels
    const levelLabels = container.append('g').attr('class', 'level-labels');
    sortedHops.forEach(hop => {
      const rowY = topPadding + hop * rowHeight;
      levelLabels.append('text')
        .attr('x', 20)
        .attr('y', rowY + 4)
        .attr('fill', HOP_COLORS[Math.min(hop, HOP_COLORS.length - 1)])
        .attr('font-size', 11)
        .attr('font-weight', 'bold')
        .attr('opacity', 0.7)
        .text(hop === 0 ? 'CENTER' : `${hop} HOP${hop > 1 ? 'S' : ''}`);

      // Add subtle horizontal line for each level
      levelLabels.append('line')
        .attr('x1', 80)
        .attr('x2', width - 20)
        .attr('y1', rowY)
        .attr('y2', rowY)
        .attr('stroke', HOP_COLORS[Math.min(hop, HOP_COLORS.length - 1)])
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,4')
        .attr('opacity', 0.2);
    });

    // Create node groups
    const node = container
      .append('g')
      .attr('class', 'nodes')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')
      .call(drag);

    // Add circles
    node
      .append('circle')
      .attr('r', d => d.isCenter ? 25 : 15)
      .attr('fill', d => HOP_COLORS[Math.min(d.hopDistance ?? 0, HOP_COLORS.length - 1)])
      .attr('stroke', d => d.isCenter ? '#ffffff' : d.is_critical ? '#ef4444' : '#1e293b')
      .attr('stroke-width', d => d.isCenter ? 3 : d.is_critical ? 2 : 1.5);

    // Add labels
    node
      .append('text')
      .text(d => d.name.length > 15 ? d.name.substring(0, 12) + '...' : d.name)
      .attr('dy', d => d.isCenter ? 40 : 28)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', d => d.isCenter ? 12 : 10)
      .attr('font-weight', d => d.isCenter ? 'bold' : 'normal');

    // Add hop distance label inside node
    node
      .append('text')
      .text(d => d.isCenter ? 'C' : d.hopDistance?.toString() ?? '')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', d => d.isCenter ? 14 : 11)
      .attr('font-weight', 'bold');

    // Hover effects
    node
      .on('mouseenter', function(_, d) {
        d3.select(this).select('circle')
          .attr('stroke', '#3b82f6')
          .attr('stroke-width', 3);
        setHoveredNode(d);
      })
      .on('mouseleave', function(_, d) {
        d3.select(this).select('circle')
          .attr('stroke', d.isCenter ? '#ffffff' : d.is_critical ? '#ef4444' : '#1e293b')
          .attr('stroke-width', d.isCenter ? 3 : d.is_critical ? 2 : 1.5);
        setHoveredNode(null);
      });

    // Helper to get midpoint of curved path
    const getCurvedPathMidpoint = (d: SimLink) => {
      const source = d.source as SimNode;
      const target = d.target as SimNode;
      const sourceX = source.x!;
      const sourceY = source.y!;
      const targetX = target.x!;
      const targetY = target.y!;

      // For same-level nodes (arc above)
      if (Math.abs(sourceY - targetY) < 10) {
        return {
          x: (sourceX + targetX) / 2,
          y: sourceY - 40 + 10, // Midpoint of arc, slightly below apex
        };
      }

      // For hierarchical connections (midpoint of bezier)
      return {
        x: (sourceX + targetX) / 2,
        y: (sourceY + targetY) / 2 - 8,
      };
    };

    // Update positions
    simulation.on('tick', () => {
      link.attr('d', createCurvedPath);

      // Update edge label positions
      edgeLabels
        .attr('x', d => getCurvedPathMidpoint(d).x)
        .attr('y', d => getCurvedPathMidpoint(d).y);

      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [subgraph, nodesWithHops, dimensions]);

  if (isLoading) {
    return (
      <div className="h-96 flex items-center justify-center">
        <Loading />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-96 flex items-center justify-center text-red-400">
        Failed to load topology data
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center justify-between bg-slate-700/50 p-4 rounded-lg">
        <div className="flex items-center gap-4">
          <label className="text-sm text-slate-300">
            Max Hops: <span className="font-bold text-white">{maxHops}</span>
          </label>
          <input
            type="range"
            min="1"
            max="5"
            value={maxHops}
            onChange={(e) => onHopsChange(Number(e.target.value))}
            className="w-48 h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-primary-500"
          />
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map(hop => (
              <button
                key={hop}
                onClick={() => onHopsChange(hop)}
                className={`w-8 h-8 rounded text-sm font-medium transition-colors ${
                  maxHops === hop
                    ? 'bg-primary-500 text-white'
                    : 'bg-slate-600 text-slate-300 hover:bg-slate-500'
                }`}
              >
                {hop}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={resetView}
          className="px-3 py-1.5 text-sm bg-slate-600 hover:bg-slate-500 text-white rounded transition-colors"
        >
          Reset View
        </button>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-sm">
        <span className="text-slate-400">Hop Distance:</span>
        {HOP_COLORS.slice(0, maxHops + 1).map((color, i) => (
          <div key={i} className="flex items-center gap-1">
            <div
              className="w-4 h-4 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-slate-300">
              {i === 0 ? 'Center' : `${i} hop${i > 1 ? 's' : ''}`}
            </span>
          </div>
        ))}
      </div>

      {/* Graph container - taller to accommodate hierarchical layout */}
      <div
        ref={containerRef}
        className="h-[600px] bg-slate-800 border border-slate-700 rounded-lg overflow-hidden relative"
      >
        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
          preserveAspectRatio="xMidYMid meet"
        />

        {/* Hover tooltip */}
        {hoveredNode && (
          <div className="absolute top-4 right-4 bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-lg max-w-xs">
            <p className="font-medium text-white">{hoveredNode.name}</p>
            <p className="text-sm text-slate-400 mt-1">{hoveredNode.ip_address}</p>
            <div className="flex items-center gap-2 mt-2">
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{ backgroundColor: HOP_COLORS[Math.min(hoveredNode.hopDistance ?? 0, HOP_COLORS.length - 1)] }}
              />
              <span className="text-sm text-slate-300">
                {hoveredNode.isCenter ? 'Center asset' : `${hoveredNode.hopDistance} hop${(hoveredNode.hopDistance ?? 0) > 1 ? 's' : ''} away`}
              </span>
            </div>
            {hoveredNode.is_critical && (
              <span className="inline-block mt-2 px-2 py-0.5 text-xs bg-red-500/20 text-red-400 rounded">
                Critical Asset
              </span>
            )}
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="flex flex-wrap items-center gap-6 text-sm text-slate-400">
        <span>
          <span className="text-white font-medium">{nodesWithHops.length}</span> assets affected
        </span>
        <span>
          <span className="text-white font-medium">{subgraph?.edges.length ?? 0}</span> connections
        </span>
        <span>
          <span className="text-white font-medium">
            {nodesWithHops.filter(n => n.is_critical && !n.isCenter).length}
          </span> critical assets in blast radius
        </span>
        <span className="text-slate-500">|</span>
        {/* Per-hop breakdown */}
        {Array.from({ length: maxHops }, (_, i) => i + 1).map(hop => {
          const count = nodesWithHops.filter(n => n.hopDistance === hop).length;
          if (count === 0) return null;
          return (
            <span key={hop} className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: HOP_COLORS[hop] }}
              />
              <span className="text-white font-medium">{count}</span>
              <span>at {hop} hop{hop > 1 ? 's' : ''}</span>
            </span>
          );
        })}
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
