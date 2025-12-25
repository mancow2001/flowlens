import { useRef, useEffect, useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { topologyApi } from '../services/api';
import type { TopologyNode, TopologyEdge } from '../types';

interface SimNode extends TopologyNode, d3.SimulationNodeDatum {}

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
}

type GroupingMode = 'none' | 'location' | 'environment' | 'datacenter' | 'type';

// Colors for node types
const NODE_COLORS: Record<string, string> = {
  server: '#3b82f6',
  database: '#8b5cf6',
  workstation: '#10b981',
  network_device: '#f59e0b',
  load_balancer: '#06b6d4',
  firewall: '#ef4444',
  container: '#14b8a6',
  cloud_service: '#6366f1',
  router: '#f59e0b',
  switch: '#f59e0b',
  storage: '#8b5cf6',
  virtual_machine: '#3b82f6',
  unknown: '#6b7280',
};

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
      return node.type?.replace('_', ' ') || 'Unknown';
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
function hullPath(hull: [number, number][], padding: number = 30): string {
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

export default function Topology() {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [groupingMode, setGroupingMode] = useState<GroupingMode>('none');
  const simulationRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology', 'graph'],
    queryFn: () => topologyApi.getGraph(),
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
  };

  // D3 Force simulation
  useEffect(() => {
    if (!svgRef.current || !topology || topology.nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const { width, height } = dimensions;

    // Create simulation nodes and links
    const nodes: SimNode[] = topology.nodes.map((n) => ({ ...n }));
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    const links: SimLink[] = topology.edges
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

    simulationRef.current = simulation;

    // Create arrow marker
    svg
      .append('defs')
      .append('marker')
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

    // Create links
    const link = container
      .append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('class', 'edge')
      .attr('stroke', (d) => (d.is_critical ? '#ef4444' : '#3b82f6'))
      .attr('stroke-width', (d) => Math.min(Math.log(d.bytes_total + 1) / 5, 4))
      .attr('marker-end', 'url(#arrowhead)');

    // Create drag behavior
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
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
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
      .call(dragBehavior);

    // Add circles to nodes - color based on internal/external
    node
      .append('circle')
      .attr('r', 20)
      .attr('fill', (d) => d.is_internal ? '#10b981' : '#f97316')
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 2);

    // Add labels to nodes
    node
      .append('text')
      .text((d) => d.name.substring(0, 12))
      .attr('dy', 35)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', 11);

    // Add icon/initial to nodes - I for internal, E for external
    node
      .append('text')
      .text((d) => d.is_internal ? 'I' : 'E')
      .attr('dy', 5)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', 14)
      .attr('font-weight', 'bold');

    // Handle click
    node.on('click', (_, d) => {
      setSelectedNode(d);
    });

    // Handle hover
    node
      .on('mouseenter', function () {
        d3.select(this).select('circle').attr('stroke', '#3b82f6').attr('stroke-width', 3);
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle').attr('stroke', '#1e293b').attr('stroke-width', 2);
      });

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!);

      node.attr('transform', (d) => `translate(${d.x},${d.y})`);

      // Update group hulls
      if (groupingMode !== 'none') {
        hullGroup.selectAll('*').remove();

        groups.forEach((groupNodes, key) => {
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
              hullGroup
                .append('path')
                .attr('d', hullPath(hull, 40))
                .attr('fill', color)
                .attr('fill-opacity', 0.1)
                .attr('stroke', color)
                .attr('stroke-width', 2)
                .attr('stroke-opacity', 0.5);

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
              .attr('stroke-opacity', 0.5);

            hullGroup
              .append('text')
              .attr('x', cx)
              .attr('y', cy - 70)
              .attr('text-anchor', 'middle')
              .attr('fill', color)
              .attr('font-size', 14)
              .attr('font-weight', 'bold')
              .text(key);
          }
        });
      }
    });

    // Cleanup
    return () => {
      simulation.stop();
    };
  }, [topology, dimensions, groupingMode, groups, groupColors]);

  if (isLoading) {
    return <LoadingPage />;
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Topology Map</h1>
          <p className="text-slate-400 mt-1">
            Interactive visualization of asset dependencies
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <Button variant="secondary" size="sm" onClick={resetView}>
            Reset View
          </Button>
        </div>
      </div>

      <div className="flex-1 flex gap-4">
        {/* Graph Area */}
        <div
          ref={containerRef}
          className="flex-1 bg-slate-800 border border-slate-700 rounded-lg overflow-hidden"
        >
          {topology && topology.nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-400">
              No topology data available
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
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-2">Node Colors</div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-green-500" />
                  <span className="text-sm text-slate-300">Internal (I)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-orange-500" />
                  <span className="text-sm text-slate-300">External (E)</span>
                </div>
              </div>

              {groupingMode !== 'none' && groups.size > 0 && (
                <>
                  <div className="text-xs text-slate-400 uppercase tracking-wider mt-4 mb-2">Groups</div>
                  <div className="space-y-2">
                    {Array.from(groupColors.entries()).map(([name, color]) => (
                      <div key={name} className="flex items-center gap-2">
                        <div
                          className="w-4 h-4 rounded"
                          style={{ backgroundColor: color, opacity: 0.5 }}
                        />
                        <span className="text-sm text-slate-300">{name}</span>
                        <span className="text-xs text-slate-500">
                          ({groups.get(name)?.length || 0})
                        </span>
                      </div>
                    ))}
                  </div>
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
                    {selectedNode.type?.replace('_', ' ') ?? 'Unknown'}
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

          {/* Stats */}
          <Card title="Statistics">
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-400">Nodes</span>
                <span className="text-white">{topology?.nodes.length ?? 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Edges</span>
                <span className="text-white">{topology?.edges.length ?? 0}</span>
              </div>
              {groupingMode !== 'none' && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Groups</span>
                  <span className="text-white">{groups.size}</span>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
