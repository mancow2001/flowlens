/**
 * Arc Topology Renderer
 * Canvas-based renderer for arc/sunburst visualization of folder hierarchy.
 */

import { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import * as d3 from 'd3';
import type { ArcTopologyData, FolderTreeNode } from '../../types';
import {
  buildArcHierarchy,
  applyPartitionLayout,
  createArcGenerator,
  findNodeAtPoint,
  mapDependenciesToConnections,
  getAncestors,
  type ArcNode,
  type ArcLayoutConfig,
  type VisualConnection,
} from '../../utils/arcLayout';

interface ArcTopologyRendererProps {
  data: ArcTopologyData;
  width: number;
  height: number;
  onFolderClick?: (folderId: string) => void;
  onApplicationClick?: (appId: string) => void;
  onFolderDoubleClick?: (folderId: string) => void;
  focusedFolderId?: string | null;
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  content: {
    title: string;
    type: 'folder' | 'application' | 'connection';
    details: { label: string; value: string }[];
  } | null;
}

export function ArcTopologyRenderer({
  data,
  width,
  height,
  onFolderClick,
  onApplicationClick,
  onFolderDoubleClick,
  focusedFolderId,
}: ArcTopologyRendererProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredNode, setHoveredNode] = useState<d3.HierarchyRectangularNode<ArcNode> | null>(null);
  const [hoveredConnection, setHoveredConnection] = useState<VisualConnection | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, content: null });
  const [transform, setTransform] = useState<d3.ZoomTransform>(d3.zoomIdentity);

  // Layout configuration
  const config: ArcLayoutConfig = useMemo(() => {
    const minDim = Math.min(width, height);
    return {
      innerRadius: minDim * 0.1,
      outerRadius: minDim * 0.45,
      padAngle: 0.01,
      cornerRadius: 3,
    };
  }, [width, height]);

  // Build hierarchy and layout
  const { nodes, connections, arcGenerator } = useMemo(() => {
    const hierarchy = buildArcHierarchy(data);
    const root = applyPartitionLayout(hierarchy, config);
    const allNodes = root.descendants();
    const arcGen = createArcGenerator(config);
    const conns = mapDependenciesToConnections(data.dependencies, allNodes, config);

    return {
      nodes: allNodes,
      connections: conns,
      arcGenerator: arcGen,
    };
  }, [data, config]);

  // Get focused node and related nodes
  const focusedData = useMemo(() => {
    if (!focusedFolderId) {
      return { visibleNodes: nodes, visibleConnections: connections, relevantIds: undefined };
    }

    const focusNode = nodes.find(n => n.data.id === focusedFolderId);
    if (!focusNode) {
      return { visibleNodes: nodes, visibleConnections: connections, relevantIds: undefined };
    }

    const descendants = new Set(focusNode.descendants().map(n => n.data.id));
    const ancestors = new Set(getAncestors(focusNode).map(n => n.data.id));
    const relevantIds = new Set([...descendants, ...ancestors]);

    const visibleNodes = nodes;
    const visibleConnections = connections.filter(
      c => descendants.has(c.sourceId) || descendants.has(c.targetId)
    );

    return { visibleNodes, visibleConnections, relevantIds };
  }, [focusedFolderId, nodes, connections]);

  // Render function
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    // Apply transform
    const centerX = width / 2;
    const centerY = height / 2;
    ctx.save();
    ctx.translate(centerX + transform.x, centerY + transform.y);
    ctx.scale(transform.k, transform.k);

    // Draw connections first (under arcs)
    const { visibleConnections, relevantIds } = focusedData;

    ctx.lineCap = 'round';
    for (const conn of visibleConnections) {
      const isHighlighted =
        hoveredConnection?.id === conn.id ||
        hoveredNode?.data.id === conn.sourceId ||
        hoveredNode?.data.id === conn.targetId;

      ctx.beginPath();
      const path2D = new Path2D(conn.path);
      ctx.strokeStyle = isHighlighted
        ? 'rgba(59, 130, 246, 0.9)' // Blue highlight
        : `rgba(100, 116, 139, ${conn.opacity})`;
      ctx.lineWidth = isHighlighted ? conn.strokeWidth * 1.5 : conn.strokeWidth;
      ctx.stroke(path2D);
    }

    // Draw arcs
    for (const node of focusedData.visibleNodes) {
      if (node.data.type === 'root') continue;

      const isHovered = hoveredNode?.data.id === node.data.id;
      const isDimmed = focusedFolderId && !relevantIds?.has(node.data.id);

      // Generate arc path
      const arcPath = arcGenerator(node);
      if (!arcPath) continue;

      ctx.beginPath();
      const path2D = new Path2D(arcPath);

      // Fill color
      let fillColor = node.data.color || '#64748b';
      if (node.data.type === 'application') {
        // Slightly lighter for applications
        fillColor = d3.color(fillColor)?.brighter(0.3)?.formatHex() || fillColor;
      }

      // Apply opacity based on state
      let opacity = 1;
      if (isDimmed) opacity = 0.2;
      if (isHovered) opacity = 1;

      const rgbColor = d3.color(fillColor);
      if (rgbColor) {
        rgbColor.opacity = opacity;
        ctx.fillStyle = rgbColor.formatRgb();
      } else {
        ctx.fillStyle = fillColor;
      }
      ctx.fill(path2D);

      // Stroke
      ctx.strokeStyle = isHovered
        ? 'rgba(59, 130, 246, 1)'
        : isDimmed
        ? 'rgba(226, 232, 240, 0.3)'
        : 'rgba(226, 232, 240, 0.8)';
      ctx.lineWidth = isHovered ? 2 : 1;
      ctx.stroke(path2D);

      // Labels (only for larger arcs)
      const arcAngle = node.x1! - node.x0!;
      const arcRadius = config.innerRadius + (node.y0! + node.y1!) / 2;
      const arcLength = arcAngle * arcRadius;

      if (arcLength > 40 && !isDimmed) {
        const midAngle = (node.x0! + node.x1!) / 2 - Math.PI / 2;
        const labelRadius = config.innerRadius + node.y0! + (node.y1! - node.y0!) * 0.5;
        const labelX = Math.cos(midAngle) * labelRadius;
        const labelY = Math.sin(midAngle) * labelRadius;

        ctx.save();
        ctx.translate(labelX, labelY);

        // Rotate text to follow arc
        let textAngle = midAngle + Math.PI / 2;
        if (textAngle > Math.PI / 2 && textAngle < (3 * Math.PI) / 2) {
          textAngle += Math.PI;
        }
        ctx.rotate(textAngle);

        const label = node.data.displayName || node.data.name;
        const truncatedLabel = label.length > 15 ? label.substring(0, 12) + '...' : label;

        ctx.font = node.data.type === 'folder' ? 'bold 11px sans-serif' : '10px sans-serif';
        ctx.fillStyle = isHovered ? '#1e293b' : '#475569';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(truncatedLabel, 0, 0);
        ctx.restore();
      }
    }

    ctx.restore();
  }, [
    focusedData,
    hoveredNode,
    hoveredConnection,
    transform,
    arcGenerator,
    config,
    width,
    height,
    focusedFolderId,
  ]);

  // Set up canvas and rendering
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    render();
  }, [width, height, render]);

  // Set up zoom behavior
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const zoom = d3.zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.5, 4])
      .on('zoom', (event) => {
        setTransform(event.transform);
      });

    d3.select(canvas).call(zoom);

    return () => {
      d3.select(canvas).on('.zoom', null);
    };
  }, []);

  // Handle mouse move for hover detection
  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = width / 2;
      const centerY = height / 2;

      // Transform mouse coordinates
      const mouseX = (event.clientX - rect.left - centerX - transform.x) / transform.k;
      const mouseY = (event.clientY - rect.top - centerY - transform.y) / transform.k;

      // Find node under mouse
      const node = findNodeAtPoint(mouseX, mouseY, focusedData.visibleNodes, config);
      setHoveredNode(node);

      // Update tooltip
      if (node && node.data.type !== 'root') {
        const details: { label: string; value: string }[] = [];

        if (node.data.type === 'folder') {
          const folder = node.data.data as FolderTreeNode;
          if (folder) {
            details.push({ label: 'Applications', value: `${folder.applications.length}` });
            details.push({ label: 'Subfolders', value: `${folder.children.length}` });
            if (folder.team) details.push({ label: 'Team', value: folder.team });
          }
        } else if (node.data.type === 'application') {
          const app = node.data.data as any;
          if (app) {
            if (app.environment) details.push({ label: 'Environment', value: app.environment });
            if (app.criticality) details.push({ label: 'Criticality', value: app.criticality });
            if (app.team) details.push({ label: 'Team', value: app.team });
          }
        }

        setTooltip({
          visible: true,
          x: event.clientX,
          y: event.clientY,
          content: {
            title: node.data.displayName || node.data.name,
            type: node.data.type as 'folder' | 'application',
            details,
          },
        });
      } else {
        setTooltip({ visible: false, x: 0, y: 0, content: null });
        setHoveredNode(null);
      }
    },
    [focusedData.visibleNodes, config, transform, width, height]
  );

  // Handle click
  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = width / 2;
      const centerY = height / 2;

      const mouseX = (event.clientX - rect.left - centerX - transform.x) / transform.k;
      const mouseY = (event.clientY - rect.top - centerY - transform.y) / transform.k;

      const node = findNodeAtPoint(mouseX, mouseY, focusedData.visibleNodes, config);
      if (node) {
        if (node.data.type === 'folder' && onFolderClick) {
          onFolderClick(node.data.id);
        } else if (node.data.type === 'application' && onApplicationClick) {
          onApplicationClick(node.data.id);
        }
      }
    },
    [focusedData.visibleNodes, config, transform, width, height, onFolderClick, onApplicationClick]
  );

  // Handle double click
  const handleDoubleClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = width / 2;
      const centerY = height / 2;

      const mouseX = (event.clientX - rect.left - centerX - transform.x) / transform.k;
      const mouseY = (event.clientY - rect.top - centerY - transform.y) / transform.k;

      const node = findNodeAtPoint(mouseX, mouseY, focusedData.visibleNodes, config);
      if (node && node.data.type === 'folder' && onFolderDoubleClick) {
        onFolderDoubleClick(node.data.id);
      }
    },
    [focusedData.visibleNodes, config, transform, width, height, onFolderDoubleClick]
  );

  const handleMouseLeave = useCallback(() => {
    setTooltip({ visible: false, x: 0, y: 0, content: null });
    setHoveredNode(null);
    setHoveredConnection(null);
  }, []);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className="cursor-pointer"
        onMouseMove={handleMouseMove}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onMouseLeave={handleMouseLeave}
      />

      {/* Tooltip */}
      {tooltip.visible && tooltip.content && (
        <div
          className="absolute z-50 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3 pointer-events-none"
          style={{
            left: tooltip.x + 10,
            top: tooltip.y + 10,
            transform: 'translate(0, 0)',
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                tooltip.content.type === 'folder' ? 'bg-blue-500' : 'bg-green-500'
              }`}
            />
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {tooltip.content.title}
            </span>
          </div>
          {tooltip.content.details.length > 0 && (
            <div className="space-y-1">
              {tooltip.content.details.map((detail, i) => (
                <div key={i} className="text-sm text-gray-600 dark:text-gray-400">
                  <span className="text-gray-500">{detail.label}:</span> {detail.value}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3">
        <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Legend</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="w-3 h-3 rounded-sm bg-blue-500" />
            <span>Folder</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="w-3 h-3 rounded-sm bg-blue-300" />
            <span>Application (Map)</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="w-6 h-0.5 bg-gray-400" />
            <span>Dependency</span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="absolute top-4 right-4 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3">
        <div className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
          <div>Folders: {data.statistics.total_folders}</div>
          <div>Applications: {data.statistics.total_applications}</div>
          <div>Dependencies: {data.statistics.total_dependencies}</div>
        </div>
      </div>

      {/* Instructions */}
      <div className="absolute bottom-4 right-4 text-xs text-gray-500 dark:text-gray-400">
        <div>Click: Select | Double-click: Focus | Scroll: Zoom</div>
      </div>
    </div>
  );
}
