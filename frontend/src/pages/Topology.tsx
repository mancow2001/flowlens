import { useRef, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as d3 from 'd3';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import { topologyApi } from '../services/api';
import type { TopologyNode } from '../types';

interface SimNode extends TopologyNode, d3.SimulationNodeDatum {}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  id: string;
  port: number;
  protocol: string;
  bytes_total: number;
  is_active: boolean;
}

const NODE_COLORS: Record<string, string> = {
  server: '#3b82f6',
  database: '#8b5cf6',
  workstation: '#10b981',
  network_device: '#f59e0b',
  load_balancer: '#06b6d4',
  firewall: '#ef4444',
  container: '#14b8a6',
  cloud_service: '#6366f1',
  external: '#f97316',
  unknown: '#6b7280',
};

export default function Topology() {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  const { data: topology, isLoading } = useQuery({
    queryKey: ['topology', 'graph'],
    queryFn: () => topologyApi.getGraph(),
  });

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
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
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

    svg.call(zoom);

    // Create container for zoom/pan
    const container = svg.append('g');

    // Create simulation
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
      .attr('stroke', (d) => (d.is_active ? '#3b82f6' : '#475569'))
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

    // Add circles to nodes
    node
      .append('circle')
      .attr('r', 20)
      .attr('fill', (d) => NODE_COLORS[d.type] || NODE_COLORS.unknown)
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

    // Add icon/initial to nodes
    node
      .append('text')
      .text((d) => d.name.charAt(0).toUpperCase())
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
    });

    // Cleanup
    return () => {
      simulation.stop();
    };
  }, [topology, dimensions]);

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
          <Button variant="secondary" size="sm">
            Reset View
          </Button>
          <Button variant="secondary" size="sm">
            Export
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
            <div className="space-y-2">
              {Object.entries(NODE_COLORS).map(([type, color]) => (
                <div key={type} className="flex items-center gap-2">
                  <div
                    className="w-4 h-4 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-sm text-slate-300 capitalize">
                    {type?.replace('_', ' ') ?? 'Unknown'}
                  </span>
                </div>
              ))}
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
                  <span className="text-sm text-slate-400">External</span>
                  <p className="text-white">
                    {selectedNode.is_external ? 'Yes' : 'No'}
                  </p>
                </div>
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
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
