import { useRef, useEffect, useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import {
  ArrowLeftIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import { LoadingPage } from '../components/common/Loading';
import EdgeTooltip from '../components/topology/EdgeTooltip';
import { applicationsApi } from '../services/api';
import { getProtocolName, formatProtocolPort } from '../utils/network';
import type { AssetType } from '../types';

// D3 simulation node extending the API response
interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  display_name: string | null;
  ip_address: string;
  asset_type: AssetType;
  is_entry_point: boolean;
  entry_point_port: number | null;
  entry_point_protocol: number | null;
  entry_point_order: number | null;
  role: string | null;
  is_critical: boolean;
  is_external?: boolean;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  target_port: number;
  protocol: number;
  dependency_type: string | null;
  bytes_last_24h: number | null;
  last_seen: string | null;
  is_internal: boolean;
}

// Color scheme for nodes
const NODE_COLORS = {
  entry_point: '#eab308', // yellow for entry points
  internal: '#3b82f6', // blue for internal members
  external: '#6b7280', // gray for external
  critical: '#ef4444', // red for critical
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
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  // Fetch application topology
  const { data: topology, isLoading, error } = useQuery({
    queryKey: ['application-topology', id, showExternal],
    queryFn: () => applicationsApi.getTopology(id!, showExternal),
    enabled: !!id,
  });

  // Transform data for D3
  const { nodes, links } = useMemo(() => {
    if (!topology) return { nodes: [], links: [] };

    const simNodes: SimNode[] = topology.nodes.map((node) => ({
      ...node,
      x: undefined,
      y: undefined,
    }));

    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    const simLinks: SimLink[] = topology.edges
      .filter((edge) => nodeMap.has(edge.source) && nodeMap.has(edge.target))
      .map((edge, i) => ({
        id: `${edge.source}-${edge.target}-${i}`,
        source: edge.source,
        target: edge.target,
        target_port: edge.target_port,
        protocol: edge.protocol,
        dependency_type: edge.dependency_type,
        bytes_last_24h: edge.bytes_last_24h,
        last_seen: edge.last_seen,
        is_internal: edge.is_internal,
      }));

    return { nodes: simNodes, links: simLinks };
  }, [topology]);

  // Handle container resize
  useEffect(() => {
    if (!containerRef.current) return;

    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    updateDimensions();
    const resizeObserver = new ResizeObserver(updateDimensions);
    resizeObserver.observe(containerRef.current);

    return () => resizeObserver.disconnect();
  }, []);

  // D3 force simulation
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const { width, height } = dimensions;

    // Create zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);
    zoomRef.current = zoom;

    // Main group for zoom/pan
    const g = svg.append('g');

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

    // Entry point marker (star shape)
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

    // Create simulation
    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(120)
      )
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40));

    // Draw links
    const linksGroup = g.append('g').attr('class', 'links');
    const linkElements = linksGroup
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('fill', 'none')
      .attr('stroke', (d) => (d.is_internal ? '#64748b' : '#374151'))
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.6)
      .attr('marker-end', 'url(#arrowhead)')
      .style('cursor', 'pointer')
      .on('mouseenter', function (event, d) {
        d3.select(this).attr('stroke-width', 4).attr('stroke-opacity', 1);
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
      .on('mouseleave', function () {
        d3.select(this).attr('stroke-width', 2).attr('stroke-opacity', 0.6);
        setHoveredEdge(null);
      });

    // Port labels on edges
    const edgeLabels = linksGroup
      .selectAll('text.edge-label')
      .data(links)
      .join('text')
      .attr('class', 'edge-label')
      .attr('text-anchor', 'middle')
      .attr('fill', '#94a3b8')
      .attr('font-size', 9)
      .attr('pointer-events', 'none')
      .text((d) => d.target_port?.toString() || '');

    // Draw nodes
    const nodesGroup = g.append('g').attr('class', 'nodes');
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
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      )
      .on('mouseenter', function (_, d) {
        setHoveredNode(d);
        d3.select(this).select('circle').attr('stroke-width', 3);
      })
      .on('mouseleave', function () {
        setHoveredNode(null);
        d3.select(this).select('circle').attr('stroke-width', 1.5);
      });

    // Node circles
    nodeElements
      .append('circle')
      .attr('r', (d) => (d.is_entry_point ? 16 : 12))
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
      .attr('font-size', 12)
      .text('★');

    // Node labels
    nodeElements
      .append('text')
      .attr('dy', 28)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', 11)
      .text((d) => d.display_name || d.name);

    // Update positions on tick
    simulation.on('tick', () => {
      linkElements.attr('d', (d) => {
        const source = d.source as SimNode;
        const target = d.target as SimNode;
        const dx = (target.x ?? 0) - (source.x ?? 0);
        const dy = (target.y ?? 0) - (source.y ?? 0);
        const dr = Math.sqrt(dx * dx + dy * dy) * 1.5;
        return `M${source.x},${source.y}A${dr},${dr} 0 0,1 ${target.x},${target.y}`;
      });

      edgeLabels
        .attr('x', (d) => {
          const source = d.source as SimNode;
          const target = d.target as SimNode;
          return ((source.x ?? 0) + (target.x ?? 0)) / 2;
        })
        .attr('y', (d) => {
          const source = d.source as SimNode;
          const target = d.target as SimNode;
          return ((source.y ?? 0) + (target.y ?? 0)) / 2 - 5;
        });

      nodeElements.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    // Initial zoom to fit
    const padding = 50;
    svg.call(
      zoom.transform,
      d3.zoomIdentity.translate(padding, padding).scale(0.9)
    );

    return () => {
      simulation.stop();
    };
  }, [nodes, links, dimensions]);

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
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={showExternal}
              onChange={(e) => setShowExternal(e.target.checked)}
              className="rounded bg-slate-700 border-slate-600 text-blue-500 focus:ring-blue-500"
            />
            Show external connections
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1">
        {/* Topology Visualization */}
        <div className="lg:col-span-3 bg-slate-900 rounded-lg overflow-hidden relative">
          <div ref={containerRef} className="w-full h-[600px]">
            <svg
              ref={svgRef}
              width={dimensions.width}
              height={dimensions.height}
              className="bg-slate-900"
            />
          </div>

          {/* Node hover tooltip */}
          {hoveredNode && (
            <div className="absolute top-4 right-4 bg-slate-800 rounded-lg p-4 shadow-lg max-w-xs">
              <div className="flex items-center gap-2 mb-2">
                <span className="font-medium text-white">
                  {hoveredNode.display_name || hoveredNode.name}
                </span>
                {hoveredNode.is_entry_point && (
                  <StarIconSolid className="h-4 w-4 text-yellow-400" />
                )}
              </div>
              <div className="space-y-1 text-sm">
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
                {hoveredNode.is_entry_point && hoveredNode.entry_point_port && (
                  <div className="text-slate-400">
                    Entry Port:{' '}
                    <span className="text-yellow-400">
                      {hoveredNode.entry_point_port}/
                      {getProtocolName(hoveredNode.entry_point_protocol ?? 6)}
                    </span>
                  </div>
                )}
                {hoveredNode.is_external && (
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
                  name: (hoveredEdge.edge.source as SimNode).name,
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

        {/* Entry Points Panel */}
        <div className="space-y-4">
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
                Drag nodes to reposition them.
              </p>
              <p>Scroll to zoom, drag background to pan.</p>
              <p>Hover over edges to see connection details.</p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
